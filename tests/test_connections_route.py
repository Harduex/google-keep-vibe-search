"""Connections endpoint: similarity / shared tags / shared entities for one note.

All assertions run against the synthetic fixture corpus (30 notes, stub embedder,
stub spaCy) — never real notes.
"""


def _points(client):
    resp = client.get("/api/embeddings")
    assert resp.status_code == 200
    return resp.json()["embeddings"]


def test_connections_shape_and_similarity(client):
    points = _points(client)
    note_id = points[0]["id"]

    resp = client.get(f"/api/notes/{note_id}/connections?k=5")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"id", "similar", "shared_tags", "shared_entities"}
    assert body["id"] == note_id

    assert 0 < len(body["similar"]) <= 5
    scores = [n["score"] for n in body["similar"]]
    assert scores == sorted(scores, reverse=True)
    assert all(set(n) == {"id", "title", "score"} for n in body["similar"])
    # Never connects a note to itself.
    assert note_id not in [n["id"] for n in body["similar"]]


def test_connections_shared_tags(client):
    # Fixture notes 6-8 each carry a distinct label (Label6..Label8), so a tagged
    # note's groups only ever contain tags it actually has.
    points = _points(client)
    tagged = next(p for p in points if p["tags"])

    resp = client.get(f"/api/notes/{tagged['id']}/connections")
    assert resp.status_code == 200
    groups = resp.json()["shared_tags"]
    assert all(g["tag"] in tagged["tags"] for g in groups)
    for g in groups:
        assert len(g["notes"]) <= 10
        assert tagged["id"] not in [n["id"] for n in g["notes"]]


def test_connections_unknown_note_is_404(client):
    resp = client.get("/api/notes/no-such-note/connections")
    assert resp.status_code == 404


def test_connections_k_is_validated(client):
    points = _points(client)
    resp = client.get(f"/api/notes/{points[0]['id']}/connections?k=0")
    assert resp.status_code == 422
    resp = client.get(f"/api/notes/{points[0]['id']}/connections?k=51")
    assert resp.status_code == 422
