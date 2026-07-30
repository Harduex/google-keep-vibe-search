import json
import math
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

import app.services.categorization_service as cat_mod
from app.models.label import Label, LabelVocabulary
from app.services.categorization_service import CategorizationService
from app.services.tagging.cluster import reduce_embeddings

REPO_ROOT = Path(__file__).resolve().parent.parent

# A synthetic marker standing in for sampled note text.
# It must never appear in stdout, stderr, any file, or any client stream frame.
SENTINEL = "SENTINEL_NOTE_TEXT_7f3a91"


def _leaky_exception_message() -> str:
    """A LiteLLM/httpx-shaped message that embeds the request body.

    This is the whole point of the redaction rule: provider exceptions quote the
    failed request, so `str(e)` carries the prompt — which carries sampled note text.
    """
    return (
        "litellm.APIConnectionError: POST /v1/chat/completions failed - "
        '{"messages": [{"role": "user", "content": '
        f'"Title: {SENTINEL}\\nSnippet: {SENTINEL} the rest of the note body"'
        "}]}"
    )


class _RaisingLLM:
    """Stub LLM client whose every call fails with a note-text-bearing message."""

    def __init__(self, message: str):
        self.message = message

    async def complete_with_tools(self, **kwargs):
        raise RuntimeError(self.message)

    async def complete(self, **kwargs):
        raise RuntimeError(self.message)


class _EmptyLLM:
    """Stub LLM client that returns an empty completion on every attempt."""

    async def complete_with_tools(self, **kwargs):
        return {"tool_calls": [], "content": "   "}

    async def complete(self, **kwargs):
        return "   "


async def _instant_sleep(*_args, **_kwargs):
    return None


def _log_like_names(directory: Path):
    """Names of log-ish files directly in `directory` (never their contents)."""
    return {
        p.name
        for p in directory.iterdir()
        if p.is_file() and (p.suffix == ".log" or "failure" in p.name.lower())
    }


def _files_containing(directory: Path, needle: str):
    """Paths under `directory` whose bytes contain `needle`. Returns paths only."""
    hits = []
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if needle in text:
            hits.append(str(path.relative_to(directory)))
    return hits


@pytest.mark.asyncio
async def test_llm_naming_failure_never_leaks_note_text(tmp_path, monkeypatch, capsys):
    """A failing naming call must leak nothing to stdout, stderr or disk.

    The service writes its failure log relative to the CWD, so the test runs in a
    tmp CWD: that keeps the real repo root clean (an existing llm_failures.log
    there may hold pre-fix leaked text and must never be read or truncated) while
    still letting us scan the file the code actually writes.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cat_mod.asyncio, "sleep", _instant_sleep)

    root_logs_before = _log_like_names(REPO_ROOT)

    service = CategorizationService(
        search_service=None,
        note_service=None,
        llm=_RaisingLLM(_leaky_exception_message()),
    )

    result = await service._get_llm_tag_name(
        notes_text=f"Title: {SENTINEL}\nSnippet: {SENTINEL} note body",
        keywords="alpha, beta",
        neighbor_keywords="gamma",
    )
    assert result == ""

    captured = capsys.readouterr()
    assert SENTINEL not in captured.out, "sentinel leaked into stdout"
    assert SENTINEL not in captured.err, "sentinel leaked into stderr"

    leaked_files = _files_containing(tmp_path, SENTINEL)
    assert leaked_files == [], f"sentinel leaked into file(s): {leaked_files}"

    new_root_logs = sorted(_log_like_names(REPO_ROOT) - root_logs_before)
    assert new_root_logs == [], f"log file(s) created in the repo root: {new_root_logs}"


@pytest.mark.asyncio
async def test_llm_failure_log_holds_only_redacted_metadata(tmp_path, monkeypatch, capsys):
    """The failure log may contain exception types and counters — nothing else."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cat_mod.asyncio, "sleep", _instant_sleep)

    service = CategorizationService(
        search_service=None,
        note_service=None,
        llm=_RaisingLLM(_leaky_exception_message()),
    )
    await service._get_llm_tag_name(
        notes_text=f"Title: {SENTINEL}\nSnippet: {SENTINEL}",
        keywords="alpha",
        neighbor_keywords="beta",
    )
    capsys.readouterr()

    log_path = tmp_path / "llm_failures.log"
    if not log_path.exists():
        pytest.skip("no failure log written; nothing to audit")

    log_text = log_path.read_text(encoding="utf-8")
    assert SENTINEL not in log_text, "sentinel leaked into llm_failures.log"
    for marker in ("Title:", "Snippet:", "messages", "content"):
        assert marker not in log_text, f"prompt marker {marker!r} leaked into llm_failures.log"
    long_lines = [i for i, line in enumerate(log_text.splitlines(), 1) if len(line) > 160]
    assert long_lines == [], f"suspiciously long log line(s) at {long_lines}"
    assert "RuntimeError" in log_text, "the exception type should still be logged"


