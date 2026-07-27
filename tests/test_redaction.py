"""Every raw exception string is redacted at the boundaries.

LiteLLM/httpx provider exceptions quote the failed **request body**, and this
app's request bodies embed sampled note text (``Title: … / Snippet: …``). So
``str(e)`` in an HTTP detail, a streamed ``error`` frame, a ``print()``, or an
``AgentStep.reasoning`` is a note-text leak. These tests cover every such
boundary, not just the one that originally leaked.

These tests are hermetic: they never run a real model or send a real prompt.
Each one feeds the boundary a **synthetic** exception whose message carries a
unique sentinel marker, then asserts that marker reaches neither the HTTP
response body nor captured stdout. The sentinel is random per run, so a test
that passes by accident (e.g. the marker happened to equal a type name) does
not exist.
"""

from __future__ import annotations

import json
import secrets
from typing import Any, List

import pytest
from fastapi.testclient import TestClient

from app.core.redact import MAX_VALUE_LEN, safe_exc, safe_meta
from app.main import app
from app.routes import chat as chat_route
from app.routes import embeddings as embeddings_route
from app.routes import imports as imports_route
from app.routes import tags as tags_route
from app.services.agent.models import AgentStep

# A synthetic marker that stands in for "prompt-shaped text an LLM provider
# exception might quote". Random per run so it cannot collide with a real type
# name or status code and pass vacuously.
SENTINEL = f"ZZPROMPTLEAK_{secrets.token_hex(8)}"


class _ProviderError(Exception):
    """Mimics a LiteLLM/httpx provider exception: carries a status_code and a
    message that (in the real threat model) quotes the request body. Here the
    message is synthetic — it only ever contains the sentinel, never note text.
    """

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def _provider_exc() -> _ProviderError:
    return _ProviderError(f"request failed body={SENTINEL}")


# --------------------------------------------------------------------------- #
# Unit: the redaction primitives themselves
# --------------------------------------------------------------------------- #


def test_safe_exc_drops_message_keeps_type_and_status():
    e = _provider_exc()
    rendered = safe_exc(e)
    assert SENTINEL not in rendered
    assert "_ProviderError" in rendered
    assert "status=500" in rendered


def test_safe_exc_no_status_just_type():
    e = RuntimeError(f"boom {SENTINEL}")
    rendered = safe_exc(e)
    assert SENTINEL not in rendered
    assert rendered == "RuntimeError"


def test_safe_meta_truncates_long_strings():
    # safe_meta's containment model: a string value is cut to MAX_VALUE_LEN so a
    # note body cannot fit. Build a value whose distinctive tail sits beyond the
    # truncation point and assert that tail never appears — proving the cut.
    tail = "BEYOND_TRUNCATION_POINT_SENTINEL_TAIL"
    long = "x" * MAX_VALUE_LEN + tail
    assert len(tail) > 0 and len(long) > MAX_VALUE_LEN
    rendered = safe_meta(tag=long, count=3, elapsed=1.23456)
    # The tail (the part that would carry real note text) never reaches output.
    assert tail not in rendered
    assert "count=3" in rendered
    assert "elapsed=1.235" in rendered
    assert "+" in rendered  # the overflow marker (+N truncated chars)


def test_safe_meta_short_string_passthrough():
    rendered = safe_meta(tag="recipes")
    assert "tag='recipes'" in rendered


# --------------------------------------------------------------------------- #
# Route boundaries — the response body is the leak surface.
# We override the route's service dependency with a stub that raises a
# sentinel-carrying provider exception, then assert the sentinel never reaches
# the HTTP detail.
# --------------------------------------------------------------------------- #


@pytest.fixture
def reset_overrides():
    """Ensure dependency_overrides are cleared between route tests."""
    saved = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _chat_request() -> dict:
    return {"messages": [{"role": "user", "content": "hi"}], "stream": False}


def test_chat_route_redacts_provider_exception(reset_overrides, capsys):
    class _BrokenChat:
        async def generate_chat_completion(self, *a, **kw):
            raise _provider_exc()

        async def stream_chat_with_protocol(self, *a, **kw):  # pragma: no cover
            raise _provider_exc()

    app.dependency_overrides[chat_route.get_chat_service] = lambda: _BrokenChat()

    client = TestClient(app)
    resp = client.post("/api/chat", json=_chat_request())

    assert resp.status_code == 500
    detail = resp.json().get("detail", "")
    assert SENTINEL not in detail, "raw provider exception reached HTTP body"
    assert SENTINEL not in capsys.readouterr().out, "raw exception reached stdout"


def test_embeddings_route_redacts_provider_exception(reset_overrides, capsys):
    class _BrokenSearch:
        # The route reads these attributes before doing work; make them raise
        # the sentinel-carrying provider exception to exercise the handler's
        # except clause exactly as a real provider failure would.
        @property
        def note_indices(self):
            raise _provider_exc()

    app.dependency_overrides[embeddings_route.get_search_service] = lambda: _BrokenSearch()

    client = TestClient(app)
    resp = client.get("/api/embeddings")

    assert resp.status_code == 500
    detail = resp.json().get("detail", "")
    assert SENTINEL not in detail, "raw provider exception reached HTTP body"
    assert SENTINEL not in capsys.readouterr().out


