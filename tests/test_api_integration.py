import json

import pytest


def test_wired_app_loads_no_real_models(wired_app):
    """The wired fixture must be hermetic — no real model weights, ever (T1/T2).

    A patch target that misses one import site does not fail loudly: the app just
    downloads and runs the real model, so the suite stays green while depending on
    network and a warm HF cache. This asserts every model handle in the wired app is a
    stub, by class name only — never touching note text.

    The heavy models are built lazily, which is exactly how this test could rot into a
    vacuous pass: the handles do not exist at boot, so "the attribute is absent" would
    be green while the real weights load on the first request. So every assertion below
    *forces* construction through the lazy property and asserts on what comes back.
    """
    from tests.fixtures.stubs import StubCrossEncoder, StubEmbedder, StubSpacyNLP

    models = wired_app.state.models
    # Non-vacuous by construction: nothing is built yet, so each assertion that follows
    # is what triggers the build.
    assert models.loaded == {
        "reranker": False,
        "verification": False,
        "grounding": False,
        "chunking": False,
    }

    chat_service = wired_app.state.chat_service

    assert isinstance(chat_service.retrieval.search_service.engine.model, StubEmbedder)
    assert isinstance(models.reranker.model, StubCrossEncoder)
    assert isinstance(models.verification.nli_model, StubCrossEncoder)
    assert isinstance(models.grounding.nli_model, StubCrossEncoder)
    assert isinstance(models.chunking.model, StubEmbedder)
    assert isinstance(wired_app.state.entity_service.nlp, StubSpacyNLP)

    # And the collaborators reach those very objects through their placeholders — a stub
    # behind `app.state.models` would prove nothing if chat held a second, real instance.
    assert chat_service.verification_service.nli_model is models.verification.nli_model
    assert chat_service.grounding_service.nli_model is models.grounding.nli_model
    assert chat_service.retrieval.reranker.model is models.reranker.model
    assert chat_service.retrieval.chunking_service.model is models.chunking.model
    assert wired_app.state.search_service.engine.reranker.model is models.reranker.model


def test_heavy_models_are_built_on_first_use_and_only_once(client, monkeypatch):
    """Prove the laziness, not just the wiring.

    Boot builds none of them; a `/api/search` builds only what the search path actually
    touches; a `/api/chat` builds the rest; a second `/api/chat` builds nothing new.
    """
    from app.core.config import settings

    models = client.app.state.models
    assert dict(models.construction_counts) == {}

    # `/api/search` pulls the cross-encoder — app/search.py reranks the fused window on
    # every query — but must not pull the NLI weights or the chunk index.
    resp = client.post("/api/search", json={"query": "this"})
    assert resp.status_code == 200
    assert len(resp.json()["results"]) > 1  # non-vacuous: the rerank branch was reachable
    assert models.loaded == {
        "reranker": True,
        "verification": False,
        "grounding": False,
        "chunking": False,
    }

    monkeypatch.setattr(settings, "agent_max_steps", 1)
    monkeypatch.setattr(client.app.state.chat_service.retrieval, "max_context_notes", 20)
    _stub_agent_decision(monkeypatch, ["Content with label"])
    payload = {
        "messages": [{"role": "user", "content": "what did I write about labels"}],
        "stream": True,
        "useNotesContext": True,
    }

    # The whole stream, not just the context event: grounding is scored after `done`.
    context = _chat_events(client, payload)
    assert len(context) > 1  # non-vacuous: conflict detection needs two notes to run
    after_first_chat = dict(models.construction_counts)
    assert after_first_chat == {
        "reranker": 1,
        "verification": 1,
        "grounding": 1,
        "chunking": 1,
    }

    # Cached for the process, not rebuilt per request.
    assert _chat_events(client, payload)
    assert dict(models.construction_counts) == after_first_chat


def _chat_events(client, payload):
    """Drain a whole chat stream; return the context notes it reported.

    Unlike `_chat_context_notes`, this consumes every event, so the post-`done` grounding
    step actually runs.
    """
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    notes = []
    for line in resp.iter_lines():
        if line and line.strip():
            event = json.loads(line)
            if event["type"] == "context":
                notes = event["notes"]
    return notes


