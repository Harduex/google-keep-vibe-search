"""Deterministic tag deduplication service with auto and gray tiers + LLM adjudication."""

import re
from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.services.agent.constants import TOOL_RETRIES
from app.services.agent.model_factory import build_agent_model
from app.services.tagging.constants import TAG_MERGE_AUTO, TAG_MERGE_GRAY_LOW


class MergeDecision(BaseModel):
    tag_a: str
    tag_b: str
    verdict: Literal["merge", "keep_both"]
    canonical: Optional[str] = None  # required iff merge


class DedupeReview(BaseModel):
    decisions: List[MergeDecision]


GRAY_ADJUDICATION_PROMPT = """You are deciding whether pairs of similar note tags in a personal vault should be merged into a single tag or kept separate.

GRAY PAIRS TO REVIEW:
{pairs_text}

Rules:
- Merge ONLY true duplicates or synonyms (e.g., "keyboards" vs "keyboard", "recipes" vs "cooking recipes").
- Subtopic vs parent topic (e.g., "guitar" vs "music gear") = keep_both.
- Distinct topics = keep_both.
- If verdict is "merge", canonical MUST be set to one of the two tags (tag_a or tag_b), preferably the one with higher note count."""


def normalize_tag(tag: str) -> str:
    cleaned = tag.strip().lower().strip('"\'`')
    if cleaned.endswith("."):
        cleaned = cleaned[:-1].strip()
    return re.sub(r"\s+", " ", cleaned)


