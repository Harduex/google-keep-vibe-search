"""Property tests for the pure functions in ``app.domain.model``.

All data is synthetic — generated inline from random strings. No real notes,
no real export files, no fixtures that could leak corpus content.
"""

from __future__ import annotations

import random
import string

from app.domain import ChangeSet, Document, SourceDoc, content_hash, stable_id


def _rand_str(n: int = 32, seed: int | None = None) -> str:
    rng = random.Random(seed) if seed is not None else random.Random()
    alphabet = string.ascii_letters + string.digits + "  \n\t-_/&"
    return "".join(rng.choice(alphabet) for _ in range(n))


# --------------------------------------------------------------------------- #
# stable_id
# --------------------------------------------------------------------------- #


def test_stable_id_is_deterministic():
    """Same inputs must yield the same id on every call."""
    assert stable_id("keep", "note-1.json") == stable_id("keep", "note-1.json")


def test_stable_id_has_source_key_prefix():
    """The source_key namespace must be a visible prefix separated by ':'."""
    sid = stable_id("obsidian-main", "vault/inbox.md")
    assert sid.startswith("obsidian-main:")
    # 16 hex chars after the prefix
    assert len(sid.split(":", 1)[1]) == 16


def test_stable_id_differs_for_different_external_ids():
    """The whole point of A5: identity must not collapse across notes."""
    a = stable_id("keep", "note-1.json")
    b = stable_id("keep", "note-2.json")
    assert a != b


def test_stable_id_namespaces_by_source_key():
    """Same external_id in two sources must be two different documents."""
    assert stable_id("keep", "x") != stable_id("obsidian-main", "x")


def test_stable_id_collision_resistance_on_corpus():
    """Across a synthetic corpus of plausible size, no two distinct
    (source_key, external_id) pairs may collide.

    16 hex chars = 64 bits of blake2s output — collisions are astronomically
    unlikely for a few thousand inputs; this asserts it concretely.
    """
    rng = random.Random(20260725)
    sources = ["keep", "obsidian-main", "md-vault", "jsonl-export"]
    seen: set[str] = set()
    n = 5000
    for _ in range(n):
        sk = rng.choice(sources)
        ext = _rand_str(n=rng.randint(1, 64), seed=rng.randint(0, 10**9))
        sid = stable_id(sk, ext)
        # determinism spot-check: recompute and compare
        assert stable_id(sk, ext) == sid
        seen.add(sid)
    # All n inputs had distinct (sk, ext) pairs? No — ext can collide across
    # sources or repeat, so we instead assert uniqueness within source+ext.
    # Recompute over distinct (sk, ext) pairs and assert no collisions.
    distinct: set[tuple[str, str]] = set()
    while len(distinct) < n:
        distinct.add((rng.choice(sources), _rand_str(48, seed=rng.randint(0, 10**9))))
    ids = {stable_id(sk, ext) for sk, ext in distinct}
    assert len(ids) == len(distinct), "stable_id collisions on distinct inputs"


def test_stable_id_handles_unicode_external_id():
    """Non-ASCII paths must not raise and must still be deterministic."""
    sid_a = stable_id("keep", "Тест/Заметка.json")
    sid_b = stable_id("keep", "Тест/Заметка.json")
    assert sid_a == sid_b
    assert sid_a.startswith("keep:")


# --------------------------------------------------------------------------- #
# content_hash
# --------------------------------------------------------------------------- #


def test_content_hash_is_deterministic():
    assert content_hash("Title", "Body") == content_hash("Title", "Body")


def test_content_hash_differs_when_body_differs():
    assert content_hash("Title", "body one") != content_hash("Title", "body two")


def test_content_hash_differs_when_title_differs():
    assert content_hash("A", "same body") != content_hash("B", "same body")


def test_content_hash_title_and_body_are_delimited():
    """The newline delimiter must be unambiguous: a title that swallows part
    of what was the body must still produce a different hash."""
    assert content_hash("AB", "C") != content_hash("A", "BC")


def test_content_hash_collision_resistance_on_corpus():
    rng = random.Random(0xC0FFEE)
    seen: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    while len(pairs) < 5000:
        title = _rand_str(rng.randint(0, 40), seed=rng.randint(0, 10**9))
        body = _rand_str(rng.randint(0, 256), seed=rng.randint(0, 10**9))
        pairs.add((title, body))
    for title, body in pairs:
        seen.add(content_hash(title, body))
    assert len(seen) == len(pairs), "content_hash collisions on distinct inputs"


# --------------------------------------------------------------------------- #
# dataclass shape & ChangeSet
# --------------------------------------------------------------------------- #


def test_source_doc_is_frozen():
    doc = SourceDoc(external_id="x", title="t", body="b")
    import pytest

    with pytest.raises(Exception):
        doc.title = "mutated"  # type: ignore[misc]


def test_document_inherits_source_doc_fields():
    d = Document(
        external_id="x",
        title="t",
        body="b",
        id=stable_id("keep", "x"),
        source_key="keep",
        content_hash=content_hash("t", "b"),
    )
    assert d.external_id == "x"
    assert d.id.startswith("keep:")
    assert d.deleted_at is None


def test_changeset_default_buckets_are_independent_lists():
    cs = ChangeSet()
    cs.added.append(Document(external_id="x", title="t", body="b"))
    # default factories must give each instance its own list
    cs2 = ChangeSet()
    assert cs2.added == []
    assert cs.added  # mutation did not leak