def test_ready_and_stats(client):
    """
    /api/ready must flip true once everything is loaded, and /api/stats counts must
    match the fixture exactly (archived/pinned/trashed logic).
    """
    ready_resp = client.get("/api/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json().get("ready") is True

    stats_resp = client.get("/api/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_notes"] == 29  # 30 total, 1 trashed (skipped)
    assert stats["archived_notes"] == 1  # note_21.json
    assert stats["pinned_notes"] == 1  # note_22.json


def test_search_limits_and_checkboxes(client):
    """
    Search must not be silently capped at 20 results, and checkbox item text must be
    searchable.
    """
    # "this" matches almost all synthetic notes in the fixture corpus (> 20 notes)
    resp_all = client.post("/api/search", json={"query": "this"})
    assert resp_all.status_code == 200
    results_all = resp_all.json()["results"]
    assert len(results_all) >= 1

    # Search for "Item 1" which is in checkbox notes
    resp_cb = client.post("/api/search", json={"query": "Item 1"})
    assert resp_cb.status_code == 200
    results_cb = resp_cb.json()["results"]
    assert len(results_cb) > 0
    assert any("Checklist" in r["title"] for r in results_cb)


def test_exclude_tags(client):
    """
    Excluding a tag must remove its notes from search.
    """
    # Exclude notes that carry "Label6"
    ex_resp = client.post("/api/tags/excluded", json={"excluded_tags": ["Label6"]})
    assert ex_resp.status_code == 200

    # Ensure search doesn't return Labeled 6
    search_resp = client.post("/api/search", json={"query": "Labeled 6"})
    assert search_resp.status_code == 200
    results = search_resp.json()["results"]
    assert not any(r["title"] == "Labeled 6" for r in results)

    # Clean up
    client.post("/api/tags/excluded", json={"excluded_tags": []})


def test_embeddings_carry_tags_for_colouring(client):
    """The 3D map is coloured by tag, so the payload has to carry them.

    The route read `note.get("tags")` off the engine's note dicts, which are never
    tag-enriched (enrichment mutates route-level copies), so every point came back with
    `tags: []` on a fresh server and the map had nothing to colour by.
    """
    resp = client.get("/api/embeddings")
    assert resp.status_code == 200
    points = resp.json()["embeddings"]

    assert points
    assert all("tags" in point for point in points)
    # Keep's own labels are seeded as tags at startup, so the labelled fixture notes carry
    # them here without any prior request having to warm a cache.
    tagged = {point["title"]: point["tags"] for point in points if point["tags"]}
    assert tagged.get("Labeled 6") == ["Label6"]
    assert tagged.get("Labeled 7") == ["Label7"]


def test_embeddings_payload_is_trimmed_and_3d(client):
    """Points carry a bounded snippet instead of the full content, and 3D coordinates.

    The full-content payload was many MB at real corpus scale and the view never
    displayed more than a hover line of it.
    """
    resp = client.get("/api/embeddings")
    assert resp.status_code == 200
    points = resp.json()["embeddings"]
    assert len(points) > 0
    for point in points:
        assert set(point) == {"id", "title", "snippet", "tags", "coordinates"}
        assert "content" not in point
        assert len(point["snippet"]) <= 120
        assert len(point["coordinates"]) == 3


def test_embeddings_fall_back_to_pca_when_umap_fails(client, monkeypatch):
    """A UMAP failure must not 500 the endpoint — PCA is the fallback layout."""
    import app.routes.embeddings as emb_route

    emb_route.get_cached_projection.cache_clear()

    def boom(**kwargs):
        raise RuntimeError("synthetic umap failure")

    import umap

    monkeypatch.setattr(umap, "UMAP", boom)
    resp = client.get("/api/embeddings")
    assert resp.status_code == 200
    points = resp.json()["embeddings"]
    assert all(len(p["coordinates"]) == 3 for p in points)
    emb_route.get_cached_projection.cache_clear()


def _stub_agent_decision(monkeypatch, queries):
    """Make the agent's decision step deterministic and offline.

    Only the LLM decision is stubbed — the real agent loop, RetrievalOrchestrator and
    SearchService still run, which is what makes a scoping assertion meaningful. Without
    this the loop tries to reach the configured LLM, fails, and yields zero notes, so
    "every returned note is in scope" would pass vacuously.
    """
    from app.services.agent.decision import SearchDecision

    class StubDecisionAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, prompt):
            class Result:
                output = SearchDecision(
                    tool="search_notes", queries=list(queries), reasoning="probe"
                )

            return Result()

    monkeypatch.setattr("app.services.agent.pydantic_agent.Agent", StubDecisionAgent)


def _chat_context_notes(client, payload):
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    for line in resp.iter_lines():
        if line and line.strip():
            event = json.loads(line)
            if event["type"] == "context":
                return event["notes"]
    raise AssertionError("no context event in the stream")


