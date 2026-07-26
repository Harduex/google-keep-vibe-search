"""Applying tag proposals must not be quadratic, or rewrite the tag file per action.

Reported as "the apply button spins forever". It was not hung — it finished after
minutes. Two costs, both proportional to the whole corpus rather than to the work
being asked for:

* ``_resolve_note_id`` scanned every note to resolve one id, and ``tag_notes``
  called it once per id. Applying a vocabulary that covers the corpus was therefore
  O(notes x ids): ~5s of pure scanning at 15,380 notes, ~11s when ids miss (no
  early exit).
* ``save_tags_to_cache`` ran once per action, each time serialising the entire
  tag map and copying the previous file to ``.bak``. 264 proposals meant 264 full
  rewrites of a 3.1 MB file.

These assert on operation counts, not wall-clock, so they cannot go flaky on a
loaded machine or a spinning disk.
"""

from typing import Any, Dict, List

import pytest

from app.services import note_service as ns_module
from app.services.note_service import NoteService


@pytest.fixture
def counting_save(monkeypatch):
    """Count full tag-file writes without performing any."""
    calls: List[int] = []

    def fake_save(tags: Dict[str, List[str]]) -> None:
        calls.append(len(tags))

    monkeypatch.setattr(ns_module, "save_tags_to_cache", fake_save)
    return calls


def _service(n: int) -> NoteService:
    svc = NoteService()
    svc.notes = [{"id": f"id{i}", "external_id": f"ext{i}.json"} for i in range(n)]
    svc.note_tags = {}
    svc.excluded_tags = set()
    return svc


class TestIdResolutionIsIndexed:
    def test_resolving_every_id_does_not_rescan_the_corpus(self):
        # A scan-per-id is O(n^2); an index makes the whole pass O(n). Assert on
        # comparisons rather than seconds: count how many notes get inspected.
        svc = _service(500)
        inspected = 0

        class CountingNote(dict):
            def get(self, key, default=None):
                nonlocal inspected
                if key in ("id", "external_id"):
                    inspected += 1
                return super().get(key, default)

        svc.notes = [CountingNote(n) for n in svc.notes]
        for i in range(500):
            assert svc._resolve_note_id(f"id{i}") == f"id{i}"

        # Indexed: each note is inspected a small constant number of times while the
        # index is built, then never again. Unindexed this is ~250,000.
        assert inspected < 500 * 6, f"{inspected} inspections — id resolution is still scanning"

    def test_resolves_by_external_id_too(self):
        svc = _service(10)
        assert svc._resolve_note_id("ext7.json") == "id7"

    def test_a_missing_id_still_reports_none(self):
        svc = _service(10)
        assert svc._resolve_note_id("nope") is None

    def test_the_index_notices_when_the_notes_change(self):
        # The dangerous half of any cache. A reload must not leave stale ids
        # resolving, or tags land on the wrong notes.
        svc = _service(5)
        assert svc._resolve_note_id("id3") == "id3"

        svc.notes = [{"id": "new1", "external_id": "new1.json"}]
        assert svc._resolve_note_id("id3") is None
        assert svc._resolve_note_id("new1") == "new1"


class TestOneWritePerApply:
    def test_tag_notes_can_defer_persistence(self, counting_save):
        svc = _service(100)
        svc.tag_notes([f"id{i}" for i in range(50)], "Recipes", save=False)

        assert counting_save == [], "save=False must not touch disk"
        assert svc.note_tags["id0"] == ["Recipes"]

    def test_tag_notes_still_persists_by_default(self, counting_save):
        svc = _service(10)
        svc.tag_notes(["id1"], "Recipes")
        assert len(counting_save) == 1

    def test_persist_tags_writes_once(self, counting_save):
        svc = _service(10)
        svc.tag_notes(["id1"], "A", save=False)
        svc.tag_notes(["id2"], "B", save=False)
        svc.tag_notes(["id3"], "C", save=False)
        svc.persist_tags()

        assert len(counting_save) == 1, "three actions must cost one write, not three"

    def test_invalid_ids_still_raise_before_anything_is_written(self, counting_save):
        svc = _service(10)
        with pytest.raises(ValueError):
            svc.tag_notes(["id1", "ghost"], "Recipes")
        assert counting_save == [], "a rejected call must not half-write the tag map"


class TestApplyRouteWritesOnce:
    def test_many_actions_cost_one_write(self, counting_save, monkeypatch):
        from app.models.organize import ApplyProposalsRequest
        from app.routes.organize import apply_proposals

        svc = _service(300)
        monkeypatch.setattr("app.routes.organize.clear_pending_proposals", lambda: None)

        actions: List[Dict[str, Any]] = [
            {
                "action": "approve",
                "tag_name": f"Tag {a}",
                "note_ids": [f"id{a * 10 + j}" for j in range(10)],
            }
            for a in range(20)
        ]
        result = apply_proposals(ApplyProposalsRequest(actions=actions), note_service=svc)

        assert result["notes_tagged"] == 200
        assert len(counting_save) == 1, f"{len(counting_save)} writes for 20 actions"
