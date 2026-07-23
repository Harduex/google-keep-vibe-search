# Master Implementation Plan — Keep Vibe Search v2

**Audience:** an implementation agent (small model). Follow parts and phases IN ORDER. Run every CHECKPOINT before continuing. Never delete working code until its replacement's checkpoint passes.

**Supersedes:** `tagging_upgrade_plan.md` and `agent_migration_plan.md`. This document is self-contained.

**Hardware:** 12 GB VRAM. Embedding models and the LLM (via Ollama, out-of-process) must never be resident together in our process — free PyTorch models when done with them.

---

# PART 0 — Global rules (apply to EVERY phase)

## 0.1 Configuration discipline — non-negotiable
1. **DO NOT add any environment variables.** `.env` and `.env.example` are frozen. Final acceptance includes `git diff .env.example` → EMPTY.
2. Existing env settings are the only user-facing knobs: `LLM_*`, `EMBEDDING_MODEL`, `ENABLE_AGENT_MODE`, `AGENT_MAX_STEPS`, `MAX_RESULTS`, `SEARCH_THRESHOLD`, etc.
3. **All new tuning values are hardcoded constants** in per-module `constants.py` files, each with a one-line comment. If something *seems* to need an env var, it does not — make it a constant.

## 0.2 Reliability philosophy
- The local LLM (~9B) is given the SMALLEST possible decision space, always with schema validation.
- Deterministic code (math, regex, thresholds) decides everything it can: when to stop, what merges, what's valid.
- Every LLM output is validated; every failure has a graceful fallback; the pipeline never crashes on bad LLM output.

## 0.3 Constants — create these two files first

```python
# app/services/tagging/constants.py
UMAP_N_COMPONENTS = 10
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.0
HDBSCAN_MIN_CLUSTER_SIZE = 12
HDBSCAN_MIN_SAMPLES = 5
SAMPLE_CENTRAL_DOCS = 4
SAMPLE_DIVERSE_DOCS = 4
SAMPLE_DOC_SNIPPET_CHARS = 300
TAG_MERGE_AUTO = 0.85        # >= : merge silently
TAG_MERGE_GRAY_LOW = 0.60    # [0.60, 0.85) : LLM adjudicates -> dashboard approval
MULTILABEL_SIMILARITY = 0.60
NOISE_RESCUE_SIMILARITY = 0.50
CONFIDENCE_AUTO_APPLY = 0.70
MAX_TAGS_PER_NOTE = 3
RANDOM_SEED = 42
```

```python
# app/services/agent/constants.py
COVERAGE_SIM_THRESHOLD = 0.45
COVERAGE_MIN_NOTES = 3
NOVELTY_MIN_RATIO = 0.34
QUERY_MAX_CHARS = 200
MAX_QUERIES_PER_STEP = 3
TOOL_RETRIES = 2
STEP_TIMEOUT_SECONDS = 60
MAX_COLLECTED_NOTES = 40
```

### CHECKPOINT 0
Both files import cleanly. `.env.example` untouched.

---

# PART A — Search foundations (benefits tagging AND agent)

## Phase A1 — Text preprocessing

Notes are currently embedded raw. Create `app/services/tagging/preprocess.py`:

```python
import re

FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
CODEBLOCK_RE   = re.compile(r"```.*?```", re.DOTALL)
URL_RE         = re.compile(r"https?://\S+")
MD_LINK_RE     = re.compile(r"\[([^\]]*)\]\([^)]*\)")
MD_SYNTAX_RE   = re.compile(r"[#*_>`~]+")
WHITESPACE_RE  = re.compile(r"\s+")

def clean_note(text: str) -> str:
    text = FRONTMATTER_RE.sub("", text)
    text = CODEBLOCK_RE.sub(" ", text)
    text = MD_LINK_RE.sub(r"\1", text)
    text = URL_RE.sub(" ", text)
    text = MD_SYNTAX_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()
