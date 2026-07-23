from app.services.tagging.naming import (
    BANNED_TAGS,
    clean_and_normalize_tag,
    name_clusters_sequential,
    name_single_cluster,
    validate_tag,
)


def test_validate_tag_rules():
    assert validate_tag("mechanical keyboards") is True
    assert validate_tag("3d printing") is True
    assert validate_tag("recipe & cooking") is True

    # Invalid cases
    assert validate_tag("misc") is False
    assert validate_tag("notes") is False
    assert validate_tag("general") is False
    assert validate_tag("too many words in this tag label") is False
    assert validate_tag("invalid!punctuation?") is False
    assert validate_tag("") is False


def test_clean_and_normalize_tag():
    assert clean_and_normalize_tag('"Mechanical Keyboards."') == "mechanical keyboards"
    assert clean_and_normalize_tag("  Python Programming. ") == "python programming"


def test_naming_fallback_on_invalid_output(monkeypatch):
    # Stub model factory or agent run_sync to simulate invalid LLM response
    def stub_name_single(keywords, samples_text, existing_tags):
        # Emulate fallback when LLM fails validation
        fallback = " ".join(keywords[:2])
        cleaned = clean_and_normalize_tag(fallback)
        return cleaned if validate_tag(cleaned) else "topics"

    monkeypatch.setattr("app.services.tagging.naming.name_single_cluster", stub_name_single)

    clusters = [
        {"size": 15, "keywords": ["python", "async", "tutorial"], "samples_text": "sample 1"},
        {"size": 30, "keywords": ["keyboard", "switches", "keycaps"], "samples_text": "sample 2"},
    ]

    named = name_clusters_sequential(clusters)

    # Size DESC order check: 30-sized cluster first, 15-sized cluster second
    assert named[0]["size"] == 30
    assert named[0]["name"] == "keyboard switches"
    assert named[1]["size"] == 15
    assert named[1]["name"] == "python async"

    # All tags pass validation and zero banned tags
    for c in named:
        assert validate_tag(c["name"]) is True
        assert c["name"] not in BANNED_TAGS