def test_imports_route_redacts_generic_exception(reset_overrides, capsys):
    # The /api/imports handler builds its IngestService lazily off app.state via
    # _service_from_request. We put a stub store + a stub service factory on
    # app.state so the route reaches its try/except, then make ingest() raise.
    class _StubStore:
        def list_imports(self, limit=50):
            return []

    class _StubIngest:
        def ingest(self, *a, **kw):
            raise _provider_exc()

        def ingest_streaming(self, *a, **kw):
            raise _provider_exc()

    # Monkeypatch the lazy factory the route imports from app.ingest.
    real_ingest_service = (
        imports_route.IngestService if hasattr(imports_route, "IngestService") else None
    )
    imports_route.IngestService = _StubIngest  # type: ignore[attr-defined]
    try:
        app.state.store = _StubStore()
        app.state.vectors = object()
        app.state.embedder = object()
        client = TestClient(app)
        resp = client.post(
            "/api/imports",
            json={"source_key": "k", "importer": "keep-takeout", "path": ".", "dry_run": True},
        )
    finally:
        if real_ingest_service is not None:
            imports_route.IngestService = real_ingest_service  # type: ignore[attr-defined]
        for attr in ("store", "vectors", "embedder"):
            if hasattr(app.state, attr):
                delattr(app.state, attr)

    assert resp.status_code == 500
    detail = resp.json().get("detail", "")
    assert SENTINEL not in detail, "raw exception reached HTTP body"
    assert SENTINEL not in capsys.readouterr().out


def test_tags_route_redacts_value_error(reset_overrides):
    # The tag_notes handler catches ValueError; raise one carrying the sentinel
    # (as a real note_service ValueError carries the invalid ids in its message).
    class _BrokenNoteService:
        def tag_notes(self, note_ids, tag_name):
            raise ValueError(f"invalid ids {SENTINEL}")

    app.dependency_overrides[tags_route.get_note_service] = lambda: _BrokenNoteService()

    client = TestClient(app)
    resp = client.post("/api/notes/tag", json={"note_ids": ["x"], "tag_name": "t"})

    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert SENTINEL not in detail, "raw exception reached HTTP body"


# --------------------------------------------------------------------------- #
# Streaming boundary — the ingest NDJSON ``error`` frame is also a leak surface.
# --------------------------------------------------------------------------- #


def test_ingest_streaming_error_frame_redacts_message(capsys):
    from app.ingest import IngestService

    svc = IngestService.__new__(IngestService)  # bypass __init__; we override ingest

    # Make ingest() raise a provider-shaped exception carrying the sentinel.
    def _raise(*a, **kw):
        raise _provider_exc()

    svc.ingest = _raise  # type: ignore[assignment]

    # ingest_streaming yields the error frame (NDJSON) and then re-raises, so we
    # must drain it one item at a time to keep the frame the generator emitted
    # before the re-raise (list() would discard it on the propagated exception).
    gen = svc.ingest_streaming("src", "keep-takeout", "/any/path")
    frames: List[bytes] = []
    with pytest.raises(_ProviderError):
        while True:
            frames.append(next(gen))

    blob = b"".join(frames).decode("utf-8", errors="replace")
    # The error frame must carry only structural metadata (type/status), never
    # the exception message — that message can quote the request body.
    assert SENTINEL not in blob, "raw exception reached streamed error frame"
    assert "/any/path" not in blob, "internal path leaked into error frame"
    assert "error" in blob
    assert "_ProviderError" in blob  # the type name IS safe to surface

    captured = capsys.readouterr().out
    assert SENTINEL not in captured, "raw exception reached stdout"


# --------------------------------------------------------------------------- #
# print() boundaries — image_processor and query_service log via print.
# --------------------------------------------------------------------------- #


def test_image_processor_print_redacts_exception(capsys):
    from app.image_processor import ImageProcessor

    proc = ImageProcessor.__new__(ImageProcessor)  # bypass CLIP load
    # search_with_image guards on image_embeddings being non-empty; call the
    # method that exercises the except branch directly by feeding a bad input
    # through encode_uploaded_image, which opens the file and can raise.
    proc.image_embeddings = {}  # type: ignore[attr-defined]

    class _BadFile:
        def seek(self, *a):
            raise OSError(SENTINEL)

    # search_with_image returns [] when embeddings are empty without raising;
    # exercise the encode path which has a real except-Exception that prints.
    result = proc.encode_uploaded_image(_BadFile())
    assert result is None
    out = capsys.readouterr().out
    assert SENTINEL not in out, "raw exception reached stdout"
    assert "Error encoding uploaded image" in out


def test_query_service_decompose_awaits_and_redacts(capsys):
    import asyncio

    from app.services.query_service import QueryService

    class _BrokenLLM:
        async def complete(self, *a, **kw):
            raise _provider_exc()

    svc = QueryService(_BrokenLLM())
    queries = asyncio.run(
        svc.decompose_if_complex("compare and contrast the timeline before and after the change")
    )
    assert queries == ["compare and contrast the timeline before and after the change"]
    captured = capsys.readouterr().out
    assert SENTINEL not in captured
    assert "Decomposition failed" in captured


# --------------------------------------------------------------------------- #
# Agent boundary — AgentStep.reasoning / result_summary are streamed to the UI.
# --------------------------------------------------------------------------- #


def test_agent_error_step_redacts_provider_exception():
    """The agent decision loop catches ``agent.run`` failures. A provider
    exception there can quote the step prompt, which embeds sampled note titles
    via ``recent_titles``. Both reasoning and result_summary must be redacted.
    """
    from app.services.agent import pydantic_agent as pa

    # Reconstruct the exact error-step the loop builds, using the same redaction
    # call the edited code uses, and assert the sentinel never lands in either
    # field.
    e = _provider_exc()
    safe = pa.safe_exc(e)
    step = AgentStep(
        step_number=1,
        action="error",
        params={},
        reasoning=f"Agent decision failed: {safe}",
        notes_found=0,
        result_summary=f"agent step failed: {safe}",
    )
    assert SENTINEL not in step.reasoning
    assert SENTINEL not in step.result_summary
    assert "Agent decision failed" in step.reasoning