```

Rules: ingest stores BOTH raw text (display, LLM samples) and cleaned text (embeddings, BM25, c-TF-IDF). Nothing embeds raw text after this phase.

### CHECKPOINT A1
Unit test: note with URL, markdown link, and code block → artifacts gone, words preserved.

## Phase A2 — Multilingual BM25 (port from agentic-notebook)

Source: the user's own repo `github.com/Harduex/agentic-notebook`, file `skills/agentic-notebook/scripts/search_index.py` (MIT). Port — do not reinvent — into `app/services/search/bm25.py`:

1. The `tokenize()` function and its helpers: Unicode word regex, CJK bigram ranges, light English stemming, casefolding. This tokenizer handles Cyrillic correctly — REQUIRED for mixed Bulgarian/English notes. Do not replace it with `.split()` or `rank_bm25` defaults.
2. The BM25 scoring math (k1/b as in the source).
3. Adapt storage: index lives in memory, built at ingest over CLEANED note texts, rebuilt when notes change (reuse the existing ingest hooks). No `.notebook/` folder, no pickle cache in v1.

API: `bm25_search(query: str, k: int) -> list[tuple[note_id, score]]`.

### CHECKPOINT A2
Query in Bulgarian matches a Bulgarian note; query "keyboards" matches a note containing "keyboard" (stemming); scores are finite and ordered.

## Phase A3 — Hybrid fusion in search_service

In `search_service.search()`:
1. Run dense search (existing embeddings) → ranked list A.
2. Run `bm25_search` → ranked list B.
3. Fuse with the EXISTING RRF implementation (same one used for image search): `score(d) = Σ 1/(60 + rank_i(d))`.
4. Remove the old ad-hoc "keyword overlap" blending — RRF replaces it.
5. Image search, when enabled, joins the same RRF fusion as a third list.

### CHECKPOINT A3
For 5 test queries (2 Bulgarian, 3 English): hybrid results are a superset-or-better of dense-only (manual relevance eyeball). Exact-word queries (a rare term appearing verbatim in one note) now rank that note top-3.

---

# PART B — Tagging pipeline v2

## Phase B1 — Embedding cache

`app/services/tagging/embed.py`: cache keyed by `sha256(cleaned_text)`, JSON file in the existing `./cache/` dir (constant `TAG_EMBED_CACHE = "cache/tag_embeddings.json"` in code — not env). Always `normalize_embeddings=True`. After encoding, `del model; gc.collect(); torch.cuda.empty_cache()`.

### CHECKPOINT B1
Second run on same notes performs zero encodes (log "0 to embed") and returns identical arrays.

## Phase B2 — UMAP + HDBSCAN clustering

`app/services/tagging/cluster.py` (replaces the direct HDBSCAN call in `categorization_service`):

```python
def cluster_notes(embeddings):
    reduced = umap.UMAP(n_components=UMAP_N_COMPONENTS, n_neighbors=UMAP_N_NEIGHBORS,
                        min_dist=UMAP_MIN_DIST, metric="cosine",
                        random_state=RANDOM_SEED).fit_transform(embeddings)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
                                min_samples=HDBSCAN_MIN_SAMPLES,
                                prediction_data=True)
    labels = clusterer.fit_predict(reduced)
    return labels, clusterer.probabilities_

def compute_centroids(embeddings, labels):
    # ORIGINAL embedding space, unit-normalized. NEVER do similarity math in UMAP space.
    ...
```

Rules: log cluster count, sizes, noise %. If noise > 40% or clusters < 5: halve `min_cluster_size` ONCE, retry ONCE, then proceed regardless and report.

### CHECKPOINT B2
Full vault: noise ≤ 40%; rerun with same seed → identical labels.

## Phase B3 — Representative sampling (MMR)

`app/services/tagging/sampling.py`: keep/refactor the existing MMR into: `SAMPLE_CENTRAL_DOCS` nearest-centroid + `SAMPLE_DIVERSE_DOCS` via MMR (λ=0.5). Per selected note, the LLM receives title + first `SAMPLE_DOC_SNIPPET_CHARS` chars of RAW text. Never full notes, never the whole cluster.

### CHECKPOINT B3
For one cluster, print the 8 titles: 4 near-identical in topic, 4 varied but on-topic.

## Phase B4 — LLM tag naming (sequential, constrained)

`app/services/tagging/naming.py`. Replaces concurrent naming — clusters are named **sequentially, largest first**, and each accepted tag is appended to the `existing_tags` shown in the next prompt.

Prompt (verbatim):
```
You are naming a group of similar personal notes with a short tag.

