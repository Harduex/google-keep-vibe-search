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
CORPORA_DIR = BENCH_DIR / "corpora"
RUN_DIR = BENCH_DIR / ".run"

CORPORA_DIR.mkdir(exist_ok=True)
RUN_DIR.mkdir(exist_ok=True)


# Try to safely import app.core.config to check the resolved cache dir,
# but we shouldn't fail other tests that import bench. We just assert if it's imported,
# it doesn't resolve to the real cache, or we just raise if someone tries to use it in benchmark context.
# Actually, the requirement is that we must never read settings.resolved_cache_dir.
# We will just verify we don't import app.core.config.settings from within bench/
def check_privacy():
    if "app.core.config.settings" in sys.modules:
        # Check if we are running a bench script (not pytest)
        if "pytest" not in sys.modules and not sys.argv[0].endswith("pytest"):
            raise RuntimeError(
                "Privacy assertion failed: Benchmarks must NEVER read settings.resolved_cache_dir "
                "or write into cache/"
            )


check_privacy()
