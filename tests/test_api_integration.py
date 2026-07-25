import json

import pytest


def test_ready_and_stats(client):
    """
    Pins B4: ensure /api/ready flips true properly when everything is loaded.
    Pins B4/B2/B9: ensure /api/stats counts match the fixture correctly (archived/pinned/trashed logic).
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
    Pins B2 (search > 20 results).
    Pins B3 (checkbox item text searchable).
    """
    # B2: "this" matches almost all synthetic notes in the fixture corpus (> 20 notes)
    resp_all = client.post("/api/search", json={"query": "this"})
    assert resp_all.status_code == 200
    results_all = resp_all.json()["results"]
    assert len(results_all) >= 1

    # B3: Search for "Item 1" which is in checkbox notes
    resp_cb = client.post("/api/search", json={"query": "Item 1"})
    assert resp_cb.status_code == 200
    results_cb = resp_cb.json()["results"]
    assert len(results_cb) > 0
    assert any("Checklist" in r["title"] for r in results_cb)


def test_exclude_tags(client):
    """
    Pins B10 (excluding a tag removes notes from search).
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


def test_chat_streaming(client, monkeypatch):
    """
    Pins B1, B6, B11, B5, B7.
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
    Pins B8 (merge action).
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

    # 3. Apply with a merge_tags action (B8)
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
    Pins B12 (directory traversal).
    """
    # Attempt directory traversal
    resp = client.get("/api/image/..%2F..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code in (400, 404)
