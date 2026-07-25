"""Benchmark package — and the one place that keeps benchmarks out of the real cache.

Two hazards, both of which have actually fired:

1. `settings` is constructed the moment `app.core.config` is first imported, reading
   `CACHE_DIR` from the environment *at that instant*. A runner that sets
   `os.environ["CACHE_DIR"]` after importing `app.search` is too late: the already-built
   settings object still resolves to the repo's `cache/`, and `VibeSearch(force_refresh=True)`
   then overwrites the user's real `embeddings.npz` and `notes_hash.json` with benchmark
   data. So the environment is set **here**, at package import, before any bench module can
   pull in an app module.
2. The previous guard in this file checked `"app.core.config.settings" in sys.modules`,
   which is never true — `sys.modules` is keyed by module name, never by attribute — so it
   passed unconditionally. `assert_cache_isolated()` below actually resolves the path and
   compares it.
"""

import os
import sys
from pathlib import Path

# Privacy assertions
keep_path = os.getenv("GOOGLE_KEEP_PATH")
if keep_path is not None and keep_path != "." and keep_path != "./":
    raise RuntimeError(
        "Privacy assertion failed: GOOGLE_KEEP_PATH is set to a real path. "
        "Benchmarks must only run with GOOGLE_KEEP_PATH=. to avoid touching user notes."
    )

BENCH_DIR = Path(__file__).parent
REPO_ROOT = BENCH_DIR.parent
CORPORA_DIR = BENCH_DIR / "corpora"
RUN_DIR = BENCH_DIR / ".run"
REAL_CACHE_DIR = (REPO_ROOT / "cache").resolve()

CORPORA_DIR.mkdir(exist_ok=True)
RUN_DIR.mkdir(exist_ok=True)

# One fresh cache per process, i.e. per benchmark run. Fresh matters for more than safety:
# sharing a cache between runs made the first run compute chunk embeddings and later runs
# load them back, and the float round-trip flipped rank-boundary documents, so the harness
# disagreed with its own baseline.
BENCH_CACHE_DIR = RUN_DIR / f"cache_{os.getpid()}"

# Under pytest, isolation belongs to the suite's own autouse fixture — bench must not fight
# it for the environment, and `app.core.config` is legitimately imported first there.
_UNDER_PYTEST = "pytest" in sys.modules

if not _UNDER_PYTEST:
    BENCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["CACHE_DIR"] = str(BENCH_CACHE_DIR)

    if "app.core.config" in sys.modules:
        raise RuntimeError(
            "app.core.config was imported before bench/__init__.py, so `settings` may "
            "already point at the real cache/. Import bench (or a bench.* module) first."
        )


def assert_cache_isolated() -> None:
    """Fail loudly if the app's resolved cache dir is the real one.

    Call this right after importing app modules in a runner. It reads a path, never a cache
    file's contents.
    """
    from app.core.config import settings

    resolved = Path(settings.resolved_cache_dir).resolve()
    if resolved == REAL_CACHE_DIR or REAL_CACHE_DIR in resolved.parents:
        raise RuntimeError(
            f"Refusing to run: the app resolved its cache to {resolved}, which is the real "
            f"cache. Benchmarks must never read or write it."
        )