KEYWORDS extracted from this group: {keywords}

SAMPLE NOTES from this group:
{samples}

EXISTING TAGS in this vault (reuse one if it fits well):
{existing_tags}

Rules:
- Output a tag of 1 to 3 words.
- Prefer reusing an EXISTING TAG when it accurately describes the group.
- Be specific ("mechanical keyboards"), not generic ("technology", "notes", "misc").
- Output ONLY the tag. No explanation, no punctuation, no quotes.
```

Enforcement: structured output via PydanticAI (see Part C model factory — reuse `build_agent_model()`):

```python
class TagName(BaseModel):
    tag: str = Field(..., max_length=40)
```

Validation in code:
```python
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9 &\-]{0,39}$")
BANNED = {"misc", "notes", "general", "other", "stuff", "various", "topics"}
# lowercase, strip quotes/period; reject BANNED, >3 words, regex fail
```
On failure: one retry with the reason appended; then fall back to top-2 c-TF-IDF keywords joined by a space + warning log. Never crash.

### CHECKPOINT B4
All clusters named, zero crashes, zero BANNED tags, all pass validation.

## Phase B5 — Deterministic tag dedupe (auto tier)

`app/services/tagging/dedupe.py`, in this order:
1. Normalize (lowercase, strip, collapse whitespace) → merge exact dupes.
2. Plural rule: `a + "s" == b` → keep shorter.
3. Embed tag strings (same embedding model; batch this BEFORE freeing it in B1's flow, or reload briefly). For pairs with cosine ≥ `TAG_MERGE_AUTO` (0.85): **merge silently, no user approval** — keep the tag of the larger cluster.
4. Record `{old: canonical}` mapping; remap clusters. Merging renames tags; it never merges clusters or notes.
5. Pairs with cosine in `[TAG_MERGE_GRAY_LOW, TAG_MERGE_AUTO)` → collect into `gray_pairs` for B6. Pairs below 0.60 → keep, LLM never sees them.

### CHECKPOINT B5
Synthetic input `["keyboards", "keyboard", "mechanical keyboards", "cooking"]` → first two merged automatically, "mechanical keyboards" lands in gray_pairs, "cooking" untouched.

## Phase B6 — LLM gray-zone adjudication (ONE call) + dashboard approval

Schema:
```python
class MergeDecision(BaseModel):
    tag_a: str
    tag_b: str
    verdict: Literal["merge", "keep_both"]
    canonical: str | None = None   # required iff verdict == "merge"

class DedupeReview(BaseModel):
    decisions: list[MergeDecision]
```

One LLM call listing all gray pairs, each with its two tags AND note counts. Prompt instructs: merge only true duplicates/synonyms; a subtopic vs. its parent topic ("guitar" vs "music gear") is `keep_both`; `canonical` must be one of the two tags, prefer the larger.

**Hard validation in code** — any decision failing ANY rule defaults to `keep_both`:
- (tag_a, tag_b) must be a pair we sent (no invented pairs)
- `canonical` ∈ {tag_a, tag_b} (no invented names)
- every sent pair must be decided; missing → keep_both

Flow: verdicts are NOT applied to disk. Stream them as proposals to the existing `OrganizeDashboard` (same `Protocol.proposals` mechanism) as "Merge X into Y? (n + m notes)" with approve/reject. Auto-merges from B5 are already applied and merely listed as informational.

### CHECKPOINT B6
Synthetic gray set: one true duplicate pair → merge with valid canonical; one parent/child pair → keep_both; one hand-crafted invalid LLM response (hallucinated canonical) → code defaults it to keep_both without error.

## Phase B7 — Assignment: multi-label + noise rescue

`app/services/tagging/assign.py`:
- Every note: cosine vs all centroids (original space). All tags with sim ≥ `MULTILABEL_SIMILARITY` assigned, capped at `MAX_TAGS_PER_NOTE`, primary first.
- Clustered notes: primary = own cluster's tag; confidence = HDBSCAN probability; `review = confidence < CONFIDENCE_AUTO_APPLY`.
- Noise notes (label −1): nearest centroid; if sim ≥ `NOISE_RESCUE_SIMILARITY` adopt its tag with `review = True`; else untagged + review.
- Only non-review assignments are auto-applied; review items go to the dashboard proposals (same UI as B6).

### CHECKPOINT B7
Summary printed: % tagged, % multi-tag, % review, % untagged. Untagged < 10% (else lower rescue threshold by 0.05 ONCE and report).

## Phase B8 — Orchestration + incremental mode

Order: load → clean → embed(cache) → cluster → centroids → c-TF-IDF(cleaned) → sample → name(sequential) → dedupe(auto) → gray-zone(LLM→dashboard) → assign → apply+proposals → save manifest.

Manifest `cache/tag_manifest.json`: run date, constants snapshot, per-cluster {tag, size, centroid, keywords}.

Incremental (new/changed notes only, detected by hash): embed → assign vs manifest centroids. NO clustering, NO LLM. If >20% of vault is new: log "recommend full re-run", proceed anyway.

Tag-name stability on full re-runs: match new centroids to manifest centroids; cosine ≥ 0.9 → REUSE old tag, skip LLM for that cluster.

### CHECKPOINT B8
(1) Full run clean. (2) Immediate second full run: ≥95% of notes keep their primary tag. (3) One new note + incremental: correct existing tag, zero LLM calls. (4) VRAM peak < 12 GB.

---

# PART C — Agent migration (NoteAgent → PydanticAI)

## Phase C1 — Dependency + model factory

Install `pydantic-ai-slim[openai]` (NOT the full metapackage).

```python
# app/services/agent/model_factory.py
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from app.config import settings

