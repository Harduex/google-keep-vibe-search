from typing import Any, Dict, List, Tuple


def generate_synthetic_notes() -> List[Tuple[str, Dict[str, Any]]]:
    """Generate exactly 30 deterministic synthetic Google Keep notes."""
    notes = []
    base_time = 1700000000000000

    def _make_note(
        id_num: int,
        title: str,
        textContent: str = "",
        listContent: List[Dict[str, Any]] = None,
        **kwargs,
    ) -> Tuple[str, Dict[str, Any]]:
        note = {
            "title": title,
            "textContent": textContent,
            "createdTimestampUsec": base_time + (id_num * 1000000000),
            "userEditedTimestampUsec": base_time + (id_num * 1000000000),
            "isArchived": False,
            "isPinned": False,
            "isTrashed": False,
            "color": "DEFAULT",
        }
        if listContent is not None:
            note["listContent"] = listContent
        note.update(kwargs)
        return f"note_{id_num:02d}.json", note

    # 1-5: Checkbox notes (listContent only) - B3
    for i in range(1, 6):
        notes.append(
            _make_note(
                i,
                f"Checklist {i}",
                listContent=[{"text": f"Item {j}", "isChecked": j % 2 == 0} for j in range(3)],
            )
        )

    # 6-8: Notes carrying labels - B3b
    for i in range(6, 9):
        notes.append(
            _make_note(
                i, f"Labeled {i}", textContent="Content with label", labels=[{"name": f"Label{i}"}]
            )
        )

    # 9-14: Bulgarian notes
    bg_texts = [
        "Здравей, свят! Това е тестов бележник.",
        "Купи мляко, хляб и сирене от магазина.",
        "Среща с екипа утре в 10 часа.",
        "Не забравяй да платиш сметката за ток.",
        "Резервация за ресторант в събота.",
        "Проектът трябва да бъде завършен до петък.",
    ]
    for i in range(9, 15):
        notes.append(_make_note(i, f"БГ {i}", textContent=bg_texts[i - 9]))

    # 15: Mixed BG/EN note
    notes.append(
        _make_note(
            15, "Mixed Language", textContent="Това е български text mixed with English words."
        )
    )

    # 16: > 2000 chars note (for ChunkingService)
    long_text = "This is a very long text to test chunking. " * 100  # ~4300 chars
    notes.append(_make_note(16, "Long Note", textContent=long_text))

    # 17-18: Near-duplicate notes (conflict detection)
    notes.append(
        _make_note(
            17,
            "Duplicate A",
            textContent="The quick brown fox jumps over the lazy dog. Important project update.",
        )
    )
    notes.append(
        _make_note(
            18,
            "Duplicate B",
            textContent="The quick brown fox jumps over the lazy dog. Important project update!",
        )
    )

    # 19-20: Notes with named entities (EntityService)
    notes.append(
        _make_note(
            19, "Tech News", textContent="Tim Cook announced new Apple products in California."
        )
    )
    notes.append(
        _make_note(20, "Travel Plan", textContent="Visiting the Eiffel Tower in Paris, France.")
    )

    # 21: Archived
    notes.append(_make_note(21, "Archived Note", textContent="This is archived.", isArchived=True))

    # 22: Pinned
    notes.append(_make_note(22, "Pinned Note", textContent="This is pinned.", isPinned=True))

    # 23: Trashed (must be skipped)
    notes.append(_make_note(23, "Trashed Note", textContent="This is trashed.", isTrashed=True))

    # 24: Malformed note (missing fields, but will be parsed safely)
    malformed = _make_note(24, "")
    malformed[1].pop("textContent")  # completely missing textContent
    notes.append(malformed)

    # 25: Note with an image attachment
    notes.append(
        _make_note(
            25,
            "Image Note",
            textContent="Look at this picture.",
            attachments=[{"filePath": "fake_image.jpg", "mimetype": "image/jpeg"}],
        )
    )

    # 26-30: Standard notes
    for i in range(26, 31):
        notes.append(
            _make_note(
                i, f"Standard Note {i}", textContent=f"Just some regular content for note {i}."
            )
        )

    return notes
