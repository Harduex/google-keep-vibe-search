import os
import sys

if os.environ.get("GOOGLE_KEEP_PATH") != ".":
    print("ERROR: GOOGLE_KEEP_PATH must be set to '.' for safety.")
    sys.exit(1)

import asyncio
import hashlib
import json
import resource
import tempfile
from typing import Any, Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import bench BEFORE any app.* module — same load-bearing ordering as
# scripts/eval_retrieval.py. bench/__init__.py pins CACHE_DIR to an isolated
# per-run dir at import time; `settings` is built at the first `app.core.config`
# import and binds whatever CACHE_DIR says *at that instant*, so importing an
# app module first leaves it pointing at the real cache/.
#
# Redirecting `settings.google_keep_path` (below) is NOT sufficient isolation on
# its own, and used to be: this script was written when NoteService parsed that
# path directly. NoteService now reads from the store, so
# `load_notes(force_refresh=True)` runs IngestService against the REAL store.db
# and soft-deletes every document absent from the synthetic import — i.e. the
# whole corpus. The cache dir, not the source path, is what has to move.
import bench  # noqa: F401,E402  — imported for its import-time side effect

try:
    import torch

    HAS_CUDA = torch.cuda.is_available()
except ImportError:
    HAS_CUDA = False

from app.core.config import settings  # noqa: E402

bench.assert_cache_isolated()
from app.domain import Document, content_hash
from app.search import VibeSearch, _model_dim
from app.services.categorization_service import CategorizationService
from app.services.llm_client import LLMClient
from app.services.note_service import NoteService
from app.services.search_service import SearchService
from app.store import VectorStore
from tests.fixtures.notes import generate_synthetic_notes


class CountingFakeLLM(LLMClient):
    def __init__(self):
        super().__init__(model="test")
        self.call_count = 0

    async def complete(self, *args, **kwargs) -> str:
        self.call_count += 1
        prompt = kwargs.get("messages", [{}])[0].get("content", "")
        if "Classify these note title prefixes" in prompt:
            return '{"classifications": []}'
        elif "Borderline Pairs to Consider Merging" in prompt or "Respond as JSON" in prompt:
            return '{"merges": [], "keep": []}'
        return "{}"

    async def complete_with_tools(self, *args, **kwargs) -> Dict[str, Any]:
        self.call_count += 1
        messages = kwargs.get("messages", [])
        prompt_text = ""
        for m in messages:
            prompt_text += m.get("content", "")

        h = hashlib.md5(prompt_text.encode("utf-8")).hexdigest()[:6]
        # Space, not underscore: `_sanitize_tag_name` allows only
        # [A-Za-zА-Яа-я0-9\s&/-], so "Tag_<hash>" sanitized to "" and every cluster
        # ended up unnamed. Stability was then measured over empty strings and read
        # 100% no matter what the pipeline did — a gate that cannot fail. Keyed on the
        # prompt hash so the name is still deterministic across runs, which is what
        # the stability metric actually needs.
        tag_name = f"Tag {h}"

        class MockFunction:
            arguments = json.dumps({"tag": tag_name})

        class MockToolCall:
            function = MockFunction()

        return {"content": tag_name, "tool_calls": [MockToolCall()]}


def get_memory_stats():
    # ru_maxrss is in kilobytes on Linux
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    vram_mb = 0
    if HAS_CUDA:
        try:
            vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)
        except Exception:
            pass
    return rss_mb, vram_mb


def _notes_to_documents(notes: list) -> list:
    """Convert NoteService note dicts to content-addressed Documents.

    Parity with the deleted legacy constructor: it embedded each note's
    ``cleaned_text``, which ``NoteService._doc_to_dict`` sets to
    ``clean_note(f"{title} {content}")``. Building the Document with the same
    ``title`` and ``body`` reproduces that via ``_doc_to_note_dict``.
    """
    docs = []
    for n in notes:
        title = n.get("title", "") or ""
        body = n.get("content", "") or ""
        nid = n.get("id", "") or n.get("external_id", "")
        docs.append(
            Document(
                external_id=n.get("external_id", nid),
                title=title,
                body=body,
                id=nid,
                source_key="eval",
                content_hash=content_hash(title, body),
            )
        )
    return docs