def build_agent_model() -> OpenAIChatModel:
    base_url = settings.LLM_API_BASE_URL
    if settings.LLM_PROVIDER == "ollama" and not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    return OpenAIChatModel(settings.LLM_MODEL,
        provider=OpenAIProvider(base_url=base_url,
                                api_key=settings.LLM_API_KEY or "ollama"))
```

LiteLLM remains for final chat generation. This factory serves the agent loop AND Part B naming calls only.

### CHECKPOINT C1
Throwaway script: `Agent(build_agent_model()).run_sync("say ok")` works against configured Ollama. Delete script.

## Phase C2 — Deterministic coverage (replaces evaluate_coverage)

`app/services/agent/coverage.py` — pure math, no LLM:

```python
def coverage_is_sufficient(query_embedding, collected_embeddings,
                           last_batch_size, last_batch_new,
                           steps_taken, max_steps) -> tuple[bool, str]:
    if steps_taken >= max_steps:                    return True, "max steps reached"
    if len(collected_embeddings) >= MAX_COLLECTED_NOTES: return True, "note limit reached"
    if len(collected_embeddings) < COVERAGE_MIN_NOTES:   return False, "too few notes collected"
    if last_batch_size > 0 and (last_batch_new / last_batch_size) < NOVELTY_MIN_RATIO:
        return True, "searches returning mostly duplicates"
    sims = np.stack(collected_embeddings) @ query_embedding
    if float(np.mean(np.sort(sims)[-COVERAGE_MIN_NOTES:])) >= COVERAGE_SIM_THRESHOLD:
        return True, "collected notes match query well"
    return False, "coverage below threshold"
```

### CHECKPOINT C2
Unit tests: each stop reason + the keep-going path.

## Phase C3 — Decision schema with synonym sweep (up to 3 queries)

```python
# app/services/agent/decision.py
class SearchDecision(BaseModel):
    """The next search action against the user's notes."""
    tool: Literal["search_notes", "search_chunks", "filter_by_tag"]
    queries: list[str] = Field(..., min_length=1, max_length=MAX_QUERIES_PER_STEP,
        description="1-3 differently-worded probes for the SAME information need: "
                    "synonyms, entity names, and the notes' likely language/wording. "
                    "For filter_by_tag: exactly one item, the exact tag name.")
    reasoning: str = Field(..., max_length=300)

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, v):
        v = [q.strip() for q in v if q.strip()]
        if not v: raise ValueError("at least one non-empty query")
        if any(len(q) > QUERY_MAX_CHARS for q in v): raise ValueError("query too long")
        # dedupe case-insensitively, preserve order
        seen, out = set(), []
        for q in v:
            if q.lower() not in seen: seen.add(q.lower()); out.append(q)
        return out