def deduplicate_tags(
    tag_counts: Dict[str, int], model_name: Optional[str] = None
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """Deduplicate tag list using exact normalization, plural rules, and embedding similarity.

    Returns:
        (canonical_mapping: {old_tag: new_tag}, gray_pairs: [{tag1, tag2, similarity, count1, count2}])
    """
    if not tag_counts:
        return {}, []

    raw_tags = list(tag_counts.keys())
    canonical_mapping: Dict[str, str] = {t: t for t in raw_tags}

    # Step 1: Normalize exact dupes
    norm_to_tags: Dict[str, List[str]] = {}
    for tag in raw_tags:
        norm = normalize_tag(tag)
        norm_to_tags.setdefault(norm, []).append(tag)

    for norm, group in norm_to_tags.items():
        if len(group) > 1:
            # Pick tag with highest count
            primary = max(group, key=lambda t: (tag_counts[t], -len(t)))
            for tag in group:
                canonical_mapping[tag] = primary

    # Active unique tags after step 1
    active_tags = sorted(list(set(canonical_mapping.values())))

    # Step 2: Plural rule: a + "s" == b -> keep shorter
    plural_mapping: Dict[str, str] = {}
    for i in range(len(active_tags)):
        t1 = active_tags[i]
        for j in range(i + 1, len(active_tags)):
            t2 = active_tags[j]
            if t1 + "s" == t2 or t2 + "s" == t1:
                shorter = t1 if len(t1) <= len(t2) else t2
                longer = t2 if len(t1) <= len(t2) else t1
                plural_mapping[longer] = shorter

    for old_tag, can_tag in list(canonical_mapping.items()):
        if can_tag in plural_mapping:
            canonical_mapping[old_tag] = plural_mapping[can_tag]

    # Active unique tags after step 2
    active_tags = sorted(list(set(canonical_mapping.values())))
    if len(active_tags) <= 1:
        return canonical_mapping, []

    # Step 3: Embed active tag strings and check cosine similarity
    target_model = model_name or settings.embedding_model
    model = SentenceTransformer(target_model)
    embeddings = model.encode(active_tags, normalize_embeddings=True)

    sim_matrix = cosine_similarity(embeddings)

    auto_merges: Dict[str, str] = {}
    gray_pairs: List[Dict[str, Any]] = []

    for i in range(len(active_tags)):
        for j in range(i + 1, len(active_tags)):
            t1, t2 = active_tags[i], active_tags[j]
            sim = float(sim_matrix[i, j])

            c1 = tag_counts.get(t1, 0)
            c2 = tag_counts.get(t2, 0)

            if sim >= TAG_MERGE_AUTO:
                target = t1 if c1 >= c2 else t2
                source = t2 if c1 >= c2 else t1
                auto_merges[source] = target
            elif sim >= TAG_MERGE_GRAY_LOW:
                gray_pairs.append(
                    {
                        "tag1": t1,
                        "tag2": t2,
                        "similarity": round(sim, 4),
                        "count1": c1,
                        "count2": c2,
                    }
                )

    for old_tag, can_tag in list(canonical_mapping.items()):
        current = can_tag
        while current in auto_merges:
            current = auto_merges[current]
        canonical_mapping[old_tag] = current

    return canonical_mapping, gray_pairs


def adjudicate_gray_pairs(gray_pairs: List[Dict[str, Any]]) -> List[MergeDecision]:
    """Perform ONE LLM call to decide gray-zone tag pairs with strict validation."""
    if not gray_pairs:
        return []

    print(f"[TAGGING DEDUPE] Adjudicating {len(gray_pairs)} gray-zone tag pairs via LLM...")

    valid_pairs_set = set()
    pairs_lines = []
    for pair in gray_pairs:
        t1, t2 = pair["tag1"], pair["tag2"]
        c1, c2 = pair.get("count1", 0), pair.get("count2", 0)
        valid_pairs_set.add((t1, t2))
        valid_pairs_set.add((t2, t1))
        pairs_lines.append(f"- Tag A: '{t1}' ({c1} notes), Tag B: '{t2}' ({c2} notes)")

    pairs_text = "\n".join(pairs_lines)
    prompt = GRAY_ADJUDICATION_PROMPT.format(pairs_text=pairs_text)

    decisions: List[MergeDecision] = []
    reviewed_pairs = set()

    try:
        model = build_agent_model()
        agent = Agent(model, result_type=DedupeReview, retries=TOOL_RETRIES)
        res = agent.run_sync(prompt)

        for d in res.data.decisions:
            pair_key = (d.tag_a, d.tag_b)
            rev_key = (d.tag_b, d.tag_a)

            if pair_key not in valid_pairs_set:
                continue

            reviewed_pairs.add(pair_key)
            reviewed_pairs.add(rev_key)

            if d.verdict == "merge":
                # Hard validation: canonical MUST be in {tag_a, tag_b}
                if d.canonical not in {d.tag_a, d.tag_b}:
                    decisions.append(
                        MergeDecision(tag_a=d.tag_a, tag_b=d.tag_b, verdict="keep_both")
                    )
                else:
                    decisions.append(d)
            else:
                decisions.append(
                    MergeDecision(tag_a=d.tag_a, tag_b=d.tag_b, verdict="keep_both")
                )

    except Exception as e:
        print(f"Warning: LLM gray zone adjudication error: {e}")

    # Any un-reviewed input pairs default to keep_both
    for pair in gray_pairs:
        t1, t2 = pair["tag1"], pair["tag2"]
        if (t1, t2) not in reviewed_pairs and (t2, t1) not in reviewed_pairs:
            decisions.append(MergeDecision(tag_a=t1, tag_b=t2, verdict="keep_both"))

    print(f"          └─ Gray-zone adjudication complete ({len(decisions)} decisions)")
    return decisions


def format_dashboard_proposals(
    canonical_mapping: Dict[str, str],
    merge_decisions: List[MergeDecision],
    tag_counts: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Format auto-merges (informational) and gray-zone merge decisions (proposals) for OrganizeDashboard."""
    proposals: List[Dict[str, Any]] = []

    # Informational auto merges
    for old_tag, new_tag in canonical_mapping.items():
        if old_tag != new_tag:
            proposals.append(
                {
                    "type": "info",
                    "message": f"Auto-merged '{old_tag}' into '{new_tag}'",
                }
            )

    # Actionable proposals from LLM gray zone verdicts
    for dec in merge_decisions:
        if dec.verdict == "merge" and dec.canonical:
            source = dec.tag_b if dec.canonical == dec.tag_a else dec.tag_a
            target = dec.canonical
            count_total = tag_counts.get(source, 0) + tag_counts.get(target, 0)
            proposals.append(
                {
                    "type": "proposal",
                    "action": "merge_tags",
                    "source_tag": source,
                    "target_tag": target,
                    "message": f"Merge '{source}' into '{target}' ({count_total} notes)",
                }
            )

    return proposals
