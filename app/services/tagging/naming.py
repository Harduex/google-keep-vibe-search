"""Sequential, constrained LLM cluster naming service."""

import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.services.agent.constants import TOOL_RETRIES
from app.services.agent.model_factory import build_agent_model

BANNED_TAGS = {"misc", "notes", "general", "other", "stuff", "various", "topics"}
TAG_REGEX = re.compile(r"^[a-z0-9][a-z0-9 &\-]{0,39}$")

VERBATIM_NAMING_PROMPT = """You are naming a group of similar personal notes with a short tag.

KEYWORDS extracted from this group: {keywords}

SAMPLE NOTES from this group:
{samples}

EXISTING TAGS in this vault (reuse one if it fits well):
{existing_tags}

Rules:
- Output a tag of 1 to 3 words.
- Prefer reusing an EXISTING TAG when it accurately describes the group.
- Be specific ("mechanical keyboards"), not generic ("technology", "notes", "misc").
- Output ONLY the tag. No explanation, no punctuation, no quotes."""


class TagName(BaseModel):
    tag: str = Field(..., max_length=40)


def validate_tag(tag: str) -> bool:
    cleaned = tag.strip().lower().strip('"\'`')
    if cleaned.endswith("."):
        cleaned = cleaned[:-1].strip()
    if not cleaned:
        return False
    if cleaned in BANNED_TAGS:
        return False
    if len(cleaned.split()) > 3:
        return False
    if not TAG_REGEX.match(cleaned):
        return False
    return True


def clean_and_normalize_tag(tag: str) -> str:
    cleaned = tag.strip().lower().strip('"\'`')
    if cleaned.endswith("."):
        cleaned = cleaned[:-1].strip()
    return cleaned


def name_single_cluster(
    keywords: List[str], samples_text: str, existing_tags: List[str]
) -> str:
    prompt = VERBATIM_NAMING_PROMPT.format(
        keywords=", ".join(keywords),
        samples=samples_text,
        existing_tags=", ".join(existing_tags) if existing_tags else "(none)",
    )

    try:
        model = build_agent_model()
        agent = Agent(model, result_type=TagName, retries=TOOL_RETRIES)
        result = agent.run_sync(prompt)
        raw_tag = result.data.tag

        if validate_tag(raw_tag):
            return clean_and_normalize_tag(raw_tag)

        # Retry once with reason
        retry_prompt = (
            f"{prompt}\n\n"
            f"Previous output '{raw_tag}' was invalid (must be 1-3 lowercase words, specific, no punctuation). "
            "Please provide a valid tag."
        )
        retry_result = agent.run_sync(retry_prompt)
        retry_tag = retry_result.data.tag

        if validate_tag(retry_tag):
            return clean_and_normalize_tag(retry_tag)

    except Exception as e:
        print(f"Warning: LLM tag naming exception: {e}")

    # Fallback = top-2 c-TF-IDF keywords joined by space
    fallback = " ".join(keywords[:2]) if keywords else "uncategorized"
    fallback_clean = clean_and_normalize_tag(fallback)
    print(f"Warning: Tag naming fallback used: '{fallback_clean}'")
    return fallback_clean if validate_tag(fallback_clean) else "topics"


def name_clusters_sequential(clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order clusters by size DESC, name sequentially appending accepted tags to existing_tags."""
    sorted_clusters = sorted(clusters, key=lambda c: c.get("size", len(c.get("notes", []))), reverse=True)
    existing_tags: List[str] = []

    for cluster in sorted_clusters:
        keywords = cluster.get("keywords", [])
        samples_text = cluster.get("samples_text", "")
        accepted = name_single_cluster(keywords, samples_text, existing_tags)
        cluster["name"] = accepted
        if accepted not in existing_tags:
            existing_tags.append(accepted)

    return sorted_clusters