```

Execution rule: the chosen tool runs ONCE PER QUERY in the list; results are merged and deduped by note_id before counting novelty. `filter_by_tag` with >1 query → use only the first, log a warning.

Design rule (do not deviate): NO `respond` tool, NO `evaluate_coverage` tool. Stopping is C2's job. This enum + list + string is the LLM's entire decision space.

### CHECKPOINT C3
Schema accepts 1–3 queries; rejects empty list, blank strings, >3, over-long; dedupes case-insensitive duplicates.

## Phase C4 — The agent loop

`app/services/agent/pydantic_agent.py`. Same generator contract as old NoteAgent (yields AgentStep..., then AgentResult) so chat_service changes stay minimal.

State:
```python
@dataclass
class AgentRunState:
    query: str
    collected: dict[str, dict] = field(default_factory=dict)
    collected_embeddings: list = field(default_factory=list)
    past_queries: list[str] = field(default_factory=list)   # fixes repeat-search bug
    steps_taken: int = 0
```

Step prompt:
```
You are gathering context from a personal notes database to answer:
"{query}"

Searches already performed (DO NOT repeat these or trivial variations):
{past_queries}

Notes collected so far ({n_collected} total), most recent titles:
{recent_titles}

Decide the single next search that would add the most NEW relevant information.
Provide 1-3 differently-worded queries for it: synonyms, entity names, and the
notes' likely wording. If the notes may be in another language than the
question (e.g. Bulgarian vs English), include a probe in that language, and
for inflected languages include an inflected variant.
```

Agent: `Agent(build_agent_model(), output_type=SearchDecision, retries=TOOL_RETRIES, model_settings={"temperature": settings.LLM_TEMPERATURE})`.

Loop (per iteration):
1. `coverage_is_sufficient(...)` → if stop: yield `AgentStep(action="respond", reasoning=reason)`, break.
2. Run decision agent with `asyncio.wait_for(..., STEP_TIMEOUT_SECONDS)`. ANY exception → yield `AgentStep(action="error", reasoning=...)`, break (graceful: respond with what we have; never raise into chat_service).
3. Code-level duplicate guard: drop any query case-insensitively equal to a past query; if all dropped, count the step with `last_batch_new = 0` (novelty rule then ends the loop).
4. Execute tool once per remaining query; merge results by note_id; update collected, embeddings (from the EXISTING ingest-time cache — `embed_fn_cached` looks up, never re-encodes; only the user's question is encoded fresh, once per run), past_queries (`"{tool}: {q}"` each), steps_taken.
5. Yield `AgentStep(action=tool, reasoning=..., notes_found=len(new))`.

Finally: `yield AgentResult(list(state.collected.values()))`.

### CHECKPOINT C4
Integration test with PydanticAI `TestModel` + stub tools: multi-query step merges results; duplicate query dropped; loop ends via novelty; well-formed step sequence ending in AgentResult. No network.

## Phase C5 — Grounded generation in chat_service

### C5.1 Wiring
Swap `NoteAgent` → `PydanticNoteAgent` where constructed. Two protocol changes:
- Map `action="error"` steps to `Protocol.agent_step("error", ...)` AND continue to generation with collected notes — never dead-end the stream.
- Every emitted protocol line gets a per-request monotonic `seq` integer.
`ENABLE_AGENT_MODE=false` path must be byte-identical to before.

### C5.2 Grounding Contract → generation prompt
Append this block (verbatim) to the system/context prompt built by `context_builder.build()`:

```
GROUNDING RULES:
1. The notes provided above are your ONLY source of facts. General knowledge may
   shape language and structure, never facts.
