"""Regression tests for the image route's path-traversal guard (audit finding B12).

All fixtures are synthetic directory trees built under pytest's ``tmp_path`` —
never the real Google Keep export or ``cache/`` — per the privacy boundary in
AGENTS.md / EXECUTION-PROTOCOL.md.

Traversal payloads are sent through the real HTTP layer (a `TestClient` against
an app that only mounts `images.router`), with ".." segments percent-encoded
(`%2e%2e`) so the HTTP client does not collapse them before the request
reaches the route — httpx normalizes literal ".." in a URL path itself, which
would otherwise 404 at the router before our guard ever runs.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routes import images


@pytest.fixture
def image_tree(tmp_path):
    """Build a synthetic Keep-export-shaped tree with an escape target.

    tmp_path/
        data/
            Keep/                <- google_keep_path (the "base")
                sub/photo.png    <- legitimate nested image
                escape_link -> outside/   (symlink escape)
            Keep_other/secret.txt  <- sibling-prefix escape target
        etc/passwd                 <- "../../etc/passwd"-style escape target
        outside_abs/secret.txt     <- absolute-path escape target
        outside/secret.txt        <- symlink escape target
    """
    base = tmp_path / "data" / "Keep"
    (base / "sub").mkdir(parents=True)
    (base / "sub" / "photo.png").write_bytes(b"fake-image-bytes")

    sibling = tmp_path / "data" / "Keep_other"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("do-not-serve")

    deep_escape_dir = tmp_path / "etc"
    deep_escape_dir.mkdir()
    (deep_escape_dir / "passwd").write_text("do-not-serve")

    outside_abs = tmp_path / "outside_abs"
    outside_abs.mkdir()
    (outside_abs / "secret.txt").write_text("do-not-serve")

    symlink_target = tmp_path / "outside"
    symlink_target.mkdir()
    (symlink_target / "secret.txt").write_text("do-not-serve")
    (base / "escape_link").symlink_to(symlink_target)

    return {"base": base, "tmp_path": tmp_path, "outside_abs": outside_abs}


@pytest.fixture
def client(image_tree, monkeypatch):
    monkeypatch.setattr(settings, "google_keep_path", str(image_tree["base"]))
    app = FastAPI()
    app.include_router(images.router)
    return TestClient(app)


def test_legitimate_nested_image_returns_200(client):
    resp = client.get("/api/image/sub/photo.png")
    assert resp.status_code == 200


def test_sibling_prefix_escape_is_rejected(client):
    # base = .../data/Keep, target = .../data/Keep_other/secret.txt.
    # This is the exact B12 payload: normpath+startswith admits it because
    # "/data/Keep_other" starts with the string "/data/Keep".
    resp = client.get("/api/image/%2e%2e/Keep_other/secret.txt")
    assert resp.status_code == 400
    assert "Keep_other" not in resp.text
    assert "secret.txt" not in resp.text


def test_dotdot_escape_is_rejected(client):
    resp = client.get("/api/image/%2e%2e/%2e%2e/etc/passwd")
    assert resp.status_code == 400
    assert "passwd" not in resp.text


def test_absolute_path_is_rejected(client, image_tree):
    outside_abs = image_tree["outside_abs"]
    resp = client.get(f"/api/image/{outside_abs}/secret.txt")
    assert resp.status_code == 400
    assert "secret.txt" not in resp.text


def test_symlink_escape_is_rejected(client):
    resp = client.get("/api/image/escape_link/secret.txt")
    assert resp.status_code == 400
    assert "secret.txt" not in resp.text
