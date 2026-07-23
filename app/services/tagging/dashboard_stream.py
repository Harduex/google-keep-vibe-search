"""Dashboard proposal formatting for the streaming categorization pipeline.

The streaming ``CategorizationService`` stages proposals for user approval
(nothing is written to disk until the dashboard "Apply" step). These helpers
turn its intermediate signals into the same proposal shapes the batch pipeline
emits (see ``dedupe.format_dashboard_proposals``) so the frontend has one
contract:

- auto-merges the pipeline already applied -> informational (no buttons)
- surviving near-duplicate tag pairs -> actionable ``merge_tags`` proposals
- low-confidence (catch-all) note assignments -> ``assign_tag`` review proposals

All functions are pure and deterministic so they can be unit-tested without a
GPU, LLM, or the note vault.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.services.tagging.constants import TAG_MERGE_AUTO, TAG_MERGE_GRAY_LOW


def auto_merge_info(merges: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """Informational cards for merges already applied during consolidation.

    ``merges`` is a list of ``(source_tag, target_tag)`` pairs. Self-merges and
    duplicates are skipped.
    """
    proposals: List[Dict[str, Any]] = []
    seen = set()
    for source, target in merges:
        if not source or not target or source == target:
            continue
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        proposals.append(
            {
                "type": "info",
                "message": f"Auto-merged '{source}' into '{target}'",
            }
        )
    return proposals


def gray_zone_merge_proposals(
    labels: List[Tuple[str, int, Optional[np.ndarray]]],
) -> List[Dict[str, Any]]:
    """Actionable merge proposals for near-duplicate tag pairs.

    ``labels`` is a list of ``(name, note_count, prototype_vector)``. Pairs whose
    cosine similarity falls in ``[TAG_MERGE_GRAY_LOW, TAG_MERGE_AUTO)`` are
    surfaced for user approval. Each tag appears in at most one proposal; the
    larger tag is the merge target.
    """
    usable = [(name, count, vec) for name, count, vec in labels if vec is not None]
    if len(usable) < 2:
        return []

    pairs: List[Tuple[float, int, int]] = []
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            v1 = usable[i][2]
            v2 = usable[j][2]
            denom = float(np.linalg.norm(v1) * np.linalg.norm(v2))
            sim = float(np.dot(v1, v2) / denom) if denom > 0 else 0.0
            if TAG_MERGE_GRAY_LOW <= sim < TAG_MERGE_AUTO:
                pairs.append((sim, i, j))

    # Highest-similarity pairs first; keep each tag in a single proposal.
    pairs.sort(key=lambda p: p[0], reverse=True)
    used: set = set()
    proposals: List[Dict[str, Any]] = []
    for sim, i, j in pairs:
        if i in used or j in used:
            continue
        used.add(i)
        used.add(j)

        name_i, count_i, _ = usable[i]
        name_j, count_j, _ = usable[j]
        # Merge the smaller tag into the larger one.
        if count_j >= count_i:
            source, target, note_count = name_i, name_j, count_i + count_j
        else:
            source, target, note_count = name_j, name_i, count_i + count_j

        proposals.append(
            {
                "type": "proposal",
                "action": "merge_tags",
                "source_tag": source,
                "target_tag": target,
                "note_count": note_count,
                "confidence": round(sim, 2),
                "message": f"Merge '{source}' into '{target}' ({note_count} notes)",
            }
        )
    return proposals


def review_assignment_proposals(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Review-queue proposals for low-confidence note-to-tag assignments.

    Each item must have ``note_id`` and ``tag``; ``confidence`` and ``title`` are
    optional. Items missing a note id or tag are skipped.
    """
    proposals: List[Dict[str, Any]] = []
    for item in items:
        note_id = item.get("note_id")
        tag = item.get("tag")
        if not note_id or not tag:
            continue
        confidence = float(item.get("confidence", 0.0))
        title = item.get("title") or note_id
        proposals.append(
            {
                "type": "proposal",
                "action": "assign_tag",
                "note_id": note_id,
                "tag": tag,
                "note_title": item.get("title", ""),
                "confidence": round(confidence, 2),
                "message": f"Assign tag '{tag}' to note '{title}' (confidence: {confidence:.2f})",
            }
        )
    return proposals