2. Every factual claim must cite its note as [Note #N].
3. If the notes do not contain the answer, say plainly: "Your notes don't mention
   this." Then point to the closest related notes that ARE present. Never fill
   gaps silently.
4. If you add anything beyond the notes, fence it visibly: "Outside your notes: ...".
5. Preserve the notes' own wording for numbers, names, and hedges. If a note says
   "may", never write "does".
6. If the provided notes conflict with each other, present both sides with their
   citations and say the disagreement exists. Do not silently pick one.
```

Rule 6 pairs with the existing `detect_conflicts` output: when conflicts were detected, list them explicitly in the context block so the model addresses them.

### C5.3 Citation verification (deterministic, post-generation)
After `full_response` is assembled, before `Protocol.done`:

```python
CITE_RE = re.compile(r"\[Note #(\d+)\]")

def verify_citations(text: str, retrieved_count: int) -> tuple[str, list[int], list[int]]:
    """Returns (cleaned_text, valid_ids, invalid_ids). Invalid = id out of range."""
    cited = sorted({int(m) for m in CITE_RE.findall(text)})
    valid = [i for i in cited if 1 <= i <= retrieved_count]
    invalid = [i for i in cited if i not in valid]
    for i in invalid:
        text = text.replace(f"[Note #{i}]", "")   # strip hallucinated citations
    return text, valid, invalid
```

Emit `Protocol.done(cleaned_text, citations=valid)`; if `invalid` non-empty, log a warning and include a `citation_warnings` count in the done payload (additive field — protocol stays backward compatible).

### CHECKPOINT C5
Live against Ollama, 5 varied questions in agent mode: NDJSON stream well-formed (phases ordered, seq gapless, steps present, done has citations). One question deliberately unanswerable from the vault → response contains "don't mention" honesty, not invented facts. A forced hallucinated `[Note #99]` (injected in a test) is stripped. `ENABLE_AGENT_MODE=false` unchanged.

## Phase C6 — Delete the old agent

Only after C5 passes:
- Delete `note_agent.py`, its JSON-fallback/regex parsers, `AGENT_SYSTEM_PROMPT` if unused.
- Delete `evaluate_coverage` and `respond` tool implementations + schemas.
- `grep -r "NoteAgent\|evaluate_coverage" app/ tests/` → empty.
- README: document the new agent (3 tools, 1–3 query probes, deterministic stopping, constants not env).

### CHECKPOINT C6
Test suite green, grep clean, app answers in both modes.

---

# PART D — Frontend (small, contained)

In `useChat.ts` / chat components:
1. Buffer `delta` text in a ref; flush to state on `requestAnimationFrame` (kills the per-chunk re-render debt).
2. Track `seq`; on a gap, `console.warn` only (observability, no UX change).
3. Render `agent_step` with `action === "error"` as a subdued inline notice ("Search assistant hit a snag — answering from notes found so far"); the stream must continue rendering normally.
4. OrganizeDashboard: render the new merge proposals from B6 ("Merge X into Y? (n + m notes)") with the existing approve/reject handlers; render B7 review-queue assignments the same way.

### CHECKPOINT D
Kill Ollama mid-run → notice shown, response still completes from collected notes, no frozen spinner. Long answers stream smoothly. A gray-zone merge round-trips: approve in UI → tags updated.

---

# PART E — Final acceptance

1. Full tagging run + immediate rerun: ≥95% primary-tag stability; untagged <10%; VRAM <12 GB.
2. 10-question chat benchmark (mix BG/EN) in agent mode: zero crashes, zero frozen streams, no repeated identical searches (check past_queries logs), citations all valid.
3. One unanswerable question → honest "your notes don't mention this".
4. `git diff .env.example` → EMPTY. `pip list` has no langchain/langgraph/smolagents.
5. Incremental tagging of one new note: correct tag, zero LLM calls.

---

# Explicit non-goals — DO NOT implement
- No new env vars or config sections (constants.py only).
- No note merging or note deletion, ever — duplicate NOTES are report-only (future).
- No LangGraph/Smolagents/Pi; no MCP; no sub-agents, planning, or self-reflection loops.
- No migration of final chat generation off LiteLLM.
- No hierarchical/nested tags; no Studio artifact exports; no suggested-questions empty state (all deferred).
- No streaming of the decision LLM's tokens (only final generation streams).
- No retry loops beyond those specified (PydanticAI retries; the single retries in B2/B4/B7).

# Priority order if time-constrained
1. Part A (cleaning + hybrid search) — improves everything downstream
2. C1–C4 (reliable agent core)
3. B1–B4 (tagging core) and C5 (grounded generation) — parallel-safe, different services
4. B5–B8, C6, D — dedupe tiers, cleanup, frontend polish
