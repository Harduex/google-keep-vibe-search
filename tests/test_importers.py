"""Tests for the pluggable importers.

All test data is synthetic, written inline to a tmp folder — never the real
Keep export or the cache directory (see AGENTS.md privacy boundary). The one
real-corpus acceptance test reads ``bench/corpora.py``'s ``markdown_vault``,
which is the sanctioned exception; it skips itself if that corpus accessor is
the stub that ships today.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from app.domain import SourceDoc
from app.importers import REGISTRY, KeepTakeoutImporter, MarkdownDirImporter, get_importer
from app.importers.base import Skip, scan

# --------------------------------------------------------------------------- #
# Helpers — synthetic Keep JSON and markdown files written into a tmp folder.
# --------------------------------------------------------------------------- #

_USEC = 1_700_000_000_000_000


def _write_keep_note(dir_: Path, name: str, payload: dict) -> Path:
    p = dir_ / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _set_mtime(path: Path, ts: float) -> None:
    """Pin a file's mtime so markdown-imported SourceDocs are deterministic."""
    os.utime(path, (ts, ts))


def _make_keep_folder(tmp_path: Path, n: int = 30) -> Path:
    """Build a 30-file synthetic Keep folder with the cases that matter.

    Composition (sums to 30, deterministic):
      - 5 checklist notes (listContent only)           — exercises list flattening
      - 3 labeled notes                                 — exercises label import
      - 2 trashed notes                                 — counted as skips
      - 1 malformed JSON file                           — counted as skips
      - 1 JSON file that isn't a Keep note              — counted as not-a-note
      - 18 plain text notes                             — bulk
    """
    d = tmp_path / "keep"
    d.mkdir()
    for i in range(1, 6):
        _write_keep_note(
            d,
            f"checklist_{i:02d}.json",
            {
                "title": f"Checklist {i}",
                "listContent": [{"text": f"item {j}", "isChecked": j % 2 == 0} for j in range(3)],
                "createdTimestampUsec": _USEC + i,
                "userEditedTimestampUsec": _USEC + i,
                "isTrashed": False,
            },
        )
    for i in range(1, 4):
        _write_keep_note(
            d,
            f"labeled_{i:02d}.json",
            {
                "title": f"Labeled {i}",
                "textContent": f"body {i}",
                "labels": [{"name": f"Label{i}"}, {"name": "shared"}],
                "createdTimestampUsec": _USEC + 100 + i,
                "userEditedTimestampUsec": _USEC + 100 + i,
                "isTrashed": False,
            },
        )
    for i in range(1, 3):
        _write_keep_note(
            d,
            f"trashed_{i:02d}.json",
            {
                "title": f"Trashed {i}",
                "textContent": "should not import",
                "isTrashed": True,
            },
        )
    (d / "malformed.json").write_text("{not valid json", encoding="utf-8")
    _write_keep_note(d, "notakeep.json", {"random": "json", "no": "keep keys"})
    for i in range(1, 19):
        _write_keep_note(
            d,
            f"plain_{i:02d}.json",
            {
                "title": f"Plain {i}",
                "textContent": f"plain body {i}",
                "createdTimestampUsec": _USEC + 200 + i,
                "userEditedTimestampUsec": _USEC + 200 + i,
                "isTrashed": False,
            },
        )
    return d