async def run_categorization(temp_dir: str):
    settings.google_keep_path = temp_dir
    settings.enable_image_search = False

    note_service = NoteService()
    notes = note_service.load_notes(force_refresh=True)
    # Build the engine via the store-backed path (from_model + build) against an
    # isolated VectorStore under the bench-isolated cache dir, replacing the
    # deleted legacy constructor (which wrote embeddings.npz into the cache).
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(settings.embedding_model)
    vectors = VectorStore(
        os.path.join(settings.resolved_cache_dir, "vibe_search"), dim=_model_dim(model)
    )
    search_engine = VibeSearch.from_model(model, vector_store=vectors)
    search_engine.build(_notes_to_documents(notes))
    search_service = SearchService(search_engine=search_engine, note_service=note_service)

    llm = CountingFakeLLM()
    cat_service = CategorizationService(search_service, note_service, llm)

    # Granularity is "specific", not "broad". At "broad" this 28-note fixture produces
    # ZERO clusters, so every note fell into a single "Uncategorized" label and the
    # stability metric compared that one label against itself — 100%, unfailable, and
    # measuring nothing. "specific" produces real clusters, so naming and manifest reuse
    # are actually exercised.
    #
    # Read the POST-naming frame. This used to accept only `type == "proposals"`,
    # and inside `categorize()` the sole frame of that type was emitted *before* the
    # naming loop ran, carrying placeholder names ("Topic 1", "Topic 2", ...). So
    # primary-tag stability was measured over placeholders: it compared cluster
    # ordering, not tag names, and could not fail unless clustering itself changed.
    # That is the third time a gate in this project turned out to be vacuous, so:
    # prefer `label_updates`, the authoritative end-of-run frame whose names are the
    # ones actually applied. `proposals` is still accepted as a fallback because the
    # two terminal early-exit paths ("All Notes", "Uncategorized") emit only that
    # frame, with real names and no naming pass.
    proposals = None
    authoritative = False
    async for line in cat_service.categorize(granularity="specific"):
        data = json.loads(line.decode("utf-8"))
        ftype = data.get("type")
        if ftype == "label_updates":
            proposals = data.get("proposals", [])
            authoritative = True
        elif ftype == "proposals" and not authoritative:
            proposals = data.get("proposals", [])

    return proposals, llm.call_count


async def main():
    print("=== Categorization Pipeline Eval ===")
    start_rss, start_vram = get_memory_stats()

    with tempfile.TemporaryDirectory() as temp_dir:
        synthetic_notes = generate_synthetic_notes()
        for filename, note_dict in synthetic_notes:
            with open(os.path.join(temp_dir, filename), "w", encoding="utf-8") as f:
                json.dump(note_dict, f)

        run1_proposals, run1_llm_calls = await run_categorization(temp_dir)
        run2_proposals, run2_llm_calls = await run_categorization(temp_dir)

    end_rss, end_vram = get_memory_stats()

    if not run1_proposals or not run2_proposals:
        print("ERROR: Categorization failed to produce proposals.")
        sys.exit(1)

    # `label_updates` carries the classic tag proposals *plus* dashboard cards
    # (auto-merge info, gray-zone merge suggestions, the review queue). Those have no
    # `tag_name` and describe actions rather than tags, so every metric below must run
    # over the classic ones only — the client draws the same distinction.
    def classic(proposals):
        return [p for p in proposals if p.get("tag_name") and "note_ids" in p]

    run1_proposals = classic(run1_proposals)
    run2_proposals = classic(run2_proposals)
    if not run1_proposals or not run2_proposals:
        print("ERROR: No classic tag proposals in the run; nothing to measure.")
        sys.exit(1)

    tag_count = len([p for p in run1_proposals if p["tag_name"] != "Uncategorized"])

    uncat = next((p for p in run1_proposals if p["tag_name"] == "Uncategorized"), None)
    uncategorized_count = uncat["note_count"] if uncat else 0
    total_notes = sum(p["note_count"] for p in run1_proposals)
    pct_uncategorized = (uncategorized_count / total_notes * 100) if total_notes else 0

    cluster_sizes = [p["note_count"] for p in run1_proposals if p["tag_name"] != "Uncategorized"]
    mean_cluster_size = sum(cluster_sizes) / len(cluster_sizes) if cluster_sizes else 0

    confidences = [p["confidence"] for p in run1_proposals if p["tag_name"] != "Uncategorized"]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0

    run1_map = {}
    for p in run1_proposals:
        for nid in p["note_ids"]:
            run1_map[nid] = p["tag_name"]

    run2_map = {}
    for p in run2_proposals:
        for nid in p["note_ids"]:
            run2_map[nid] = p["tag_name"]

    stable_count = 0
    for nid, tag1 in run1_map.items():
        if run2_map.get(nid) == tag1:
            stable_count += 1

    stability_pct = (stable_count / total_notes * 100) if total_notes else 0

    peak_rss = max(start_rss, end_rss)
    peak_vram = max(start_vram, end_vram)

    print("\n--- Eval Results ---")
    print(f"Tag count: {tag_count}")
    print(f"Uncategorized: {pct_uncategorized:.1f}%")
    print(f"Mean cluster size: {mean_cluster_size:.1f}")
    print(f"Mean confidence: {mean_confidence:.2f}")
    print(f"Primary-tag stability: {stability_pct:.1f}% (target >= 95%)")
    print(f"LLM call count: {run1_llm_calls}")
    print(f"Peak RSS: {peak_rss:.1f} MB")
    if HAS_CUDA:
        print(f"Peak VRAM: {peak_vram:.1f} MB")

    if stability_pct < 95.0:
        print("WARNING: Stability is below 95% threshold.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
