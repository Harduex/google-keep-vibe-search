import re
from typing import Any, Dict, List, Tuple


def extract_citations(
    response_text: str, context_notes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
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


CITE_RE = re.compile(r"\[Note #(\d+)\]")


def verify_citations(text: str, retrieved_count: int) -> Tuple[str, List[int], List[int]]:
    """Verify citations in text against retrieved_count. Strips invalid citations."""
    cited = sorted({int(m) for m in CITE_RE.findall(text)})
    valid = [i for i in cited if 1 <= i <= retrieved_count]
    invalid = [i for i in cited if i not in valid]
    for i in invalid:
        text = text.replace(f"[Note #{i}]", "")
    return text, valid, invalid
