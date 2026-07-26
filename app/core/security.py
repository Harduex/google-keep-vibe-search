"""Network posture for a single-user, loopback-only application.

This app has no authentication and no per-user data model: `tags.json` and `store.db`
hold exactly one corpus, and every route reads the whole of it. That is a deliberate
supported-configuration boundary, not an unfinished feature — adding auth would mean
introducing a notion of "user" to the data model, which is an architecture decision
rather than a hardening pass.

What that boundary implies, and what this module enforces:

* The API must not be reachable from another machine. Binding to 127.0.0.1 is the
  actual control (see `docker-compose.yml` and `main.py`'s dev runner); everything
  here is defence in depth for when someone inevitably binds 0.0.0.0 anyway.
* Browsers must not let an arbitrary web page drive the API on the user's behalf, so
  the allowed origins are enumerated rather than wildcarded.
* A single client must not be able to exhaust memory or pin the GPU, whether through
  malice or a runaway retry loop.

Values are module constants on purpose: configuration is frozen for this phase of the
project, so a new tuning value belongs in code with its trade-off written down, not in
another environment variable nobody sets.
"""

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from fastapi.responses import JSONResponse

# The dev client (Vite) and the container's nginx frontend. Both loopback: an origin
# that is not one of these has no legitimate reason to call this API.
#
# Why not "*": with credentials disabled a wildcard is not the disaster it would
# otherwise be, but it also advertises the API as public, and the previous pairing of
# allow_origins=["*"] with allow_credentials=True was a combination browsers refuse
# outright for credentialed requests — permissive on paper and broken in practice.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost",
    "http://127.0.0.1",
]

# Nothing in this app uses cookies or HTTP auth, so credentialed cross-origin requests
# have no purpose. Keeping this False is what makes the origin list a real boundary
# instead of a comment.
ALLOW_CREDENTIALS = False

ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Content-Type"]

# Sized for the largest legitimate request: an /api/imports body describing a folder of
# notes, which is paths and metadata rather than note content. Chat and search bodies
# are kilobytes. Raise this if a real import ever trips it — but a request larger than
# this is far more likely to be a mistake than a user.
MAX_REQUEST_BYTES = 8 * 1024 * 1024  # 8 MiB

# Per-IP request ceiling for the expensive routes. This is a courtesy limiter against a
# runaway client — a retry loop that would otherwise queue GPU work until the process
# dies — NOT a security control: it is per-process, in-memory, resets on restart, and
# an attacker who can reach this port can trivially outrun it from several addresses.
# The real control is the loopback binding.
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60.0

# Routes worth limiting: each one can start an embedding, an LLM call or a full
# clustering run. Cheap reads (tags, stats, a single note) are left alone so the UI
# stays responsive while a long job runs.
RATE_LIMITED_PREFIXES = (
    "/api/search",
    "/api/chat",
    "/api/embeddings",
    "/api/organize",
    "/api/imports",
)


class _SlidingWindow:
    """Per-key request timestamps inside the current window.

    A deque of timestamps rather than a counter, so the limit slides instead of
    resetting on a fixed boundary — a fixed window lets a client send 2x the limit
    across the boundary instant.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float) -> bool:
        hits = self._hits[key]
        cutoff = now - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


_limiter = _SlidingWindow(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)


def reset_rate_limiter() -> None:
    """Clear all recorded hits. For tests, so one test's requests cannot fail another's."""
    _limiter.reset()


async def limit_request_size(request: Request, call_next):
    """Reject oversized bodies before they are read into memory.

    Checks Content-Length first because that is the only way to refuse a large body
    *without* buffering it. A chunked request has no Content-Length, so it is capped
    while streaming instead — otherwise the header check would be trivially bypassable
    by omitting it.
    """
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > MAX_REQUEST_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
    else:
        body = await request.body()  # cached by Starlette; the route still sees it
        if len(body) > MAX_REQUEST_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )

    return await call_next(request)


async def rate_limit(request: Request, call_next):
    """Throttle the expensive routes per client address."""
    path = request.url.path
    if path.startswith(RATE_LIMITED_PREFIXES):
        client = request.client.host if request.client else "unknown"
        if not _limiter.allow(client, time.monotonic()):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={"Retry-After": str(int(RATE_LIMIT_WINDOW_SECONDS))},
            )
    return await call_next(request)
