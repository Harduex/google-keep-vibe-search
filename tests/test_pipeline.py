import os
import numpy as np

from app.services.note_service import NoteService
from app.services.tagging import pipeline
from app.services.tagging.pipeline import run_tagging_pipeline


def test_tagging_pipeline_full_and_incremental(tmp_path, monkeypatch):
    test_manifest_path = os.path.join(str(tmp_path), "tag_manifest.json")
    test_embed_cache = os.path.join(str(tmp_path), "tag_embeddings.json")
    monkeypatch.setattr(pipeline, "TAG_MANIFEST_PATH", test_manifest_path)
    monkeypatch.setattr("app.services.tagging.embed.TAG_EMBED_CACHE", test_embed_cache)

    # Stub naming to avoid calling external LLM in test
    def stub_name_clusters(clusters):
        for i, c in enumerate(clusters):
            if not c.get("reused_tag"):
                c["name"] = f"topic {i + 1}"
        return clusters

    monkeypatch.setattr("app.services.tagging.pipeline.name_clusters_sequential", stub_name_clusters)
    monkeypatch.setattr("app.services.tagging.pipeline.adjudicate_gray_pairs", lambda gray: [])

    # Setup dummy note_service
    ns = NoteService()
    dummy_notes = [
        {"id": f"note_{i}", "title": f"Note {i}", "content": f"Content for note {i} python programming"}
        for i in range(25)
    ]
    ns.notes = dummy_notes
    monkeypatch.setattr(ns, "load_notes", lambda force_refresh=False: ns.notes)

    # (1) Full run clean
    res1 = run_tagging_pipeline(ns, incremental=False)
    assert res1["status"] == "success"
    assert res1["mode"] == "full"
    assert os.path.exists(test_manifest_path)

    # (2) Immediate second full run: >=95% of notes keep primary tag
    res2 = run_tagging_pipeline(ns, incremental=False)
    assert res2["status"] == "success"
    tags_run1 = [a["primary"] for a in res1["assignments"]]
    tags_run2 = [a["primary"] for a in res2["assignments"]]
    matching_count = sum(1 for t1, t2 in zip(tags_run1, tags_run2) if t1 == t2)
    matching_pct = matching_count / len(tags_run1)
    assert matching_pct >= 0.95, f"Tag stability {matching_pct * 100}% was below 95%"

    # (3) One new note + incremental: correct existing tag, zero LLM calls
    llm_called = False

    def spy_llm_call(clusters):
        nonlocal llm_called
        llm_called = True
        return clusters

    monkeypatch.setattr("app.services.tagging.pipeline.name_clusters_sequential", spy_llm_call)

    new_note = {"id": "note_new", "title": "New Python Note", "content": "Learning python programming"}
    ns.notes.append(new_note)

    res3 = run_tagging_pipeline(ns, incremental=True)
    assert res3["status"] == "success"
    assert res3["mode"] == "incremental"
    assert llm_called is False, "LLM was called during incremental mode!"
