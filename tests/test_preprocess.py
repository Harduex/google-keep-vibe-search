from app.services.tagging.preprocess import clean_note


def test_clean_note_removes_artifacts_and_preserves_words():
    raw_markdown = (
        "---\n"
        "layout: note\n"
        "title: Frontmatter Title\n"
        "---\n"
        "# Heading 1\n"
        "Here is a note with a [markdown link](https://example.com/page) and a standalone URL https://openai.com.\n"
        "Also includes a code block:\n"
        "```python\n"
        "def secret_code_block():\n"
        "    return 'should_be_removed'\n"
        "```\n"
        "and *bold* or `inline_code` syntax."
    )

    cleaned = clean_note(raw_markdown)

    # Output contains none of those artifacts
    assert "https://example.com/page" not in cleaned
    assert "https://openai.com" not in cleaned
    assert "secret_code_block" not in cleaned
    assert "should_be_removed" not in cleaned
    assert "---" not in cleaned
    assert "#" not in cleaned
    assert "*" not in cleaned
    assert "`" not in cleaned

    # Normal words preserved
    assert "Here is a note with a" in cleaned
    assert "markdown link" in cleaned
    assert "standalone URL" in cleaned
    assert "Also includes a code block" in cleaned
    assert "bold" in cleaned
    assert "inline code syntax" in cleaned or "inline" in cleaned


def test_clean_note_empty_and_plain():
    assert clean_note("") == ""
    assert clean_note("Plain text note without markdown") == "Plain text note without markdown"
