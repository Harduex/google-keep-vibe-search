import re
from typing import Any, Dict, List


def extract_citations(response_text: str, context_notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract legacy [Note #N] citations from response text."""
    pattern = r"\[Note #(\d+)(?:,\s*#(\d+))*\]"
    citations = []
    seen = set()

    for match in re.finditer(pattern, response_text):
        note_nums = [int(n) for n in re.findall(r"#(\d+)", match.group())]
        for num in note_nums:
            if 1 <= num <= len(context_notes) and num not in seen:
                note = context_notes[num - 1]
                citations.append(
                    {
                        "note_number": num,
                        "note_id": note.get("id", ""),
                        "note_title": note.get("title", ""),
                    }
                )
                seen.add(num)

    return citations


def extract_grounded_citations(
    response_text: str,
    context_items: List[Any],
) -> List[Dict[str, Any]]:
    """Extract [citation:CITATION_ID] markers from response text.

    Falls back to legacy [Note #N] parsing if no grounded citations found.

    Parameters
    ----------
    response_text:
        The LLM response text containing [citation:ID] markers.
    context_items:
        List of GroundedContext objects or dicts with citation_id, note_id, etc.

    Returns
    -------
    List of citation dicts with citation_id, note_id, note_title,
    start_char_idx, end_char_idx, and text_snippet.
    """
    # Build lookup from citation_id to context item
    context_map: Dict[str, Any] = {}
    for item in context_items:
        if hasattr(item, "citation_id"):
            cid = item.citation_id
            context_map[cid] = item
        elif isinstance(item, dict):
            cid = item.get("citation_id", "")
            if cid:
                context_map[cid] = item

    # Parse [citation:ID] markers
    pattern = r"\[citation:([^\]]+)\]"
    citations = []
    seen = set()

    for match in re.finditer(pattern, response_text):
        citation_id = match.group(1).strip()
        if citation_id in seen:
            continue
        seen.add(citation_id)

        if citation_id in context_map:
            item = context_map[citation_id]
            if hasattr(item, "note_id"):
                citations.append(
                    {
                        "citation_id": citation_id,
                        "note_id": item.note_id,
                        "note_title": item.note_title,
                        "start_char_idx": item.start_char_idx,
                        "end_char_idx": item.end_char_idx,
                        "text_snippet": (item.text[:200] + "...") if len(item.text) > 200 else item.text,
                    }
                )
            else:
                citations.append(
                    {
                        "citation_id": citation_id,
                        "note_id": item.get("note_id", ""),
                        "note_title": item.get("note_title", ""),
                        "start_char_idx": item.get("start_char_idx"),
                        "end_char_idx": item.get("end_char_idx"),
                        "text_snippet": item.get("text", "")[:200],
                    }
                )
        else:
            # Citation ID not found in context -- include with empty metadata
            citations.append(
                {
                    "citation_id": citation_id,
                    "note_id": "",
                    "note_title": "",
                    "start_char_idx": None,
                    "end_char_idx": None,
                    "text_snippet": "",
                }
            )

    # Fallback: if no [citation:...] found, try legacy [Note #N]
    if not citations and context_items:
        legacy_notes = []
        for item in context_items:
            if hasattr(item, "note_id"):
                legacy_notes.append({"id": item.note_id, "title": item.note_title})
            elif isinstance(item, dict):
                legacy_notes.append({
                    "id": item.get("note_id", item.get("id", "")),
                    "title": item.get("note_title", item.get("title", "")),
                })
        legacy = extract_citations(response_text, legacy_notes)
        for lc in legacy:
            citations.append(
                {
                    "citation_id": lc.get("note_id", ""),
                    "note_id": lc.get("note_id", ""),
                    "note_title": lc.get("note_title", ""),
                    "start_char_idx": None,
                    "end_char_idx": None,
                    "text_snippet": "",
                }
            )

    return citations