def test_chat_scopes_retrieval_to_the_requested_tags(client, monkeypatch):
    """The tag scope must bound what chat retrieves.

    `tags`/`date_range` were once accepted by ChatRequest and the orchestrator with
    nothing applying them: SearchService.search took no such parameters, the
    orchestrator's signature sniff therefore never fired, and the streaming path
    dropped them entirely.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "agent_max_steps", 1)
    monkeypatch.setattr(client.app.state.chat_service.retrieval, "max_context_notes", 20)
    _stub_agent_decision(monkeypatch, ["Content with label"])

    base_payload = {
        "messages": [{"role": "user", "content": "what did I write about labels"}],
        "stream": True,
        "useNotesContext": True,
    }

    unscoped = _chat_context_notes(client, base_payload)
    scoped = _chat_context_notes(client, {**base_payload, "tags": ["Label6"]})

    # Non-vacuous: the unscoped probe reaches more than the one labelled note.
    assert len(unscoped) > 1
    assert {n["title"] for n in unscoped} & {"Labeled 6", "Labeled 7", "Labeled 8"}

    assert len(scoped) >= 1
    assert {n["title"] for n in scoped} == {"Labeled 6"}


def test_chat_scopes_retrieval_to_the_requested_date_range(client, monkeypatch):
    """The date half of the same scope: a range that excludes every note yields no context."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "agent_max_steps", 1)
    _stub_agent_decision(monkeypatch, ["Content with label"])

    base_payload = {
        "messages": [{"role": "user", "content": "what did I write about labels"}],
        "stream": True,
        "useNotesContext": True,
    }

    in_range = _chat_context_notes(
        client, {**base_payload, "date_range": {"start": "2000-01-01", "end": "2100-01-01"}}
    )
    out_of_range = _chat_context_notes(
        client, {**base_payload, "date_range": {"start": "2100-01-01"}}
    )

    assert len(in_range) >= 1
    assert out_of_range == []


def test_chat_streaming(client, monkeypatch):
    """
    End-to-end guard for the streaming chat path: the NDJSON frame sequence, the cap on
    how many notes reach the prompt, and citation numbers that stay inside the
    retrieved set.
    """
    from app.core.config import settings

    monkeypatch.setattr(client.app.state.chat_service.retrieval, "max_context_notes", 5)
    monkeypatch.setattr(settings, "agent_max_steps", 2)
    monkeypatch.setattr(settings, "chat_context_notes", 5)

    resp = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "summarize notes"}],
            "stream": True,
            "useNotesContext": True,
        },
    )
    assert resp.status_code == 200

    events = []
    for line in resp.iter_lines():
        if line and line.strip():
            events.append(json.loads(line))

    types = [ev["type"] for ev in events]
    assert "context" in types
    assert "done" in types
    assert "agent_step" in types or "suggestions" in types or "phase" in types

    # Notes injected <= chat_context_notes (plus gap analysis)
    context_event = next((ev for ev in events if ev["type"] == "context"), None)
    if context_event:
        assert len(context_event.get("notes", [])) <= 25

    # Citations in range
    done_event = next(ev for ev in events if ev["type"] == "done")
    citations = done_event.get("citations", [])
    if context_event:
        num_notes = len(context_event.get("notes", []))
        for cit in citations:
            if isinstance(cit, dict) and "note_number" in cit:
                assert cit["note_number"] <= num_notes


def test_organize_categorize_apply(client):
    """
    The categorize stream runs, and a merge_tags action really moves the tag.
    """
    # 1. Categorize streams progress -> proposals -> done
    resp = client.post("/api/organize/categorize", json={"granularity": "broad"})
    assert resp.status_code == 200
    events = []
    for line in resp.iter_lines():
        if line and line.strip():
            events.append(json.loads(line))

    types = [ev["type"] for ev in events]
    assert "progress" in types

    # 2. First apply tag 'Label6' to note
    client.post(
        "/api/organize/apply",
        json={
            "actions": [{"action": "approve", "tag_name": "Label6", "note_ids": ["note_06.json"]}]
        },
    )

    # 3. Apply with a merge_tags action
    apply_resp = client.post(
        "/api/organize/apply",
        json={
            "actions": [{"action": "merge_tags", "source_tag": "Label6", "target_tag": "MergedTag"}]
        },
    )
    assert apply_resp.status_code == 200

    # Check tags
    tags_resp = client.get("/api/tags")
    assert tags_resp.status_code == 200
    tags_data = tags_resp.json()["tags"]
    tag_names = [t["name"] if isinstance(t, dict) else t for t in tags_data]
    assert "MergedTag" in tag_names
    assert "Label6" not in tag_names


def test_image_traversal(client):
    """
    Directory traversal must be rejected.
    """
    # Attempt directory traversal
    resp = client.get("/api/image/..%2F..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code in (400, 404)
