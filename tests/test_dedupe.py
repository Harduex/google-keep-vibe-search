from app.services.tagging.dedupe import deduplicate_tags


def test_deduplicate_tags_synthetic():
    tag_counts = {
        "keyboards": 5,
        "keyboard": 10,
        "mechanical keyboards": 8,
        "cooking": 12,
    }

    mapping, gray_pairs = deduplicate_tags(tag_counts)

    # First two auto-merged via plural rule / high similarity
    assert mapping["keyboards"] == "keyboard"
    assert mapping["keyboard"] == "keyboard"

    # 'cooking' untouched
    assert mapping["cooking"] == "cooking"

    # 'mechanical keyboards' and 'keyboard' in gray_pairs
    gray_tag_pairs = [
        set([g["tag1"], g["tag2"]]) for g in gray_pairs
    ]
    assert {"keyboard", "mechanical keyboards"} in gray_tag_pairs or {"keyboards", "mechanical keyboards"} in gray_tag_pairs
