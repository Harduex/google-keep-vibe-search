import re
from typing import Any, Dict, List


def extract_citations(response_text: str, context_notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
