"""The loopback-only network posture, exercised through real requests.

Asserting that a middleware is *installed* proves nothing — these drive the app with a
TestClient and check what a client actually gets back. See app/core/security.py for why
this app has no auth and why that is a boundary rather than a gap.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import security


@pytest.fixture(autouse=True)
def _clean_limiter():
    # The limiter is process-global, so one test's requests would otherwise count
    # against another's budget and make failures depend on test order.
    security.reset_rate_limiter()
    yield
    security.reset_rate_limiter()


@pytest.fixture
def app() -> FastAPI:
    """A minimal app wired with the same middleware as the real one.

    Deliberately not the real app: this exercises the posture, and building the real
    app would drag in the lifespan and its models for no benefit here.
    """
    app = FastAPI()
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=security.ALLOWED_ORIGINS,
        allow_credentials=security.ALLOW_CREDENTIALS,
        allow_methods=security.ALLOWED_METHODS,
        allow_headers=security.ALLOWED_HEADERS,
    )
    app.middleware("http")(security.rate_limit)
    app.middleware("http")(security.limit_request_size)

    @app.post("/api/search")
    async def search(payload: dict | None = None):
        return {"ok": True}

    @app.get("/api/tags")
    async def tags():
        return {"ok": True}

    return app


class TestCorsPosture:
    def test_the_origin_list_is_not_a_wildcard_and_credentials_are_off(self):
        # The old pairing (allow_origins=["*"] + allow_credentials=True) is one browsers
        # refuse for credentialed requests, so it was permissive on paper and broken in
        # practice. Guard both halves.
        assert "*" not in security.ALLOWED_ORIGINS
        assert security.ALLOW_CREDENTIALS is False
        assert security.ALLOWED_HEADERS != ["*"]

    def test_an_allowed_origin_gets_the_cors_header(self, app):
        client = TestClient(app)
        r = client.get("/api/tags", headers={"Origin": "http://localhost:5173"})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == "http://localhost:5173"

    def test_an_unlisted_origin_is_not_granted_access(self, app):
        client = TestClient(app)
        r = client.get("/api/tags", headers={"Origin": "https://evil.example.com"})
        # Starlette answers the request but withholds the header, which is what makes
        # the browser refuse to hand the response to the calling page.
        assert "access-control-allow-origin" not in r.headers


class TestRequestSizeCap:
    def test_a_body_over_the_cap_is_refused_with_413(self, app):
        client = TestClient(app)
        oversized = b"x" * (security.MAX_REQUEST_BYTES + 1)
        r = client.post("/api/search", content=oversized)
        assert r.status_code == 413

    def test_a_body_under_the_cap_passes_through(self, app):
        client = TestClient(app)
        r = client.post("/api/search", json={"query": "hello"})
        assert r.status_code == 200

    def test_a_declared_length_over_the_cap_is_refused_without_reading_the_body(self, app):
        # The Content-Length path is the one that matters: it lets the app refuse before
        # buffering. Assert on the header alone, with a body that is genuinely small, so
        # the test fails if the implementation starts ignoring the declaration.
        client = TestClient(app)
        r = client.post(
            "/api/search",
            content=b"tiny",
            headers={"Content-Length": str(security.MAX_REQUEST_BYTES + 1)},
        )
        assert r.status_code == 413


class TestRateLimit:
    def test_the_nth_request_passes_and_the_next_one_is_throttled(self, app):
        client = TestClient(app)
        for _ in range(security.RATE_LIMIT_REQUESTS):
            assert client.get("/api/search").status_code in (200, 405)
        r = client.get("/api/search")
        assert r.status_code == 429
        assert r.headers["retry-after"]

    def test_cheap_routes_are_not_rate_limited(self, app):
        # The UI polls tags and stats while a long job runs; throttling those would make
        # the app feel broken under exactly the load the limiter exists to survive.
        client = TestClient(app)
        for _ in range(security.RATE_LIMIT_REQUESTS + 5):
            assert client.get("/api/tags").status_code == 200

    def test_the_window_slides_rather_than_resetting_on_a_boundary(self):
        # A fixed window lets a client send 2x the limit across the boundary instant.
        window = security._SlidingWindow(limit=2, window_seconds=10.0)
        assert window.allow("ip", now=0.0)
        assert window.allow("ip", now=1.0)
        assert not window.allow("ip", now=2.0)
        # The first hit ages out at t=10, so one slot frees up — and only one.
        assert window.allow("ip", now=10.5)
        assert not window.allow("ip", now=10.6)

    def test_limits_are_per_client_address(self):
        window = security._SlidingWindow(limit=1, window_seconds=10.0)
        assert window.allow("10.0.0.1", now=0.0)
        assert not window.allow("10.0.0.1", now=0.1)
        assert window.allow("10.0.0.2", now=0.2)