@pytest.mark.asyncio
async def test_empty_llm_response_never_leaks_prompt(tmp_path, monkeypatch, capsys):
    """The empty-response branch also writes to the failure log — audit it too."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cat_mod.asyncio, "sleep", _instant_sleep)

    service = CategorizationService(
        search_service=None,
        note_service=None,
        llm=_EmptyLLM(),
    )
    result = await service._get_llm_tag_name(
        notes_text=f"Title: {SENTINEL}\nSnippet: {SENTINEL}",
        keywords="alpha",
        neighbor_keywords="beta",
    )
    assert result == ""

    captured = capsys.readouterr()
    assert SENTINEL not in captured.out, "sentinel leaked into stdout"
    assert SENTINEL not in captured.err, "sentinel leaked into stderr"
    leaked_files = _files_containing(tmp_path, SENTINEL)
    assert leaked_files == [], f"sentinel leaked into file(s): {leaked_files}"


@pytest.mark.asyncio
async def test_categorize_error_frame_never_leaks_note_text(monkeypatch, capsys):
    """The client stream frame must carry a redacted exception, not `str(e)`.

    This one leaves the machine, so it matters more than the log.
    """

    class _ExplodingSearchService:
        @property
        def embeddings(self):
            raise RuntimeError(_leaky_exception_message())

    service = CategorizationService(
        search_service=_ExplodingSearchService(),
        note_service=None,
        llm=_EmptyLLM(),
    )

    frames = [json.loads(line) async for line in service.categorize()]
    assert [f["type"] for f in frames] == ["error"]

    error_text = frames[0]["error"]
    assert SENTINEL not in error_text, "sentinel leaked into the client error frame"
    assert "RuntimeError" in error_text, "the exception type should still reach the client"

    captured = capsys.readouterr()
    assert SENTINEL not in captured.out, "sentinel leaked into stdout"
    assert SENTINEL not in captured.err, "sentinel leaked into stderr (traceback?)"


def test_categorization_source_has_no_redaction_bypass():
    """Static guard for the leak sites that are hard to reach in a tier-1 test.

    `_name_labels_async` is a closure inside the full clustering pipeline, so its
    error path cannot be driven with stubbed embeddings. Guard it at the source
    level instead. Reports line numbers only — never file content.
    """
    source = (REPO_ROOT / "app" / "services" / "categorization_service.py").read_text(
        encoding="utf-8"
    )
    banned = ("str(e", "traceback.print_exc", "{e}", "{e1}", "repr(raw")
    offenders = [
        (lineno, pattern)
        for lineno, line in enumerate(source.splitlines(), 1)
        for pattern in banned
        if pattern in line
    ]
    assert offenders == [], f"raw exception/response text at (line, pattern): {offenders}"


def test_sanitize_tag_name():
    # JSON input
    assert (
        CategorizationService._sanitize_tag_name('{"tag": "Home Renovation"}') == "Home Renovation"
    )

    # Quoted input
    assert CategorizationService._sanitize_tag_name('"Travel Plans"') == "Travel Plans"

    # 4+ word input truncates to 3
    assert (
        CategorizationService._sanitize_tag_name("My Awesome Travel Plans Today")
        == "My Awesome Travel"
    )

    # Sentence input
    assert CategorizationService._sanitize_tag_name("These are some recipes.") == "These Are Some"

    # Cyrillic input is valid now
    assert CategorizationService._sanitize_tag_name("Рецепти") == "Рецепти"

    # Valid
    assert CategorizationService._sanitize_tag_name("Home Renovation") == "Home Renovation"


def test_apply_merge_map():
    vocab = LabelVocabulary()
    vocab.add(
        Label(
            name="Gym",
            seed_note_ids=["1", "2"],
            sample_notes=[{"title": "A"}],
            confidence=0.8,
            source="cluster",
            is_anchor=False,
        )
    )
    vocab.add(
        Label(
            name="Workout",
            seed_note_ids=["3"],
            sample_notes=[{"title": "B"}],
            confidence=0.6,
            source="cluster",
            is_anchor=False,
        )
    )
    vocab.add(
        Label(
            name="Recipes",
            seed_note_ids=["4"],
            sample_notes=[{"title": "C"}],
            confidence=0.9,
            source="cluster",
            is_anchor=False,
        )
    )

    merge_map = {
        "merges": [
            {"into": "Fitness", "from": ["Gym", "Workout"]},
            {"into": "Unknown", "from": ["DoesNotExist"]},
        ],
        "keep": ["Recipes"],
    }

    CategorizationService._apply_merge_map(vocab, merge_map)
    result = vocab.labels

    # Should have Fitness and Recipes
    assert len(result) == 2

    # Recipes preserved
    recipes = next((p for p in result if p.name == "Recipes"), None)
    assert recipes is not None
    assert recipes.seed_note_ids == ["4"]

    # Fitness merged
    fitness = next((p for p in result if p.name == "Fitness"), None)
    assert fitness is not None

    # Union of note_ids
    assert set(fitness.seed_note_ids) == {"1", "2", "3"}

    # Sample notes from largest constituent ("Gym" had count 2)
    assert fitness.sample_notes == [{"title": "A"}]

    # Weighted confidence: (0.8*2 + 0.6*1)/3 = 2.2/3 = 0.733... -> 0.73
    assert fitness.confidence == 0.73


def test_adaptive_sizing():
    # specific: max(8, int(math.log10(n) * 3))
    # broad: max(15, int(math.log10(n) * 6))

    # n = 100
    _, _, min_sz_spec, _ = CategorizationService._get_cluster_sizing("specific", 100)
    assert min_sz_spec == max(8, int(math.log10(100) * 3))  # max(8, 6) = 8

    _, _, min_sz_broad, _ = CategorizationService._get_cluster_sizing("broad", 100)
    assert min_sz_broad == max(15, int(math.log10(100) * 6))  # max(15, 12) = 15

    # n = 2000
    _, _, min_sz_spec, _ = CategorizationService._get_cluster_sizing("specific", 2000)
    assert min_sz_spec == max(8, int(math.log10(2000) * 3))  # int(3.3 * 3) = 9

    _, _, min_sz_broad, _ = CategorizationService._get_cluster_sizing("broad", 2000)
    assert min_sz_broad == max(15, int(math.log10(2000) * 6))  # int(3.3 * 6) = 19

    # n = 20000
    _, _, min_sz_spec, _ = CategorizationService._get_cluster_sizing("specific", 20000)
    assert min_sz_spec == max(8, int(math.log10(20000) * 3))  # int(4.3 * 3) = 12

    _, _, min_sz_broad, _ = CategorizationService._get_cluster_sizing("broad", 20000)
    assert min_sz_broad == max(15, int(math.log10(20000) * 6))  # int(4.3 * 6) = 25


def test_harvest_title_prefixes():
    import app.services.categorization_service as cat_mod

    # temporarily set threshold to 2 for test
    original = cat_mod.PREFIX_MIN_COUNT
    cat_mod.PREFIX_MIN_COUNT = 2

    try:
        notes = [
            {"title": "Tip: eat veggies"},
            {"title": "TIP: sleep well"},
            {"title": "Recipe - cake"},
            {"title": "recipe - pie"},
            {"title": "Just a normal title"},
            {"title": "10:30 meeting"},  # should not match
            {"title": "Рецепта: баница"},  # cyrillic
            {"title": "РЕЦЕПТА: мусака"},  # cyrillic
            {"title": "Aaa Bbb Ccc: three words prefix"},  # 3 words
            {"title": "Aaa Bbb Ccc Ddd: four words prefix"},  # should not match (max 3 words)
            {"title": "Aaa Bbb Ccc: another one"},
        ]

        result = CategorizationService._harvest_title_prefixes(notes)

        # Tip should be found (count 2)
        assert "tip" in result
        assert result["tip"] == 2

        # Recipe should be found (count 2)
        assert "recipe" in result
        assert result["recipe"] == 2

        # Рецепта should be found (count 2)
        assert "рецепта" in result
        assert result["рецепта"] == 2

        # Aaa Bbb Ccc should be found (count 2)
        assert "aaa bbb ccc" in result
        assert result["aaa bbb ccc"] == 2

        # 10:30 should NOT be found
        assert "10" not in result
        assert "10:30" not in result

    finally:
        cat_mod.PREFIX_MIN_COUNT = original


def test_tf_idf_keyword_extraction():
    # Test for Phase 10A: c-TF-IDF keyword extraction
    # We provide multiple clusters, and a generic word "use" should be penalized
    # while specific words should be surfaced.
    cluster1 = [
        {"title": "Workout notes", "content": "use dumbbells for curls"},
        {"title": "Gym plan", "content": "use bench press for chest"},
    ]
    cluster2 = [
        {"title": "Baking recipe", "content": "use flour and sugar"},
        {"title": "Cooking", "content": "use salt and pepper"},
    ]

    # We pass a list of clusters (list of lists of notes) to the new API
    # The current _get_hint_keywords expects a single list of notes, so this will fail
    # or complain about signature mismatch, fulfilling our "failing test" requirement.
    keywords_by_cluster = CategorizationService._get_hint_keywords(
        [cluster1, cluster2], max_words=2
    )

    # "use" is in every note across all clusters. With naive Counter, it would be the #1 word.
    # With TF-IDF, it should be heavily penalized (IDF goes to 0), surfacing the specific words instead.
    assert len(keywords_by_cluster) == 2
    assert "use" not in keywords_by_cluster[0]
    assert "use" not in keywords_by_cluster[1]

    # Cluster 1 specific words should include gym-related terms
    assert any(w in ["workout", "dumbbells", "bench", "gym"] for w in keywords_by_cluster[0])

    # Cluster 2 specific words should include cooking terms
    assert any(
        w in ["baking", "recipe", "flour", "sugar", "cooking"] for w in keywords_by_cluster[1]
    )


# --------------------------------------------------------------------------
# One UMAP pass per categorize run, granularity honoured
# --------------------------------------------------------------------------


class _DeterministicLLM:
    """Stub LLM that routes every call without touching a provider.

    Returns empty classifications / no merges for the prefix and
    consolidation prompts, and a fixed tag for the naming tool-call, so a
    full ``categorize`` run completes deterministically with no network.
    """

    def __init__(self):
        self.call_count = 0

    async def complete(self, *args, **kwargs):
        self.call_count += 1
        return '{"classifications": []}'

    async def complete_with_tools(self, *args, **kwargs):
        self.call_count += 1

        class MockFunction:
            arguments = json.dumps({"tag": "Topic"})

        class MockToolCall:
            function = MockFunction()

        return {"content": "Topic", "tool_calls": [MockToolCall()]}


class _StubEngine:
    """Embedding stub: encode() returns a zero vector of the right width."""

    class _Model:
        def encode(self, texts):
            return np.zeros((len(texts), 384), dtype=np.float32)

    model = _Model()


class _StubSearchForCategorize:
    """Minimal SearchService surface used by ``CategorizationService.categorize``.

    Carries precomputed embeddings / notes / note_indices and a stub engine
    so the prototype-vector builder does not call a real model.
    """

    def __init__(self, embeddings, notes, note_indices):
        self.embeddings = embeddings
        self.notes = notes
        self.note_indices = note_indices
        self.engine = _StubEngine()


@pytest.mark.asyncio
async def test_categorize_fits_umap_exactly_once_per_run(monkeypatch):
    """A full ``categorize`` run must fit UMAP exactly once.

    An earlier version fit UMAP once for the reduced-space centroids/MMR
    and a second time inside ``cluster_notes`` (which also ignored the
    granularity-derived sizing). The merged pipeline now reduces once via
    ``reduce_embeddings`` and reuses that array for HDBSCAN. This spies on
    ``reduce_embeddings`` in the categorization_service namespace and on
    ``umap.UMAP`` to assert both are exercised exactly once per run.
    """
    # Two tight 20-vec blobs so HDBSCAN forms >= 1 cluster at broad sizing
    # (min_cluster_size = max(15, ...) at n=40 -> 15, just under a blob).
    rng = np.random.RandomState(3)
    blob_a = (rng.randn(20, 384) + 5.0).astype(np.float32)
    blob_b = (rng.randn(20, 384) - 5.0).astype(np.float32)
    embeddings = np.vstack([blob_a, blob_b])
    notes = [{"id": f"note_{i}.json", "title": "", "content": ""} for i in range(40)]
    note_indices = list(range(40))

    service = CategorizationService(
        search_service=_StubSearchForCategorize(embeddings, notes, note_indices),
        note_service=None,
        llm=_DeterministicLLM(),
    )

    reduce_spy = mock.Mock(wraps=reduce_embeddings)
    monkeypatch.setattr(cat_mod, "reduce_embeddings", reduce_spy)

    import umap as _umap

    umap_ctor_spy = mock.Mock(wraps=_umap.UMAP)
    monkeypatch.setattr("app.services.tagging.cluster.umap.UMAP", umap_ctor_spy)

    frames = []
    async for line in service.categorize(granularity="broad"):
        data = json.loads(line)
        frames.append(data)
        if data.get("type") in ("done", "error"):
            break

    assert frames and frames[-1]["type"] in (
        "done",
        "error",
    ), f"categorize did not terminate cleanly; last frame={frames[-1] if frames else None}"
    assert (
        reduce_spy.call_count == 1
    ), f"reduce_embeddings called {reduce_spy.call_count} times during one run; expected exactly 1"
    assert (
        umap_ctor_spy.call_count == 1
    ), f"umap.UMAP constructed {umap_ctor_spy.call_count} times during one run; expected exactly 1"


@pytest.mark.asyncio
async def test_categorize_streams_unique_names_when_llm_always_answers_the_same_tag():
    """Two clusters whose LLM answer collides must still stream unique cards.

    Regression for the re-run defect where collisions were only repaired by
    the end-of-run ``_deduplicate_name`` pass, after every streamed ``proposal``
    card had already shown a duplicate name. ``_DeterministicLLM`` always
    answers "Topic" for every cluster, so two tight blobs guarantee a
    collision; the naming loop must now dedupe before each ``proposal``
    frame is put on the queue, giving unique ``tag_name``s and unique
    ``proposal_id``s at stream time.
    """
    rng = np.random.RandomState(7)
    blob_a = (rng.randn(20, 384) + 5.0).astype(np.float32)
    blob_b = (rng.randn(20, 384) - 5.0).astype(np.float32)
    embeddings = np.vstack([blob_a, blob_b])
    notes = [{"id": f"note_{i}.json", "title": "", "content": ""} for i in range(40)]
    note_indices = list(range(40))

    service = CategorizationService(
        search_service=_StubSearchForCategorize(embeddings, notes, note_indices),
        note_service=None,
        llm=_DeterministicLLM(),
    )

    frames = []
    async for line in service.categorize(granularity="broad"):
        data = json.loads(line)
        frames.append(data)
        if data.get("type") in ("done", "error"):
            break

    assert frames and frames[-1]["type"] == "done", (
        f"categorize did not terminate cleanly; last frame=" f"{frames[-1] if frames else None}"
    )

    proposal_frames = [f for f in frames if f["type"] == "proposal"]
    names = [f["proposal"]["tag_name"] for f in proposal_frames]
    ids = [f["proposal"]["proposal_id"] for f in proposal_frames]
    assert len(proposal_frames) >= 2, "need a collision to test dedup"
    assert len(set(names)) == len(names), f"streamed duplicate names: {names}"
    assert len(set(ids)) == len(ids), f"streamed duplicate proposal_ids: {ids}"