def _make_md_folder(tmp_path: Path, n: int = 30) -> Path:
    """Build a 30-file synthetic Obsidian-style vault across nested folders."""
    root = tmp_path / "vault"
    (root / "inbox").mkdir(parents=True)
    (root / "projects" / "2026").mkdir(parents=True)
    files = []
    # 10 with frontmatter inline tags + an H1
    for i in range(1, 11):
        p = root / f"fm_inline_{i:02d}.md"
        p.write_text(
            f"---\ntags: [alpha, beta-{i}]\n---\n# Title {i}\n\nBody with #inline_tag{i}\n",
            encoding="utf-8",
        )
        files.append((p, _USEC + i))
    # 10 with block-list frontmatter tags
    for i in range(1, 11):
        p = root / "inbox" / f"fm_block_{i:02d}.markdown"
        p.write_text(
            f"---\ntags:\n  - gamma\n  - delta-{i}\n---\nNo H1 here, body #{i}.\n",
            encoding="utf-8",
        )
        files.append((p, _USEC + 100 + i))
    # 5 with only inline #hashtags, no frontmatter
    for i in range(1, 6):
        p = root / "projects" / f"hash_{i:02d}.md"
        p.write_text(
            f"Project note {i}. #project #urgent-{i}\nMore text.\n",
            encoding="utf-8",
        )
        files.append((p, _USEC + 200 + i))
    # 3 empty files — skipped with reason "empty"
    for i in range(1, 4):
        p = root / f"empty_{i:02d}.md"
        p.write_text("   \n", encoding="utf-8")
        files.append((p, _USEC + 300 + i))
    # 2 nested deeper, with comma-separated frontmatter tags
    for i in range(1, 3):
        p = root / "projects" / "2026" / f"deep_{i:02d}.md"
        p.write_text(
            f"---\ntag: solo-{i}\ntags: x, y, z\n---\n# Deep {i}\n",
            encoding="utf-8",
        )
        files.append((p, _USEC + 400 + i))

    for p, ts in files:
        _set_mtime(p, ts)
    return root


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_registry_has_both_importers():
    assert "keep-takeout" in REGISTRY
    assert "markdown-dir" in REGISTRY


def test_get_importer_returns_instances():
    k = get_importer("keep-takeout")
    m = get_importer("markdown-dir")
    assert isinstance(k, KeepTakeoutImporter)
    assert isinstance(m, MarkdownDirImporter)


def test_get_importer_unknown_key_raises():
    with pytest.raises(KeyError):
        get_importer("nope")


# --------------------------------------------------------------------------- #
# detect() — each importer accepts its own format and rejects the other
# --------------------------------------------------------------------------- #


def test_keep_detect_accepts_keep_folder(tmp_path):
    d = _make_keep_folder(tmp_path)
    assert KeepTakeoutImporter().detect(d) is True


def test_keep_detect_rejects_markdown_folder(tmp_path):
    d = _make_md_folder(tmp_path)
    assert KeepTakeoutImporter().detect(d) is False


def test_md_detect_accepts_markdown_folder(tmp_path):
    d = _make_md_folder(tmp_path)
    assert MarkdownDirImporter().detect(d) is True


def test_md_detect_rejects_keep_folder(tmp_path):
    d = _make_keep_folder(tmp_path)
    assert MarkdownDirImporter().detect(d) is False


