"""Guards for the two ways a cache write has destroyed real user data.

1. A test writing into the developer's live `cache/` — `test_pipeline.py` emptied
   `tags.json` that way, and `bench/run_retrieval.py` overwrote `embeddings.npz` and
   `notes_hash.json` by setting CACHE_DIR *after* importing an app module.
2. A truncating write — `open(path, "w")` empties the file before it writes, so a crash or
   an empty in-memory map leaves nothing behind.

Assertions here use counts and paths only, never cache contents.
"""

import ast
import json
import os
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.note_service import NoteService, save_excluded_tags_to_cache, save_tags_to_cache


class TestCacheIsolation:
    def test_every_test_gets_an_isolated_cache_dir(self, isolate_cache_dir):
        # The autouse fixture must have redirected the app's own resolver, not just the env.
        resolved = Path(settings.resolved_cache_dir).resolve()
        assert resolved == Path(isolate_cache_dir).resolve()

    def test_a_real_note_service_writes_only_inside_the_isolated_dir(self, isolate_cache_dir):
        service = NoteService()
        service.notes = [{"id": "n1", "labels": ["Recipes"]}]
        service.note_tags = {}
        service.excluded_tags = set()

        service.seed_tags_from_labels()

        assert (Path(isolate_cache_dir) / "tags.json").exists()

    def test_bench_cache_dir_is_never_the_real_cache(self):
        import bench

        resolved = Path(bench.BENCH_CACHE_DIR).resolve()
        assert resolved != bench.REAL_CACHE_DIR
        assert bench.REAL_CACHE_DIR not in resolved.parents

    def test_bench_isolation_assertion_actually_fires(self, monkeypatch):
        # The previous guard tested `"app.core.config.settings" in sys.modules`, which is
        # never true — sys.modules is keyed by module name — so it passed unconditionally
        # while the runners wrote into the real cache. This one must really raise.
        import bench

        monkeypatch.setattr(settings, "cache_dir", str(bench.REAL_CACHE_DIR))
        with pytest.raises(RuntimeError, match="real cache"):
            bench.assert_cache_isolated()

        monkeypatch.setattr(settings, "cache_dir", str(bench.BENCH_CACHE_DIR))
        bench.assert_cache_isolated()  # and pass when isolated


class TestScriptsImportBenchFirst:
    """The third instance of hazard 1, which the two guards above did not cover.

    They protect `tests/` (autouse fixture) and `bench/` (import-time CACHE_DIR pin).
    Nothing protected `scripts/`, and that is where the live damage path was:
    `scripts/eval_categorization.py` imported `app.core.config` with no redirect, so
    `settings` bound to the real `cache/`. `NoteService.load_notes` reads the store
    rather than parsing `google_keep_path`, so `load_notes(force_refresh=True)`
    ran IngestService against the real `store.db` and soft-deleted every document
    absent from the synthetic import — the entire corpus.

    Redirecting `settings.google_keep_path` was sufficient isolation when that script
    was written, and silently stopped being sufficient once the store landed. The lesson is
    structural, so this asserts the import order for *every* script, not just the one
    that broke: a runner that touches an app module must import `bench` first.

    Paths only — this never opens a cache file.
    """

    @staticmethod
    def _first_import_lines(source: str):
        """Return (first bench lineno, first app lineno), None where absent."""
        tree = ast.parse(source)
        bench_at = app_at = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "bench" or name.startswith("bench."):
                    if bench_at is None or node.lineno < bench_at:
                        bench_at = node.lineno
                elif name == "app" or name.startswith("app."):
                    if app_at is None or node.lineno < app_at:
                        app_at = node.lineno
        return bench_at, app_at

    def _script_paths(self):
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        return sorted(scripts_dir.glob("*.py"))

    def test_scripts_dir_is_present(self):
        # If scripts/ is ever renamed, the test below would vacuously pass.
        assert self._script_paths(), "no scripts found — this guard would pass vacuously"

    def test_every_script_touching_app_imports_bench_first(self):
        offenders = []
        for path in self._script_paths():
            bench_at, app_at = self._first_import_lines(path.read_text(encoding="utf-8"))
            if app_at is None:
                continue  # script never touches the app; settings is never built
            if bench_at is None or bench_at > app_at:
                offenders.append(f"{path.name}: app@{app_at} bench@{bench_at}")
        assert not offenders, (
            "these scripts import an app module before bench, so `settings` binds to the "
            f"REAL cache dir and a force_refresh run can destroy it: {offenders}"
        )

    def test_the_guard_fires_on_the_unfixed_import_order(self):
        # The pre-fix shape of eval_categorization.py. Without this, a rewrite that
        # loosened the check above would look green.
        unfixed = "from app.core.config import settings\nimport bench\n"
        bench_at, app_at = self._first_import_lines(unfixed)
        assert app_at == 1 and bench_at == 2
        assert bench_at > app_at  # i.e. exactly what the assertion above rejects


class TestRealCacheWritesAreBlocked:
    def test_a_write_aimed_at_the_real_cache_is_refused(self, monkeypatch):
        # Simulates the accident directly: a test whose cache dir resolves to the real one.
        import bench

        monkeypatch.setattr(settings, "cache_dir", str(bench.REAL_CACHE_DIR))
        with pytest.raises(AssertionError, match="real cache directory"):
            save_tags_to_cache({"n1": ["Recipes"]})


class TestAtomicTagWrites:
    def test_previous_version_is_kept_when_tags_are_emptied(self, isolate_cache_dir, capsys):
        save_tags_to_cache({"n1": ["Recipes"], "n2": ["Travel"]})

        save_tags_to_cache({})  # the accident: an empty in-memory map reaching disk

        tags_file = Path(settings.tags_cache_file)
        backup = Path(f"{settings.tags_cache_file}.bak")
        assert json.loads(tags_file.read_text()) == {}
        # Recoverable, and loud about it — counts only, no tag names.
        assert len(json.loads(backup.read_text())) == 2
        assert "writing 0 tagged notes over 2 existing" in capsys.readouterr().out

    def test_write_leaves_no_temporary_files_behind(self, isolate_cache_dir):
        save_tags_to_cache({"n1": ["Recipes"]})
        save_excluded_tags_to_cache({"Private"})

        leftovers = [p.name for p in Path(isolate_cache_dir).iterdir() if p.name.startswith(".tmp")]
        assert leftovers == []

    def test_a_failed_serialisation_does_not_truncate_the_existing_file(self, isolate_cache_dir):
        save_tags_to_cache({"n1": ["Recipes"]})

        class Unserialisable:
            pass

        with pytest.raises(TypeError):
            save_tags_to_cache({"n2": [Unserialisable()]})

        # The old content survived, because the write went to a temp file first.
        assert len(json.loads(Path(settings.tags_cache_file).read_text())) == 1