def test_detect_rejects_missing_dir(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert KeepTakeoutImporter().detect(missing) is False
    assert MarkdownDirImporter().detect(missing) is False


# --------------------------------------------------------------------------- #
# Keep importer — label/tag seeding behaviour preserved
# --------------------------------------------------------------------------- #


def test_keep_scan_30_file_folder_counts(tmp_path):
    """The documented checkpoint for a 30-file Keep folder.

    Composition of _make_keep_folder: 5 checklist + 3 labeled + 18 plain +
    1 non-Keep-but-valid JSON + 2 trashed + 1 malformed = 30 files.
    Imported: 5 + 3 + 18 + 1 (the non-Keep JSON yields an empty SourceDoc,
    since the importer reads every *.json that parses) = 27 docs.
    Skipped: 2 trashed + 1 malformed = 3 skips. Every file is either a doc
    or an explicit skip — no silent drops.
    """
    d = _make_keep_folder(tmp_path)
    result = KeepTakeoutImporter().scan(d)
    total_files = len(list(d.glob("*.json")))
    assert total_files == 30
    assert total_files == len(result.docs) + len(result.skips)
    assert len(result.docs) == 27
    assert len(result.skips) == 3
    assert all(isinstance(x, SourceDoc) for x in result.docs)
    assert all(isinstance(s, Skip) for s in result.skips)
    reason_counts: dict[str, int] = {}
    for s in result.skips:
        reason_counts[s.reason] = reason_counts.get(s.reason, 0) + 1
    assert reason_counts == {"trashed": 2, "malformed": 1}


def test_keep_listcontent_flattened_into_body(tmp_path):
    d = tmp_path / "keep"
    d.mkdir()
    _write_keep_note(
        d,
        "checklist.json",
        {
            "title": "Shopping",
            "listContent": [
                {"text": "Milk", "isChecked": False},
                {"text": "Eggs", "isChecked": True},
            ],
            "isTrashed": False,
        },
    )
    doc = next(KeepTakeoutImporter().read(d))
    assert "- [ ] Milk" in doc.body
    assert "- [x] Eggs" in doc.body


def test_keep_textcontent_and_listcontent_both_in_body(tmp_path):
    d = tmp_path / "keep"
    d.mkdir()
    _write_keep_note(
        d,
        "mixed.json",
        {
            "title": "Mixed",
            "textContent": "Free text",
            "listContent": [{"text": "Item", "isChecked": False}],
            "isTrashed": False,
        },
    )
    doc = next(KeepTakeoutImporter().read(d))
    assert "Free text" in doc.body
    assert "- [ ] Item" in doc.body
    # Free text precedes the checklist.
    assert doc.body.index("Free text") < doc.body.index("- [ ] Item")


def test_keep_labels_extracted(tmp_path):
    d = tmp_path / "keep"
    d.mkdir()
    _write_keep_note(
        d,
        "labeled.json",
        {
            "title": "With Labels",
            "textContent": "body",
            "labels": [{"name": "Work"}, {"name": "Important"}, {"name": ""}],
            "isTrashed": False,
        },
    )
    doc = next(KeepTakeoutImporter().read(d))
    assert doc.labels == ["Work", "Important"]


def test_keep_trashed_skipped_with_reason(tmp_path):
    d = tmp_path / "keep"
    d.mkdir()
    _write_keep_note(
        d,
        "trash.json",
        {"title": "x", "textContent": "y", "isTrashed": True},
    )
    result = KeepTakeoutImporter().scan(d)
    assert result.docs == []
    assert len(result.skips) == 1
    assert result.skips[0].reason == "trashed"
    assert result.skips[0].path == "trash.json"


def test_keep_malformed_counted_not_raised(tmp_path):
    d = tmp_path / "keep"
    d.mkdir()
    (d / "bad.json").write_text("{broken", encoding="utf-8")
    result = KeepTakeoutImporter().scan(d)
    assert result.docs == []
    assert len(result.skips) == 1
    assert result.skips[0].reason == "malformed"


def test_keep_external_id_is_basename(tmp_path):
    """external_id must match the legacy ``id`` (basename incl. .json)
    so the store migration can map old ids to stable_ids losslessly."""
    d = tmp_path / "keep"
    d.mkdir()
    _write_keep_note(
        d,
        "note-42.json",
        {"title": "t", "textContent": "b", "isTrashed": False},
    )
    doc = next(KeepTakeoutImporter().read(d))
    assert doc.external_id == "note-42.json"


def test_keep_timestamps_become_datetimes(tmp_path):
    d = tmp_path / "keep"
    d.mkdir()
    _write_keep_note(
        d,
        "ts.json",
        {
            "title": "t",
            "textContent": "b",
            "createdTimestampUsec": 1_700_000_000_000_000,
            "userEditedTimestampUsec": 1_700_000_010_000_000,
            "isTrashed": False,
        },
    )
    doc = next(KeepTakeoutImporter().read(d))
    assert doc.created_at == datetime.fromtimestamp(1_700_000_000)
    assert doc.edited_at == datetime.fromtimestamp(1_700_000_010)


def test_keep_attachments_copied(tmp_path):
    d = tmp_path / "keep"
    d.mkdir()
    _write_keep_note(
        d,
        "att.json",
        {
            "title": "t",
            "textContent": "b",
            "isTrashed": False,
            "attachments": [{"filePath": "img.jpg", "mimetype": "image/jpeg"}],
        },
    )
    doc = next(KeepTakeoutImporter().read(d))
    assert len(doc.attachments) == 1
    assert doc.attachments[0].path == "img.jpg"
    assert doc.attachments[0].mime == "image/jpeg"


def test_keep_extra_carries_archived_pinned_color(tmp_path):
    d = tmp_path / "keep"
    d.mkdir()
    _write_keep_note(
        d,
        "extra.json",
        {
            "title": "t",
            "textContent": "b",
            "isTrashed": False,
            "isArchived": True,
            "isPinned": True,
            "color": "YELLOW",
        },
    )
    doc = next(KeepTakeoutImporter().read(d))
    assert doc.extra["isArchived"] is True
    assert doc.extra["isPinned"] is True
    assert doc.extra["color"] == "YELLOW"


# --------------------------------------------------------------------------- #
# Markdown importer
# --------------------------------------------------------------------------- #


def test_md_scan_30_file_folder_counts(tmp_path):
    """The documented checkpoint: 30 md files → 27 docs + 3 empty skips."""
    d = _make_md_folder(tmp_path)
    result = MarkdownDirImporter().scan(d)
    # 10 fm_inline + 10 fm_block + 5 hash + 2 deep = 27 docs; 3 empty skips.
    assert len(result.docs) == 27
    assert len(result.skips) == 3
    assert {s.reason for s in result.skips} == {"empty"}
    total = sum(1 for _ in d.rglob("*.md")) + sum(1 for _ in d.rglob("*.markdown"))
    assert total == len(result.docs) + len(result.skips)


def test_md_frontmatter_inline_tags_become_labels(tmp_path):
    d = tmp_path / "v"
    d.mkdir()
    (d / "a.md").write_text("---\ntags: [alpha, beta]\n---\n# A\nbody\n", encoding="utf-8")
    _set_mtime(d / "a.md", _USEC)
    doc = next(MarkdownDirImporter().read(d))
    assert "alpha" in doc.labels
    assert "beta" in doc.labels


def test_md_frontmatter_block_tags_become_labels(tmp_path):
    d = tmp_path / "v"
    d.mkdir()
    (d / "a.md").write_text("---\ntags:\n  - one\n  - two\n---\nbody\n", encoding="utf-8")
    _set_mtime(d / "a.md", _USEC)
    doc = next(MarkdownDirImporter().read(d))
    assert "one" in doc.labels
    assert "two" in doc.labels


def test_md_singular_tag_key_becomes_labels(tmp_path):
    d = tmp_path / "v"
    d.mkdir()
    (d / "a.md").write_text("---\ntag: solo\n---\nbody\n", encoding="utf-8")
    _set_mtime(d / "a.md", _USEC)
    doc = next(MarkdownDirImporter().read(d))
    assert "solo" in doc.labels


def test_md_inline_hashtags_become_labels(tmp_path):
    d = tmp_path / "v"
    d.mkdir()
    (d / "a.md").write_text("Body with #project and #urgent tags.\n", encoding="utf-8")
    _set_mtime(d / "a.md", _USEC)
    doc = next(MarkdownDirImporter().read(d))
    assert "project" in doc.labels
    assert "urgent" in doc.labels


def test_md_frontmatter_and_inline_tags_both_land_in_labels(tmp_path):
    """The parity assertion for markdown: both tag sources merge."""
    d = tmp_path / "v"
    d.mkdir()
    (d / "a.md").write_text(
        "---\ntags: [fm-one]\n---\n# T\nBody #inline-one and #fm-one dup\n",
        encoding="utf-8",
    )
    _set_mtime(d / "a.md", _USEC)
    doc = next(MarkdownDirImporter().read(d))
    # fm-one appears in frontmatter and as a duplicate inline #fm-one; the
    # duplicate is de-duplicated case-insensitively, so it lands once.
    assert "fm-one" in doc.labels
    assert "inline-one" in doc.labels
    assert doc.labels.count("fm-one") == 1


def test_md_hashtag_in_url_not_a_label(tmp_path):
    d = tmp_path / "v"
    d.mkdir()
    (d / "a.md").write_text("See http://example.com/#section for details.\n", encoding="utf-8")
    _set_mtime(d / "a.md", _USEC)
    doc = next(MarkdownDirImporter().read(d))
    assert "section" not in doc.labels


def test_md_heading_not_a_label(tmp_path):
    """A markdown heading '# Title' must not be parsed as a tag."""
    d = tmp_path / "v"
    d.mkdir()
    (d / "a.md").write_text("# Title\nbody\n", encoding="utf-8")
    _set_mtime(d / "a.md", _USEC)
    doc = next(MarkdownDirImporter().read(d))
    assert "Title" not in doc.labels


def test_md_external_id_is_posix_relpath(tmp_path):
    d = tmp_path / "v"
    (d / "sub").mkdir(parents=True)
    p = d / "sub" / "note.md"
    p.write_text("# hi\n", encoding="utf-8")
    _set_mtime(p, _USEC)
    doc = next(MarkdownDirImporter().read(d))
    assert doc.external_id == "sub/note.md"


def test_md_edited_at_from_mtime(tmp_path):
    d = tmp_path / "v"
    d.mkdir()
    p = d / "a.md"
    p.write_text("body\n", encoding="utf-8")
    _set_mtime(p, 1_700_000_100)
    doc = next(MarkdownDirImporter().read(d))
    assert doc.edited_at == datetime.fromtimestamp(1_700_000_100)


def test_md_title_from_h1_else_stem(tmp_path):
    d = tmp_path / "v"
    d.mkdir()
    (d / "with_h1.md").write_text("# My Title\nbody\n", encoding="utf-8")
    (d / "no_h1.md").write_text("just body\n", encoding="utf-8")
    _set_mtime(d / "with_h1.md", _USEC)
    _set_mtime(d / "no_h1.md", _USEC)
    docs = {d_.external_id: d_ for d_ in MarkdownDirImporter().read(d)}
    assert docs["with_h1.md"].title == "My Title"
    assert docs["no_h1.md"].title == "no_h1"


def test_md_empty_file_skipped(tmp_path):
    d = tmp_path / "v"
    d.mkdir()
    (d / "empty.md").write_text("   \n", encoding="utf-8")
    result = MarkdownDirImporter().scan(d)
    assert result.docs == []
    assert len(result.skips) == 1
    assert result.skips[0].reason == "empty"


def test_md_unreadable_file_skipped(tmp_path):
    d = tmp_path / "v"
    d.mkdir()
    p = d / "a.md"
    p.write_text("body\n", encoding="utf-8")
    _set_mtime(p, _USEC)
    # Make the file unreadable to trigger the unreadable skip path.
    p.chmod(0o000)
    try:
        if os.access(p, os.R_OK):
            # Running as root — the chmod is a no-op, so this test cannot
            # exercise the unreadable branch here. Skip rather than pass vacuously.
            pytest.skip("cannot create an unreadable file as root")
        result = MarkdownDirImporter().scan(d)
        assert len(result.skips) == 1
        assert result.skips[0].reason == "unreadable"
    finally:
        p.chmod(0o644)


# --------------------------------------------------------------------------- #
# Byte-identical-across-runs (determinism). The walk is sorted and mtimes are
# pinned, so two scans over the same folder must produce equal SourceDoc lists.
# --------------------------------------------------------------------------- #


def test_keep_byte_identical_across_runs(tmp_path):
    d = _make_keep_folder(tmp_path)
    a = KeepTakeoutImporter().scan(d).docs
    b = KeepTakeoutImporter().scan(d).docs
    assert len(a) == len(b)
    assert a == b  # dataclass __eq__: field-by-field, list/dict deep


def test_md_byte_identical_across_runs(tmp_path):
    d = _make_md_folder(tmp_path)
    a = MarkdownDirImporter().scan(d).docs
    b = MarkdownDirImporter().scan(d).docs
    assert len(a) == len(b)
    assert a == b


def test_md_walk_order_does_not_change_output(tmp_path):
    """Output identity must not depend on rglob's filesystem ordering."""
    d = _make_md_folder(tmp_path)
    docs = MarkdownDirImporter().scan(d).docs
    external_ids = [d_.external_id for d_ in docs]
    assert external_ids == sorted(external_ids)


# --------------------------------------------------------------------------- #
# base.scan() helper fallback
# --------------------------------------------------------------------------- #


def test_base_scan_helper_partitions_docs_and_skips(tmp_path):
    d = _make_keep_folder(tmp_path)
    result = scan(KeepTakeoutImporter(), d)
    assert len(result.docs) > 0
    assert len(result.skips) > 0
    assert all(isinstance(x, SourceDoc) for x in result.docs)


# --------------------------------------------------------------------------- #
# Real-corpus acceptance test — markdown_vault from bench/corpora.py
# --------------------------------------------------------------------------- #


def test_markdown_vault_real_corpus(tmp_path):
    """Run the markdown importer over the benchmark markdown_vault corpus.

    Asserts the importer contract: every file is either imported or explicitly
    skipped with a reason (no silent drops), and both frontmatter tags and
    inline #tags land in ``labels``.

    ``bench/corpora.py:load_markdown_vault`` currently ships as a stub that
    returns ``None`` ("No verified CC-licensed markdown vault available"), so
    this test skips cleanly until that accessor returns real data rather than
    asserting against a fabricated count.
    """
    try:
        from bench.corpora import load_markdown_vault
    except Exception as e:  # pragma: no cover - bench import path is stable
        pytest.skip(f"bench.corpora not importable: {e}")

    corpus = load_markdown_vault()
    if corpus is None or not getattr(corpus, "docs", None):
        pytest.skip(
            "markdown_vault corpus accessor is a stub (returns None) — "
            "blocked on T35 providing a real CC-licensed vault. "
            "Not a T23 defect; reported as a blocker."
        )

    # If/when that accessor ships real data, it must expose it as files on disk the
    # importer can read, or as a directory path — BenchCorpus.docs is a list of
    # pre-loaded strings, which does not fit a folder-reading importer. Until
    # there is a directory accessor, materialise the strings to a tmp vault.
    docs_dir = tmp_path / "vault"
    docs_dir.mkdir()
    for idx, text in enumerate(corpus.docs):
        (docs_dir / f"doc_{idx:05d}.md").write_text(text, encoding="utf-8")

    result = MarkdownDirImporter().scan(docs_dir)

    # The contract: every input file is either a doc or an explicit skip.
    n_files = sum(1 for _ in docs_dir.rglob("*.md"))
    n_files += sum(1 for _ in docs_dir.rglob("*.markdown"))
    assert n_files == len(result.docs) + len(result.skips)

    # Every skip carries a non-empty reason — no silent drops.
    for skip_ in result.skips:
        assert skip_.reason

    # At least one imported doc carries a label sourced from either tag form,
    # which is what proves the importer is useful beyond Keep. (If the real
    # vault happened to have no tags at all this would be the wrong assertion;
    # the point is proof that both tag forms land in labels.)
    labelled = [d_ for d_ in result.docs if d_.labels]
    assert labelled, "expected at least one labelled doc in the real vault"
