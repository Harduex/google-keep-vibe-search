# 3D Visualization Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the 3D notes view: UMAP layout, instanced rendering, filter-driven visibility, 8-slot tag colors with an interactive legend, and per-note connection discovery (similarity / shared tags / shared entities) with multi-hop expansion.

**Architecture:** Backend swaps PCA for UMAP in `/api/embeddings` (cached by embedding hash, PCA fallback) and adds `GET /api/notes/{id}/connections` computed from in-memory data. Frontend replaces per-note `<mesh>` spheres with one `instancedMesh` (+ one ghost mesh + one `LineSegments` for edges); all buffer derivation lives in pure functions (`sceneData.ts`) that carry the unit tests; a side panel hosts selection details, layer toggles, and the interactive legend.

**Tech Stack:** FastAPI, numpy, umap-learn (already a dependency), scikit-learn; React 19, @react-three/fiber, @react-three/drei, three, vitest.

**Spec:** `docs/superpowers/specs/2026-07-30-3d-visualization-redesign-design.md`

## Global Constraints

- **STRICT PRIVACY BOUNDARY (AGENTS.md):** never read/print/log real note contents; tests use synthetic fixtures only; the autouse `isolate_cache_dir` fixture isolates the cache — never bypass it. Debug logging: structural metadata only (counts, shapes, ids, timings, exception types).
- Backend tests: `uv run pytest tests/<file> -v`. Frontend tests: `cd client && npx vitest run <path>`. Full gate: `make test`, `make lint`.
- Do not lower any dependency pin in `pyproject.toml` (pins are security floors). `umap-learn>=0.5.12` is already installed — no dependency changes needed.
- Commits: conventional-commit style, no Co-Authored-By trailer, never push.
- Public component API stays: `<Visualization searchResults={Note[]} onSelectNote={(id) => void} isAllNotesView?>` — `Results.tsx` and `AllNotes/index.tsx` are NOT modified.

## File Structure

```
app/routes/embeddings.py            — modify: UMAP projection, trimmed payload
app/routes/connections.py           — create: GET /api/notes/{id}/connections
app/main.py                         — modify: register connections router
tests/test_connections_route.py     — create
tests/test_api_integration.py       — modify: embeddings payload assertions

client/src/components/Visualization/
  index.tsx          — rewrite: state, filtering, wiring
  Scene.tsx          — create: Canvas, instanced points, edges, picking
  SidePanel.tsx      — create: selection, layers, legend, tag picker, controls
  sceneData.ts       — create: pure buffer/derivation helpers (unit-tested)
  useConnections.ts  — create: multi-note connections fetch + cache
  tagColors.ts       — modify: 8 slots
  styles.css         — modify: panel/tooltip/legend styles
  EmbeddingsVisualization.tsx — DELETE (Task 8)
  VisualizationControls.tsx   — DELETE (Task 8)
  __tests__/tagColors.test.ts    — modify
  __tests__/sceneData.test.ts    — create
  __tests__/useConnections.test.ts — create
  __tests__/SidePanel.test.tsx   — create
client/src/hooks/useEmbeddings.ts — modify: `content` → `snippet`
client/src/const.ts               — modify: add NOTE_CONNECTIONS route
```

---

### Task 1: Backend — UMAP layout and trimmed embeddings payload

**Files:**
- Modify: `app/routes/embeddings.py`
- Modify: `tests/test_api_integration.py` (the `test_embeddings_carry_tags_for_colouring` test, ~line 168)
- Modify: `client/src/hooks/useEmbeddings.ts` (type only, keeps the build green)
- Modify: `client/src/components/Visualization/EmbeddingsVisualization.tsx` (two `point.content` references — file is deleted later in Task 8, but must compile until then)

**Interfaces:**
- Produces: `GET /api/embeddings` → `{"embeddings": [{"id": str, "title": str, "snippet": str (≤120 chars), "tags": [str], "coordinates": [float, float, float]}]}`. No `content` key.
- Produces (frontend): `EmbeddingPoint = { id: string; title: string; snippet: string; tags: string[]; coordinates: [number, number, number] }`

- [ ] **Step 1: Write the failing tests**

Replace/extend the embeddings assertions in `tests/test_api_integration.py` (keep the existing tag assertion, add payload-shape assertions):

```python
def test_embeddings_payload_is_trimmed_and_3d(client):
    """Points carry a bounded snippet instead of the full content, and 3D coordinates.

    The full-content payload was many MB at real corpus scale and the view never
    displayed more than a hover line of it.
    """
    resp = client.get("/api/embeddings")
    assert resp.status_code == 200
    points = resp.json()["embeddings"]
    assert len(points) > 0
    for point in points:
        assert set(point) == {"id", "title", "snippet", "tags", "coordinates"}
        assert "content" not in point
        assert len(point["snippet"]) <= 120
        assert len(point["coordinates"]) == 3


def test_embeddings_fall_back_to_pca_when_umap_fails(client, monkeypatch):
    """A UMAP failure must not 500 the endpoint — PCA is the fallback layout."""
    import app.routes.embeddings as emb_route

    emb_route.get_cached_projection.cache_clear()

    def boom(**kwargs):
        raise RuntimeError("synthetic umap failure")

    import umap

    monkeypatch.setattr(umap, "UMAP", boom)
    resp = client.get("/api/embeddings")
    assert resp.status_code == 200
    points = resp.json()["embeddings"]
    assert all(len(p["coordinates"]) == 3 for p in points)
    emb_route.get_cached_projection.cache_clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_integration.py -k "embeddings" -v`
Expected: `test_embeddings_payload_is_trimmed_and_3d` FAILS (payload has `content`, no `snippet`). The fallback test fails or errors (UMAP not used yet).

- [ ] **Step 3: Implement**

Rewrite `app/routes/embeddings.py`:

```python
import hashlib
from functools import lru_cache

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sklearn.decomposition import PCA

from app.core.dependencies import get_search_service
from app.core.redact import safe_exc
from app.search import VibeSearch
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["embeddings"])

SNIPPET_LEN = 120


@lru_cache(maxsize=1)
def get_cached_projection(embeddings_hash: str, engine: VibeSearch) -> np.ndarray:
    """3D layout for the point cloud, cached per embedding-matrix hash.

    UMAP is the layout of record — it separates the clusters PCA smears into one
    blob. PCA stays as the fallback for degenerate inputs (tiny corpora, UMAP
    runtime failures); the warning logs only the exception type, never data.
    """
    embeddings = np.ascontiguousarray(engine.embeddings)
    try:
        import umap

        reducer = umap.UMAP(n_components=3, n_neighbors=15, min_dist=0.1, random_state=42)
        return reducer.fit_transform(embeddings)
    except Exception as e:
        print(f"[embeddings] UMAP failed ({type(e).__name__}); falling back to PCA")
        return PCA(n_components=3).fit_transform(embeddings)


@router.get("/embeddings")
def get_embeddings(search_service: SearchService = Depends(get_search_service)):
    try:
        note_indices = search_service.note_indices
        notes = search_service.notes

        # Cache key for the projection fit: hash the embedding matrix itself rather
        # than the corpus. It is what the reducer consumes, so it changes exactly
        # when the projection would.
        emb_hash = hashlib.md5(np.ascontiguousarray(search_service.engine.embeddings)).hexdigest()
        embeddings_3d = get_cached_projection(emb_hash, search_service.engine)

        data = []
        for i, note_idx in enumerate(note_indices):
            note = notes[note_idx]
            data.append(
                {
                    "id": note["id"],
                    "title": note["title"],
                    # A bounded snippet, not the content: the view shows at most a
                    # hover line, and the full corpus is many MB.
                    "snippet": (note.get("content") or "")[:SNIPPET_LEN],
                    # Resolved through the service, not off the note dict: the engine's
                    # notes are never tag-enriched, so `note.get("tags")` was [] for every
                    # point and the map had nothing to colour by.
                    "tags": search_service.tags_for(note),
                    "coordinates": embeddings_3d[i].tolist(),
                }
            )
        return {"embeddings": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embeddings: {safe_exc(e)}")
```

Note: the first UMAP call in a fresh environment JIT-compiles numba kernels (tens of seconds once, then cached on disk). Do not mistake that for a hang.

- [ ] **Step 4: Keep the frontend compiling**

In `client/src/hooks/useEmbeddings.ts`, replace the `content` field:

```ts
export interface EmbeddingPoint {
  id: string;
  title: string;
  /** First ~120 chars of the note, for hover labels only. */
  snippet: string;
  /** Tags the note carries, resolved server-side from the tag map (used to colour points). */
  tags: string[];
  coordinates: [number, number, number];
}
```

In `client/src/components/Visualization/EmbeddingsVisualization.tsx` replace the one hover-text reference `point.title || point.content.substring(0, 100) + '...'` with `point.title || point.snippet` (this file is deleted in Task 8; it just has to compile until then).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_integration.py -k "embeddings" -v && cd client && npx tsc -b --noEmit 2>/dev/null || npx tsc --noEmit`
Expected: PASS, and the client typechecks.

- [ ] **Step 6: Commit**

```bash
git add app/routes/embeddings.py tests/test_api_integration.py client/src/hooks/useEmbeddings.ts client/src/components/Visualization/EmbeddingsVisualization.tsx
git commit -m "feat(viz): switch the 3D layout to UMAP and trim the embeddings payload"
```

---

### Task 2: Backend — per-note connections endpoint

**Files:**
- Create: `app/routes/connections.py`
- Modify: `app/main.py` (register router)
- Create: `tests/test_connections_route.py`

**Interfaces:**
- Produces: `GET /api/notes/{note_id}/connections?k=10` →

```json
{
  "id": "<note_id>",
  "similar":         [{"id": "...", "title": "...", "score": 0.87}],
  "shared_tags":     [{"tag": "Label6",   "notes": [{"id": "...", "title": "..."}]}],
  "shared_entities": [{"entity": "Paris", "notes": [{"id": "...", "title": "..."}]}]
}
```

`k` ∈ [1, 50] caps `similar`; each tag/entity group is capped at 10 notes; groups sorted alphabetically; 404 for an unknown id; empty lists are valid results. Entities come from `request.app.state.entity_service.entity_index` (canonical → set of note ids); absent service ⇒ empty `shared_entities`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_connections_route.py`. The `client` fixture (see `tests/conftest.py`) boots the wired app over the 30 synthetic fixture notes with stub models — never real data.

```python
"""Connections endpoint: similarity / shared tags / shared entities for one note.

All assertions run against the synthetic fixture corpus (30 notes, stub embedder,
stub spaCy) — never real notes.
"""


def _points(client):
    resp = client.get("/api/embeddings")
    assert resp.status_code == 200
    return resp.json()["embeddings"]


def test_connections_shape_and_similarity(client):
    points = _points(client)
    note_id = points[0]["id"]

    resp = client.get(f"/api/notes/{note_id}/connections?k=5")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"id", "similar", "shared_tags", "shared_entities"}
    assert body["id"] == note_id

    assert 0 < len(body["similar"]) <= 5
    scores = [n["score"] for n in body["similar"]]
    assert scores == sorted(scores, reverse=True)
    assert all(set(n) == {"id", "title", "score"} for n in body["similar"])
    # Never connects a note to itself.
    assert note_id not in [n["id"] for n in body["similar"]]


def test_connections_shared_tags(client):
    # Fixture notes 6-8 each carry a distinct label (Label6..Label8), so a tagged
    # note's groups only ever contain tags it actually has.
    points = _points(client)
    tagged = next(p for p in points if p["tags"])

    resp = client.get(f"/api/notes/{tagged['id']}/connections")
    assert resp.status_code == 200
    groups = resp.json()["shared_tags"]
    assert all(g["tag"] in tagged["tags"] for g in groups)
    for g in groups:
        assert len(g["notes"]) <= 10
        assert tagged["id"] not in [n["id"] for n in g["notes"]]


def test_connections_unknown_note_is_404(client):
    resp = client.get("/api/notes/no-such-note/connections")
    assert resp.status_code == 404


def test_connections_k_is_validated(client):
    points = _points(client)
    resp = client.get(f"/api/notes/{points[0]['id']}/connections?k=0")
    assert resp.status_code == 422
    resp = client.get(f"/api/notes/{points[0]['id']}/connections?k=51")
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_connections_route.py -v`
Expected: FAIL — 404 on every request (route does not exist yet; FastAPI returns 404, making `test_connections_unknown_note_is_404` a false pass — the other three failing proves the route is missing).

- [ ] **Step 3: Implement**

Create `app/routes/connections.py`:

```python
from typing import Any, Dict

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.dependencies import get_search_service
from app.core.redact import safe_exc
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["connections"])

MAX_PER_GROUP = 10


def _ref(note: Dict[str, Any]) -> Dict[str, str]:
    return {"id": note["id"], "title": note.get("title", "")}


@router.get("/notes/{note_id}/connections")
def get_connections(
    note_id: str,
    request: Request,
    k: int = Query(default=10, ge=1, le=50),
    search_service: SearchService = Depends(get_search_service),
):
    """Meaningful connections for one note, computed on demand from in-memory data.

    Three independent edge sets: cosine-nearest notes by embedding, notes sharing a
    tag, and notes sharing a named entity. Empty lists are valid results.
    """
    try:
        notes = search_service.notes
        note_indices = search_service.note_indices
        row_by_id = {notes[idx]["id"]: row for row, idx in enumerate(note_indices)}
        note_by_id = {notes[idx]["id"]: notes[idx] for idx in note_indices}
        if note_id not in row_by_id:
            raise HTTPException(status_code=404, detail="Note not found")

        # --- similar: top-k cosine neighbours over the embedding matrix ---
        emb = np.asarray(search_service.embeddings, dtype=np.float32)
        target = emb[row_by_id[note_id]]
        denom = np.linalg.norm(emb, axis=1) * np.linalg.norm(target)
        sims = emb @ target / np.maximum(denom, 1e-12)
        id_by_row = {row: nid for nid, row in row_by_id.items()}
        similar = []
        for row in np.argsort(-sims):
            nid = id_by_row[int(row)]
            if nid == note_id:
                continue
            similar.append({**_ref(note_by_id[nid]), "score": round(float(sims[row]), 4)})
            if len(similar) >= k:
                break

        # --- shared tags: one group per tag the target note carries ---
        target_tags = sorted(set(search_service.tags_for(note_by_id[note_id])))
        shared_tags = []
        for tag in target_tags:
            group = []
            for nid, note in note_by_id.items():
                if nid == note_id:
                    continue
                if tag in search_service.tags_for(note):
                    group.append(_ref(note))
                    if len(group) >= MAX_PER_GROUP:
                        break
            if group:
                shared_tags.append({"tag": tag, "notes": group})

        # --- shared entities: via the entity index (canonical -> note ids) ---
        shared_entities = []
        entity_service = getattr(request.app.state, "entity_service", None)
        if entity_service is not None:
            for canonical in sorted(entity_service.entity_index):
                ids = entity_service.entity_index[canonical]
                if note_id not in ids:
                    continue
                group = [
                    _ref(note_by_id[nid])
                    for nid in sorted(ids)
                    if nid != note_id and nid in note_by_id
                ][:MAX_PER_GROUP]
                if group:
                    shared_entities.append({"entity": canonical, "notes": group})

        return {
            "id": note_id,
            "similar": similar,
            "shared_tags": shared_tags,
            "shared_entities": shared_entities,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing connections: {safe_exc(e)}")
```

In `app/main.py`, extend the existing import and registration:

```python
from app.routes import chat, connections, embeddings, images, imports, notes, organize, search, stats, tags
```

and next to the other routers:

```python
app.include_router(connections.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_connections_route.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/routes/connections.py app/main.py tests/test_connections_route.py
git commit -m "feat(viz): add per-note connections endpoint (similarity, tags, entities)"
```

---

### Task 3: Frontend — 8-slot tag color scale

**Files:**
- Modify: `client/src/components/Visualization/tagColors.ts`
- Modify: `client/src/components/Visualization/__tests__/tagColors.test.ts`

**Interfaces:**
- Produces: `MAX_TAG_SLOTS = 8`; `buildTagColorScale(points, mode)` keeps its signature and return type (`{ colorFor, legend }`). Existing consumers keep working.

- [ ] **Step 1: Update the tests (failing first)**

In `tagColors.test.ts`, the first test currently proves 3 slots. Replace its point set so 8 distinct tags win slots and a 9th folds into Other, and keep every other test unchanged (they are slot-count-agnostic):

```ts
it('gives the most common tags a hue each and folds the rest into Other', () => {
  const slotTags = ['Recipes', 'Travel', 'Work', 'Books', 'Health', 'Music', 'Ideas', 'Home'];
  const points = [
    // Descending counts: Recipes ×9, Travel ×8, ... Home ×2 — then Rare ×1.
    ...slotTags.flatMap((tag, i) => Array.from({ length: 9 - i }, () => point([tag]))),
    point(['Rare']),
  ];

  const scale = buildTagColorScale(points, 'light');

  const slotColors = slotTags.map((tag) => scale.colorFor([tag]));
  expect(new Set(slotColors).size).toBe(MAX_TAG_SLOTS);
  expect(scale.colorFor(['Rare'])).toBe(OTHER_TAGS_COLOR);
  expect(scale.legend.map((entry) => entry.label)).toEqual([...slotTags, 'Other tags']);
});
```

- [ ] **Step 2: Run tests to verify the updated test fails**

Run: `cd client && npx vitest run src/components/Visualization/__tests__/tagColors.test.ts`
Expected: FAIL — only 3 distinct slot colors exist.

- [ ] **Step 3: Implement**

In `tagColors.ts`, replace the palette block and cap. Rewrite the header comment honestly — the 3-color all-pairs CVD guarantee no longer holds at 8 slots; the design trades it for coverage because identity is never color alone (legend labels, hover names tags, and legend-click isolation from Task 7 disambiguates any pair):

```ts
/**
 * Tag colour assignment for the 3D map.
 *
 * Eight categorical slots (Okabe–Ito derived — the standard colour-vision-aware
 * categorical set, minus its gray, plus a brown). Unlike the previous 3-slot
 * palette, 8 hues cannot guarantee all-pairs CVD separation in a scatter; the
 * design accepts that because identity is never colour alone — the legend labels
 * every swatch, hovering a point names its tags, and clicking a legend swatch
 * isolates a tag outright.
 */

export const UNTAGGED_COLOR = '#9e9e9e';
export const OTHER_TAGS_COLOR = '#6b7280';

const CATEGORICAL = {
  light: ['#0072b2', '#e69f00', '#009e73', '#d55e00', '#cc79a7', '#56b4e9', '#b0a000', '#8c510a'],
  dark: ['#5aa9e6', '#f2b134', '#2fbf91', '#f0703c', '#e39ac2', '#7fd0f7', '#d6c94f', '#b07430'],
} as const;

/** How many tags get a hue of their own before the rest fold into "Other tags". */
export const MAX_TAG_SLOTS = 8;
```

(`#f0e442` pure yellow is swapped for `#b0a000` in light mode — yellow is unreadable on the `#fcfcfb` surface; dark mode keeps a yellow `#d6c94f`.)

Everything else in the file (ranking, ties, `colorFor`, legend assembly) is slot-count-driven and stays unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd client && npx vitest run src/components/Visualization/__tests__/tagColors.test.ts`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/Visualization/tagColors.ts client/src/components/Visualization/__tests__/tagColors.test.ts
git commit -m "feat(viz): extend the tag colour scale to eight categorical slots"
```

---

### Task 4: Frontend — connections types + fetch hook

**Files:**
- Modify: `client/src/const.ts`
- Create: `client/src/components/Visualization/useConnections.ts`
- Create: `client/src/components/Visualization/__tests__/useConnections.test.ts`

**Interfaces:**
- Consumes: `readQuery<T>(key)` / `subscribe(fn)` from `client/src/hooks/dataLayer.ts` (`readQuery` returns `{ data?, error?, isLoading, promise }` and dedupes in-flight requests per key).
- Produces:

```ts
export interface ConnectionNoteRef { id: string; title: string; }
export interface SimilarConnection extends ConnectionNoteRef { score: number; }
export interface TagConnectionGroup { tag: string; notes: ConnectionNoteRef[]; }
export interface EntityConnectionGroup { entity: string; notes: ConnectionNoteRef[]; }
export interface NoteConnections {
  id: string;
  similar: SimilarConnection[];
  shared_tags: TagConnectionGroup[];
  shared_entities: EntityConnectionGroup[];
}
export const connectionsUrl: (noteId: string) => string;
export function useConnectionsFor(ids: string[]): {
  byId: Record<string, NoteConnections>;
  errors: Record<string, string>;
  isLoading: boolean;
};
```

- [ ] **Step 1: Write the failing tests**

Create `__tests__/useConnections.test.ts`:

```ts
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { invalidate } from '@/hooks/dataLayer';

import { connectionsUrl, useConnectionsFor } from '../useConnections';

const CONN = (id: string) => ({
  id,
  similar: [{ id: 'n2', title: 'Two', score: 0.9 }],
  shared_tags: [],
  shared_entities: [],
});

const okResponse = (body: unknown) =>
  ({ ok: true, status: 200, json: () => Promise.resolve(body) }) as Response;

afterEach(() => {
  // The data layer cache is module-global; drop our keys between tests.
  invalidate('/api/notes/');
  vi.unstubAllGlobals();
});

describe('useConnectionsFor', () => {
  it('fetches connections for every id and exposes them by id', async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(okResponse(CONN(url.split('/')[3]))));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useConnectionsFor(['n1']));
    expect(result.current.isLoading).toBe(true);

    await waitFor(() => expect(result.current.byId.n1).toBeDefined());
    expect(result.current.byId.n1.similar[0].id).toBe('n2');
    expect(result.current.isLoading).toBe(false);
    expect(fetchMock).toHaveBeenCalledWith(connectionsUrl('n1'), undefined);
  });

  it('surfaces per-id errors without throwing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false, status: 500, statusText: 'boom' } as Response)),
    );

    const { result } = renderHook(() => useConnectionsFor(['bad']));
    await waitFor(() => expect(result.current.errors.bad).toBeDefined());
    expect(result.current.byId.bad).toBeUndefined();
  });

  it('grows the map as the chain grows, without refetching cached ids', async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(okResponse(CONN(url.split('/')[3]))));
    vi.stubGlobal('fetch', fetchMock);

    const { result, rerender } = renderHook(({ ids }) => useConnectionsFor(ids), {
      initialProps: { ids: ['n1'] },
    });
    await waitFor(() => expect(result.current.byId.n1).toBeDefined());

    act(() => rerender({ ids: ['n1', 'n2'] }));
    await waitFor(() => expect(result.current.byId.n2).toBeDefined());
    // n1 came from the cache the second time round.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
```

Note: check how `fetchJson` in `dataLayer.ts` reads error bodies — if the error test's mock response needs a `json()` method to avoid a TypeError inside the error path, add `json: () => Promise.resolve({})` to the mock. Adapt the mock, not the hook.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd client && npx vitest run src/components/Visualization/__tests__/useConnections.test.ts`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Add to `client/src/const.ts` inside `API_ROUTES`:

```ts
NOTE_CONNECTIONS: '/api/notes', // + `/${id}/connections`
```

Create `useConnections.ts`:

```ts
import { useEffect, useMemo, useState } from 'react';

import { API_ROUTES } from '@/const';
import { readQuery, subscribe } from '@/hooks/dataLayer';

export interface ConnectionNoteRef {
  id: string;
  title: string;
}
export interface SimilarConnection extends ConnectionNoteRef {
  score: number;
}
export interface TagConnectionGroup {
  tag: string;
  notes: ConnectionNoteRef[];
}
export interface EntityConnectionGroup {
  entity: string;
  notes: ConnectionNoteRef[];
}
export interface NoteConnections {
  id: string;
  similar: SimilarConnection[];
  shared_tags: TagConnectionGroup[];
  shared_entities: EntityConnectionGroup[];
}

export const connectionsUrl = (noteId: string): string =>
  `${API_ROUTES.NOTE_CONNECTIONS}/${encodeURIComponent(noteId)}/connections`;

/**
 * Connections for every note in the selection chain, read through the shared
 * data-layer cache. Each id is fetched once (the cache dedupes); expanding the
 * chain only fetches the new id.
 */
export function useConnectionsFor(ids: string[]): {
  byId: Record<string, NoteConnections>;
  errors: Record<string, string>;
  isLoading: boolean;
} {
  // `tick` only forces a re-read of the cache; the data itself lives there.
  const [, setTick] = useState(0);
  const key = ids.join('|');

  useEffect(() => {
    const urls = new Set(ids.map(connectionsUrl));
    return subscribe((changed) => {
      if (urls.has(changed)) {
        setTick((t) => t + 1);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return useMemo(() => {
    const byId: Record<string, NoteConnections> = {};
    const errors: Record<string, string> = {};
    let isLoading = false;
    ids.forEach((id) => {
      const res = readQuery<NoteConnections>(connectionsUrl(id));
      if (res.data) {
        byId[id] = res.data;
      }
      if (res.error !== undefined) {
        errors[id] = res.error instanceof Error ? res.error.message : String(res.error);
      }
      if (res.isLoading) {
        isLoading = true;
        // The shared promise must not surface as an unhandled rejection here;
        // the error lands in the cache and comes back via `res.error`.
        res.promise.catch(() => undefined);
      }
    });
    return { byId, errors, isLoading };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}
```

If the memo-on-`key` pattern makes stale reads flaky (the subscribe tick must trigger a re-render for the memo to re-run — it does, because `setTick` changes state), keep `tick` in the memo deps: `useMemo(..., [key, tick])` and destructure `const [tick, setTick] = useState(0)`. Use that form if the first test is flaky.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd client && npx vitest run src/components/Visualization/__tests__/useConnections.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/const.ts client/src/components/Visualization/useConnections.ts client/src/components/Visualization/__tests__/useConnections.test.ts
git commit -m "feat(viz): add connections fetch hook over the data-layer cache"
```

---

### Task 5: Frontend — pure scene-data helpers

**Files:**
- Create: `client/src/components/Visualization/sceneData.ts`
- Create: `client/src/components/Visualization/__tests__/sceneData.test.ts`

**Interfaces:**
- Consumes: `EmbeddingPoint` (Task 1), `NoteConnections` (Task 4).
- Produces (used by Tasks 6–8):

```ts
export const EDGE_COLORS = { similar: '#3987e5', tags: '#199e70', entities: '#d95926' } as const;
export type EdgeKind = keyof typeof EDGE_COLORS;
export interface EdgeMeta { from: string; to: string; kind: EdgeKind; label: string; }
export interface LayerToggles { similar: boolean; tags: boolean; entities: boolean; }
export interface PointBuffers {
  count: number;
  positions: Float32Array; // 3 per point
  colors: Float32Array;    // 3 per point, 0..1 rgb
  scales: Float32Array;    // 1 per point
  ids: string[];
  indexById: Map<string, number>;
}
export interface EdgeBuffers { meta: EdgeMeta[]; positions: Float32Array; colors: Float32Array; }
export const hexToRgb: (hex: string) => [number, number, number];
export const fadeTowards: (hex: string, bgHex: string, t: number) => [number, number, number];
export const buildPointBuffers: (points, opts) => PointBuffers;   // opts below
export const collectConnectedIds: (chain: string[], byId: Record<string, NoteConnections>, layers: LayerToggles) => Set<string>;
export const buildEdgeBuffers: (chain: string[], byId: Record<string, NoteConnections>, layers: LayerToggles, points: PointBuffers) => EdgeBuffers;
```

- [ ] **Step 1: Write the failing tests**

Create `__tests__/sceneData.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { EmbeddingPoint } from '@/hooks/useEmbeddings';

import {
  buildEdgeBuffers,
  buildPointBuffers,
  collectConnectedIds,
  EDGE_COLORS,
  fadeTowards,
  hexToRgb,
} from '../sceneData';
import { NoteConnections } from '../useConnections';

const pt = (id: string, coords: [number, number, number], tags: string[] = []): EmbeddingPoint => ({
  id,
  title: id,
  snippet: '',
  tags,
  coordinates: coords,
});

const baseOpts = {
  colorFor: () => '#ff0000',
  scaleFactor: 2,
  backgroundColor: '#000000',
  isolatedTag: null as string | null,
  selectedId: null as string | null,
  connectedIds: new Set<string>(),
};

const conn = (id: string, similarTo: string[]): NoteConnections => ({
  id,
  similar: similarTo.map((s) => ({ id: s, title: s, score: 0.5 })),
  shared_tags: [{ tag: 'T', notes: similarTo.map((s) => ({ id: s, title: s })) }],
  shared_entities: [],
});

describe('hexToRgb / fadeTowards', () => {
  it('converts hex and fades linearly towards the background', () => {
    expect(hexToRgb('#ff0000')).toEqual([1, 0, 0]);
    expect(fadeTowards('#ff0000', '#000000', 1)).toEqual([0, 0, 0]);
    const half = fadeTowards('#ff0000', '#000000', 0.5);
    expect(half[0]).toBeCloseTo(0.5);
  });
});

describe('buildPointBuffers', () => {
  it('scales positions and indexes every id', () => {
    const buffers = buildPointBuffers([pt('a', [1, 2, 3]), pt('b', [0, 0, 0])], baseOpts);
    expect(buffers.count).toBe(2);
    expect([...buffers.positions.slice(0, 3)]).toEqual([2, 4, 6]);
    expect(buffers.indexById.get('b')).toBe(1);
  });

  it('fades points outside an isolated tag and keeps matches at full colour', () => {
    const points = [pt('a', [0, 0, 0], ['Keep']), pt('b', [0, 0, 0], ['Drop'])];
    const buffers = buildPointBuffers(points, { ...baseOpts, isolatedTag: 'Keep' });
    expect([...buffers.colors.slice(0, 3)]).toEqual([1, 0, 0]); // full
    expect(buffers.colors[3]).toBeLessThan(0.3); // faded towards black
  });

  it('scales up the selection and its connections and fades the rest', () => {
    const points = [pt('sel', [0, 0, 0]), pt('conn', [0, 0, 0]), pt('other', [0, 0, 0])];
    const buffers = buildPointBuffers(points, {
      ...baseOpts,
      selectedId: 'sel',
      connectedIds: new Set(['conn']),
    });
    expect(buffers.scales[0]).toBeGreaterThan(buffers.scales[1]);
    expect(buffers.scales[1]).toBeGreaterThan(buffers.scales[2]);
    expect(buffers.colors[6]).toBeLessThan(0.3); // 'other' faded
  });
});

describe('collectConnectedIds', () => {
  it('unions enabled layers across the chain and always includes the chain', () => {
    const byId = { a: conn('a', ['x']), b: conn('b', ['y']) };
    const ids = collectConnectedIds(['a', 'b'], byId, { similar: true, tags: false, entities: false });
    expect(ids).toEqual(new Set(['a', 'b', 'x', 'y']));
  });

  it('respects layer toggles', () => {
    const byId = { a: conn('a', ['x']) };
    const ids = collectConnectedIds(['a'], byId, { similar: false, tags: false, entities: false });
    expect(ids).toEqual(new Set(['a']));
  });
});

describe('buildEdgeBuffers', () => {
  const points = buildPointBuffers([pt('a', [0, 0, 0]), pt('x', [1, 0, 0])], baseOpts);

  it('draws one segment per enabled-layer connection with the layer colour', () => {
    const edges = buildEdgeBuffers(['a'], { a: conn('a', ['x']) }, { similar: true, tags: false, entities: false }, points);
    expect(edges.meta).toHaveLength(1);
    expect(edges.meta[0]).toMatchObject({ from: 'a', to: 'x', kind: 'similar' });
    expect(edges.positions).toHaveLength(6);
    expect([...edges.colors.slice(0, 3)]).toEqual(hexToRgb(EDGE_COLORS.similar));
  });

  it('skips connections to points not currently visible', () => {
    const edges = buildEdgeBuffers(['a'], { a: conn('a', ['ghost']) }, { similar: true, tags: true, entities: true }, points);
    expect(edges.meta).toHaveLength(0);
  });

  it('dedupes the same pair within a kind but keeps distinct kinds', () => {
    const edges = buildEdgeBuffers(['a'], { a: conn('a', ['x']) }, { similar: true, tags: true, entities: false }, points);
    // conn() lists x under both similar and shared_tags: 1 similar + 1 tags edge.
    expect(edges.meta.map((e) => e.kind).sort()).toEqual(['similar', 'tags']);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd client && npx vitest run src/components/Visualization/__tests__/sceneData.test.ts`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `sceneData.ts`:

```ts
import { EmbeddingPoint } from '@/hooks/useEmbeddings';

import { NoteConnections } from './useConnections';

/** Edge colour per connection kind — distinct from the tag palette on purpose. */
export const EDGE_COLORS = { similar: '#3987e5', tags: '#199e70', entities: '#d95926' } as const;
export type EdgeKind = keyof typeof EDGE_COLORS;

export interface EdgeMeta {
  from: string;
  to: string;
  kind: EdgeKind;
  label: string;
}

export interface LayerToggles {
  similar: boolean;
  tags: boolean;
  entities: boolean;
}

export interface PointBuffers {
  count: number;
  positions: Float32Array;
  colors: Float32Array;
  scales: Float32Array;
  ids: string[];
  indexById: Map<string, number>;
}

export interface EdgeBuffers {
  meta: EdgeMeta[];
  positions: Float32Array;
  colors: Float32Array;
}

/** How far non-focused points fade towards the background (per-instance opacity
 *  does not exist for instancedMesh, so fading is done in colour space). */
const FADE = 0.88;

export const hexToRgb = (hex: string): [number, number, number] => {
  const value = parseInt(hex.replace('#', ''), 16);
  return [((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255];
};

const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

export const fadeTowards = (hex: string, bgHex: string, t: number): [number, number, number] => {
  const c = hexToRgb(hex);
  const bg = hexToRgb(bgHex);
  return [lerp(c[0], bg[0], t), lerp(c[1], bg[1], t), lerp(c[2], bg[2], t)];
};

interface PointBufferOpts {
  colorFor: (tags: string[] | undefined) => string;
  scaleFactor: number;
  backgroundColor: string;
  isolatedTag: string | null;
  selectedId: string | null;
  connectedIds: ReadonlySet<string>;
}

export const buildPointBuffers = (
  points: EmbeddingPoint[],
  opts: PointBufferOpts,
): PointBuffers => {
  const { colorFor, scaleFactor, backgroundColor, isolatedTag, selectedId, connectedIds } = opts;
  const count = points.length;
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const scales = new Float32Array(count);
  const ids: string[] = new Array(count);
  const indexById = new Map<string, number>();

  points.forEach((point, i) => {
    ids[i] = point.id;
    indexById.set(point.id, i);
    positions[i * 3] = point.coordinates[0] * scaleFactor;
    positions[i * 3 + 1] = point.coordinates[1] * scaleFactor;
    positions[i * 3 + 2] = point.coordinates[2] * scaleFactor;

    // Selection focus outranks tag isolation: once a note is selected, the map is
    // about its neighbourhood.
    let faded = false;
    if (selectedId !== null) {
      faded = point.id !== selectedId && !connectedIds.has(point.id);
    } else if (isolatedTag !== null) {
      faded = !(point.tags ?? []).includes(isolatedTag);
    }

    const hex = colorFor(point.tags);
    const rgb = faded ? fadeTowards(hex, backgroundColor, FADE) : hexToRgb(hex);
    colors[i * 3] = rgb[0];
    colors[i * 3 + 1] = rgb[1];
    colors[i * 3 + 2] = rgb[2];

    scales[i] =
      point.id === selectedId ? 2 : connectedIds.has(point.id) && selectedId !== null ? 1.4 : faded ? 0.7 : 1;
  });

  return { count, positions, colors, scales, ids, indexById };
};

export const collectConnectedIds = (
  chain: string[],
  byId: Record<string, NoteConnections>,
  layers: LayerToggles,
): Set<string> => {
  const out = new Set<string>(chain);
  chain.forEach((id) => {
    const conn = byId[id];
    if (!conn) {
      return;
    }
    if (layers.similar) {
      conn.similar.forEach((n) => out.add(n.id));
    }
    if (layers.tags) {
      conn.shared_tags.forEach((g) => g.notes.forEach((n) => out.add(n.id)));
    }
    if (layers.entities) {
      conn.shared_entities.forEach((g) => g.notes.forEach((n) => out.add(n.id)));
    }
  });
  return out;
};

export const buildEdgeBuffers = (
  chain: string[],
  byId: Record<string, NoteConnections>,
  layers: LayerToggles,
  points: PointBuffers,
): EdgeBuffers => {
  const meta: EdgeMeta[] = [];
  const seen = new Set<string>();

  const push = (from: string, to: string, kind: EdgeKind, label: string): void => {
    // Edges only run between currently visible points — a connection to a
    // filtered-out note simply does not draw.
    if (!points.indexById.has(from) || !points.indexById.has(to)) {
      return;
    }
    const key = from < to ? `${from}|${to}|${kind}` : `${to}|${from}|${kind}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    meta.push({ from, to, kind, label });
  };

  chain.forEach((id) => {
    const conn = byId[id];
    if (!conn) {
      return;
    }
    if (layers.similar) {
      conn.similar.forEach((n) => push(id, n.id, 'similar', `${Math.round(n.score * 100)}% similar`));
    }
    if (layers.tags) {
      conn.shared_tags.forEach((g) => g.notes.forEach((n) => push(id, n.id, 'tags', `#${g.tag}`)));
    }
    if (layers.entities) {
      conn.shared_entities.forEach((g) => g.notes.forEach((n) => push(id, n.id, 'entities', g.entity)));
    }
  });

  const positions = new Float32Array(meta.length * 6);
  const colors = new Float32Array(meta.length * 6);
  meta.forEach((edge, e) => {
    const a = points.indexById.get(edge.from)!;
    const b = points.indexById.get(edge.to)!;
    positions.set(points.positions.subarray(a * 3, a * 3 + 3), e * 6);
    positions.set(points.positions.subarray(b * 3, b * 3 + 3), e * 6 + 3);
    const rgb = hexToRgb(EDGE_COLORS[edge.kind]);
    colors.set(rgb, e * 6);
    colors.set(rgb, e * 6 + 3);
  });

  return { meta, positions, colors };
};
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd client && npx vitest run src/components/Visualization/__tests__/sceneData.test.ts`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/Visualization/sceneData.ts client/src/components/Visualization/__tests__/sceneData.test.ts
git commit -m "feat(viz): add pure buffer builders for instanced points and edges"
```

---

### Task 6: Frontend — Scene component (instanced points, edges, picking, tooltip data)

**Files:**
- Create: `client/src/components/Visualization/Scene.tsx`

**Interfaces:**
- Consumes: `PointBuffers`, `EdgeBuffers`, `EdgeMeta` from Task 5.
- Produces:

```ts
export interface HoverState { pointId?: string; edge?: EdgeMeta; x: number; y: number; }
export interface SceneProps {
  points: PointBuffers;
  ghost: PointBuffers | null;
  edges: EdgeBuffers;
  isDark: boolean;
  onHover: (hover: HoverState | null) => void;
  onSelect: (id: string) => void;
  onExpand: (id: string) => void;   // double-click
  onClearSelection: () => void;     // click on empty space
}
export const Scene: (props: SceneProps) => JSX.Element;
```

No unit test — the rendering logic worth testing lives in `sceneData.ts` (Task 5); this component is a thin buffer-to-GPU adapter verified by typecheck, lint, and the Task 9 manual run.

- [ ] **Step 1: Implement**

Create `Scene.tsx`:

```tsx
import { OrbitControls } from '@react-three/drei';
import { Canvas, ThreeEvent } from '@react-three/fiber';
import { useLayoutEffect, useRef } from 'react';
import * as THREE from 'three';

import { EdgeBuffers, EdgeMeta, PointBuffers } from './sceneData';

export interface HoverState {
  pointId?: string;
  edge?: EdgeMeta;
  x: number;
  y: number;
}

export interface SceneProps {
  points: PointBuffers;
  ghost: PointBuffers | null;
  edges: EdgeBuffers;
  isDark: boolean;
  onHover: (hover: HoverState | null) => void;
  onSelect: (id: string) => void;
  onExpand: (id: string) => void;
  onClearSelection: () => void;
}

const POINT_RADIUS = 0.06;

interface InstancedPointsProps {
  buffers: PointBuffers;
  interactive: boolean;
  baseOpacity: number;
  onHover?: (hover: HoverState | null) => void;
  onSelect?: (id: string) => void;
  onExpand?: (id: string) => void;
}

/** One draw call for the whole cloud. Colour and scale are per-instance; picking
 *  uses the raycaster's instanceId. */
const InstancedPoints = ({
  buffers,
  interactive,
  baseOpacity,
  onHover,
  onSelect,
  onExpand,
}: InstancedPointsProps) => {
  const meshRef = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) {
      return;
    }
    const matrix = new THREE.Matrix4();
    const color = new THREE.Color();
    for (let i = 0; i < buffers.count; i++) {
      const s = buffers.scales[i];
      matrix
        .makeScale(s, s, s)
        .setPosition(buffers.positions[i * 3], buffers.positions[i * 3 + 1], buffers.positions[i * 3 + 2]);
      mesh.setMatrixAt(i, matrix);
      color.setRGB(buffers.colors[i * 3], buffers.colors[i * 3 + 1], buffers.colors[i * 3 + 2]);
      mesh.setColorAt(i, color);
    }
    mesh.count = buffers.count;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) {
      mesh.instanceColor.needsUpdate = true;
    }
  }, [buffers]);

  const idFromEvent = (e: ThreeEvent<MouseEvent | PointerEvent>): string | null =>
    e.instanceId !== undefined ? buffers.ids[e.instanceId] : null;

  return (
    <instancedMesh
      // instancedMesh capacity is a constructor arg, not reactive — remount on size change.
      key={buffers.count}
      ref={meshRef}
      args={[undefined, undefined, Math.max(buffers.count, 1)]}
      onPointerMove={
        interactive
          ? (e) => {
              e.stopPropagation();
              const id = idFromEvent(e);
              if (id && onHover) {
                onHover({ pointId: id, x: e.clientX, y: e.clientY });
              }
            }
          : undefined
      }
      onPointerOut={interactive && onHover ? () => onHover(null) : undefined}
      onClick={
        interactive
          ? (e) => {
              e.stopPropagation();
              const id = idFromEvent(e);
              if (id && onSelect) {
                onSelect(id);
              }
            }
          : undefined
      }
      onDoubleClick={
        interactive
          ? (e) => {
              e.stopPropagation();
              const id = idFromEvent(e);
              if (id && onExpand) {
                onExpand(id);
              }
            }
          : undefined
      }
    >
      <sphereGeometry args={[POINT_RADIUS, 12, 12]} />
      {/* White base colour: the visible colour is instanceColor * material colour. */}
      <meshStandardMaterial color="#ffffff" transparent opacity={baseOpacity} />
    </instancedMesh>
  );
};

interface ConnectionEdgesProps {
  edges: EdgeBuffers;
  onHover: (hover: HoverState | null) => void;
}

const ConnectionEdges = ({ edges, onHover }: ConnectionEdgesProps) => {
  if (edges.meta.length === 0) {
    return null;
  }
  return (
    <lineSegments
      // Geometry attributes are not reactive across lengths — remount per edge set.
      key={edges.meta.length}
      onPointerMove={(e) => {
        e.stopPropagation();
        // For LineSegments, intersection.index is the first vertex of the segment.
        const segment = e.index !== undefined ? Math.floor(e.index / 2) : -1;
        if (segment >= 0 && segment < edges.meta.length) {
          onHover({ edge: edges.meta[segment], x: e.clientX, y: e.clientY });
        }
      }}
      onPointerOut={() => onHover(null)}
    >
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[edges.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[edges.colors, 3]} />
      </bufferGeometry>
      <lineBasicMaterial vertexColors transparent opacity={0.7} />
    </lineSegments>
  );
};

export const Scene = ({
  points,
  ghost,
  edges,
  isDark,
  onHover,
  onSelect,
  onExpand,
  onClearSelection,
}: SceneProps) => {
  const fogColor = isDark ? '#1a1a19' : '#fcfcfb';
  return (
    <Canvas
      camera={{ position: [0, 0, 15], fov: 60 }}
      onCreated={({ raycaster }) => {
        // Lines are infinitely thin; without a threshold they are unhoverable.
        raycaster.params.Line.threshold = 0.08;
      }}
      onPointerMissed={onClearSelection}
    >
      <fog attach="fog" args={[fogColor, 12, 40]} />
      <ambientLight intensity={0.8} />
      <pointLight position={[10, 10, 10]} intensity={0.8} />
      {ghost && ghost.count > 0 && (
        <InstancedPoints buffers={ghost} interactive={false} baseOpacity={0.12} />
      )}
      <InstancedPoints
        buffers={points}
        interactive
        baseOpacity={0.95}
        onHover={onHover}
        onSelect={onSelect}
        onExpand={onExpand}
      />
      <ConnectionEdges edges={edges} onHover={onHover} />
      <OrbitControls enableZoom enablePan enableRotate makeDefault />
    </Canvas>
  );
};
```

- [ ] **Step 2: Verify it compiles and lints**

Run: `cd client && npx tsc --noEmit && npm run lint --silent`
Expected: clean. (If the `bufferAttribute args` form errors under the installed @react-three/fiber types, use the props form: `<bufferAttribute attach="attributes-position" array={edges.positions} count={edges.positions.length / 3} itemSize={3} />`.)

- [ ] **Step 3: Commit**

```bash
git add client/src/components/Visualization/Scene.tsx
git commit -m "feat(viz): render the note cloud as instanced meshes with edge picking"
```

---

### Task 7: Frontend — SidePanel (selection, layers, interactive legend, tag picker)

**Files:**
- Create: `client/src/components/Visualization/SidePanel.tsx`
- Create: `client/src/components/Visualization/__tests__/SidePanel.test.tsx`

**Interfaces:**
- Consumes: `NoteConnections` (Task 4), `LayerToggles`, `EDGE_COLORS` (Task 5), `TagLegendEntry` (existing `tagColors.ts`), `EmbeddingPoint` (Task 1).
- Produces:

```ts
export interface SidePanelProps {
  selected: EmbeddingPoint | null;
  chainTitles: string[];                 // breadcrumb, in hop order
  connections: NoteConnections | null;   // for the selected note
  connectionsError: string | null;
  connectionsLoading: boolean;
  layers: LayerToggles;
  onToggleLayer: (kind: keyof LayerToggles) => void;
  legend: TagLegendEntry[];
  isolatedTag: string | null;
  onIsolateTag: (tag: string | null) => void;
  allTags: string[];                     // every tag on the visible points, sorted
  ghost: boolean;
  onToggleGhost: () => void;
  spreadFactor: number;
  onSpreadChange: (value: number) => void;
  onOpenNote: (id: string) => void;
  onClearPath: () => void;
}
export const SidePanel: (props: SidePanelProps) => JSX.Element;
```

- [ ] **Step 1: Write the failing tests**

Create `__tests__/SidePanel.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SidePanel, SidePanelProps } from '../SidePanel';

const baseProps: SidePanelProps = {
  selected: null,
  chainTitles: [],
  connections: null,
  connectionsError: null,
  connectionsLoading: false,
  layers: { similar: true, tags: false, entities: false },
  onToggleLayer: vi.fn(),
  legend: [{ label: 'Recipes', color: '#0072b2' }],
  isolatedTag: null,
  onIsolateTag: vi.fn(),
  allTags: ['Recipes', 'Travel'],
  ghost: false,
  onToggleGhost: vi.fn(),
  spreadFactor: 5,
  onSpreadChange: vi.fn(),
  onOpenNote: vi.fn(),
  onClearPath: vi.fn(),
};

const selectedProps: SidePanelProps = {
  ...baseProps,
  selected: { id: 'n1', title: 'My note', snippet: 'hello', tags: ['Recipes'], coordinates: [0, 0, 0] },
  chainTitles: ['My note'],
  connections: {
    id: 'n1',
    similar: [{ id: 'n2', title: 'Two', score: 0.9 }],
    shared_tags: [{ tag: 'Recipes', notes: [{ id: 'n3', title: 'Three' }] }],
    shared_entities: [],
  },
};

describe('SidePanel', () => {
  it('shows the selected note and per-layer counts', () => {
    render(<SidePanel {...selectedProps} />);
    expect(screen.getByText('My note')).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /similar.*1/i })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /shared tags.*1/i })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /shared entities.*0/i })).toBeTruthy();
  });

  it('toggles layers and opens the note', () => {
    render(<SidePanel {...selectedProps} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /shared tags/i }));
    expect(selectedProps.onToggleLayer).toHaveBeenCalledWith('tags');
    fireEvent.click(screen.getByRole('button', { name: /open note/i }));
    expect(selectedProps.onOpenNote).toHaveBeenCalledWith('n1');
  });

  it('isolates a tag from the legend and clears it on second click', () => {
    const onIsolateTag = vi.fn();
    const { rerender } = render(<SidePanel {...baseProps} onIsolateTag={onIsolateTag} />);
    fireEvent.click(screen.getByRole('button', { name: 'Recipes' }));
    expect(onIsolateTag).toHaveBeenCalledWith('Recipes');
    rerender(<SidePanel {...baseProps} onIsolateTag={onIsolateTag} isolatedTag="Recipes" />);
    fireEvent.click(screen.getByRole('button', { name: 'Recipes' }));
    expect(onIsolateTag).toHaveBeenCalledWith(null);
  });

  it('shows a connections error inline without hiding the rest of the panel', () => {
    render(<SidePanel {...selectedProps} connections={null} connectionsError="boom" />);
    expect(screen.getByText(/boom/)).toBeTruthy();
    expect(screen.getByText('My note')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd client && npx vitest run src/components/Visualization/__tests__/SidePanel.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `SidePanel.tsx`:

```tsx
import { EmbeddingPoint } from '@/hooks/useEmbeddings';

import { EDGE_COLORS, LayerToggles } from './sceneData';
import { TagLegendEntry } from './tagColors';
import { NoteConnections } from './useConnections';

export interface SidePanelProps {
  selected: EmbeddingPoint | null;
  chainTitles: string[];
  connections: NoteConnections | null;
  connectionsError: string | null;
  connectionsLoading: boolean;
  layers: LayerToggles;
  onToggleLayer: (kind: keyof LayerToggles) => void;
  legend: TagLegendEntry[];
  isolatedTag: string | null;
  onIsolateTag: (tag: string | null) => void;
  allTags: string[];
  ghost: boolean;
  onToggleGhost: () => void;
  spreadFactor: number;
  onSpreadChange: (value: number) => void;
  onOpenNote: (id: string) => void;
  onClearPath: () => void;
}

const LAYER_ROWS: { kind: keyof LayerToggles; label: string; count: (c: NoteConnections) => number }[] = [
  { kind: 'similar', label: 'Similar', count: (c) => c.similar.length },
  {
    kind: 'tags',
    label: 'Shared tags',
    count: (c) => c.shared_tags.reduce((n, g) => n + g.notes.length, 0),
  },
  {
    kind: 'entities',
    label: 'Shared entities',
    count: (c) => c.shared_entities.reduce((n, g) => n + g.notes.length, 0),
  },
];

export const SidePanel = ({
  selected,
  chainTitles,
  connections,
  connectionsError,
  connectionsLoading,
  layers,
  onToggleLayer,
  legend,
  isolatedTag,
  onIsolateTag,
  allTags,
  ghost,
  onToggleGhost,
  spreadFactor,
  onSpreadChange,
  onOpenNote,
  onClearPath,
}: SidePanelProps) => (
  <aside className="viz-side-panel">
    <section className="viz-panel-section">
      <h4>Tags</h4>
      <ul className="viz-tag-legend" aria-label="Point colours by tag">
        {legend.map((entry) => {
          const isSlotTag = entry.label !== 'Other tags' && entry.label !== 'Untagged';
          return (
            <li key={entry.label}>
              {isSlotTag ? (
                <button
                  className={`viz-legend-item ${isolatedTag === entry.label ? 'isolated' : ''}`}
                  onClick={() => onIsolateTag(isolatedTag === entry.label ? null : entry.label)}
                >
                  <span className="viz-tag-swatch" style={{ backgroundColor: entry.color }} />
                  {entry.label}
                </button>
              ) : (
                <span className="viz-legend-item">
                  <span className="viz-tag-swatch" style={{ backgroundColor: entry.color }} />
                  {entry.label}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      <input
        type="search"
        className="viz-tag-picker"
        placeholder="Isolate any tag…"
        list="viz-all-tags"
        value={isolatedTag ?? ''}
        onChange={(e) => onIsolateTag(allTags.includes(e.target.value) ? e.target.value : null)}
        aria-label="Isolate any tag"
      />
      <datalist id="viz-all-tags">
        {allTags.map((tag) => (
          <option key={tag} value={tag} />
        ))}
      </datalist>
    </section>

    <section className="viz-panel-section">
      <h4>View</h4>
      <label className="viz-control-row">
        <input type="checkbox" checked={ghost} onChange={onToggleGhost} />
        Ghost filtered-out notes
      </label>
      <label className="viz-control-row">
        Spread: {spreadFactor}
        <input
          type="range"
          min="1"
          max="10"
          value={spreadFactor}
          onChange={(e) => onSpreadChange(parseInt(e.target.value))}
        />
      </label>
    </section>

    {selected && (
      <section className="viz-panel-section viz-selection">
        <h4>{selected.title || 'Untitled note'}</h4>
        {selected.snippet && <p className="viz-snippet">{selected.snippet}</p>}
        {selected.tags.length > 0 && <p className="viz-selected-tags">{selected.tags.join(', ')}</p>}
        <button className="viz-open-note" onClick={() => onOpenNote(selected.id)}>
          Open note
        </button>

        {connectionsError && <p className="viz-error">Connections failed: {connectionsError}</p>}
        {connectionsLoading && <p className="viz-muted">Loading connections…</p>}

        <h5>Connections</h5>
        {LAYER_ROWS.map(({ kind, label, count }) => (
          <label key={kind} className="viz-control-row">
            <input
              type="checkbox"
              checked={layers[kind]}
              onChange={() => onToggleLayer(kind)}
              aria-label={`${label} (${connections ? count(connections) : 0})`}
            />
            <span className="viz-edge-swatch" style={{ backgroundColor: EDGE_COLORS[kind] }} />
            {label} ({connections ? count(connections) : 0})
          </label>
        ))}

        {chainTitles.length > 1 && (
          <>
            <h5>Path</h5>
            <p className="viz-breadcrumb">{chainTitles.join(' → ')}</p>
            <button onClick={onClearPath}>Clear path</button>
          </>
        )}
        <p className="viz-muted">Double-click a connected note to extend the path.</p>
      </section>
    )}
  </aside>
);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd client && npx vitest run src/components/Visualization/__tests__/SidePanel.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/Visualization/SidePanel.tsx client/src/components/Visualization/__tests__/SidePanel.test.tsx
git commit -m "feat(viz): add the side panel with layers, interactive legend, and tag picker"
```

---

### Task 8: Frontend — rewire `index.tsx`, delete the old components, styles

**Files:**
- Rewrite: `client/src/components/Visualization/index.tsx`
- Delete: `client/src/components/Visualization/EmbeddingsVisualization.tsx`
- Delete: `client/src/components/Visualization/VisualizationControls.tsx`
- Modify: `client/src/components/Visualization/styles.css`

**Interfaces:**
- Consumes: everything from Tasks 1, 3–7.
- Produces: `<Visualization searchResults onSelectNote isAllNotesView?>` — unchanged external API (`Results.tsx:331`, `AllNotes/index.tsx:319` untouched).

- [ ] **Step 1: Rewrite `index.tsx`**

```tsx
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { calculateScorePercentage } from '@/helpers';
import { EmbeddingPoint, useEmbeddings } from '@/hooks/useEmbeddings';
import { Note } from '@/types';

import { HoverState, Scene } from './Scene';
import {
  buildEdgeBuffers,
  buildPointBuffers,
  collectConnectedIds,
  LayerToggles,
} from './sceneData';
import { SidePanel } from './SidePanel';
import { buildTagColorScale, UNTAGGED_COLOR } from './tagColors';
import { useConnectionsFor } from './useConnections';
import './styles.css';

/**
 * Track the theme the document is actually in.
 *
 * Read from the DOM rather than by calling useTheme() again: a second hook instance would
 * hold its own state and go stale the moment the user toggles the theme in the header.
 */
const useDocumentTheme = (): 'light' | 'dark' => {
  const read = (): 'light' | 'dark' =>
    document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  const [mode, setMode] = useState<'light' | 'dark'>(read);

  useEffect(() => {
    const observer = new MutationObserver(() => setMode(read()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    return () => observer.disconnect();
  }, []);

  return mode;
};

const BACKGROUNDS = { light: '#fcfcfb', dark: '#1a1a19' } as const;
const GHOST_COLOR = { light: '#c9c9c6', dark: '#3a3a38' } as const;
const NO_CONNECTIONS: ReadonlySet<string> = new Set();

interface VisualizationProps {
  searchResults: Note[];
  onSelectNote: (noteId: string) => void;
  isAllNotesView?: boolean;
}

export const Visualization = memo(
  ({ searchResults, onSelectNote }: VisualizationProps) => {
    const { embeddings, isLoading, error } = useEmbeddings();
    const themeMode = useDocumentTheme();
    const containerRef = useRef<HTMLDivElement>(null);

    const [spreadFactor, setSpreadFactor] = useState(5);
    const [ghost, setGhost] = useState(false);
    const [isolatedTag, setIsolatedTag] = useState<string | null>(null);
    const [chain, setChain] = useState<string[]>([]);
    const [layers, setLayers] = useState<LayerToggles>({
      similar: true,
      tags: false,
      entities: false,
    });
    const [hover, setHover] = useState<HoverState | null>(null);
    const [isFullscreen, setIsFullscreen] = useState(false);

    const selectedId = chain.length > 0 ? chain[chain.length - 1] : null;

    // The view IS the filter: only the notes the list view shows are rendered.
    const visibleIds = useMemo(() => new Set(searchResults.map((n) => n.id)), [searchResults]);
    const visiblePoints = useMemo(
      () => embeddings.filter((p) => visibleIds.has(p.id)),
      [embeddings, visibleIds],
    );
    const ghostPoints = useMemo(
      () => (ghost ? embeddings.filter((p) => !visibleIds.has(p.id)) : []),
      [embeddings, visibleIds, ghost],
    );

    const scoreById = useMemo(() => {
      const map = new Map<string, number>();
      searchResults.forEach((n) => {
        const pct = calculateScorePercentage(n.score);
        if (pct !== null) {
          map.set(n.id, pct);
        }
      });
      return map;
    }, [searchResults]);

    // Scale from ALL embeddings, not the visible subset: positions must not shift
    // when the filter changes — spatial memory is the point of a fixed layout.
    const scaleFactor = useMemo(() => {
      let maxAbs = 0;
      embeddings.forEach((p) => p.coordinates.forEach((c) => (maxAbs = Math.max(maxAbs, Math.abs(c)))));
      return maxAbs > 0 ? spreadFactor / maxAbs : 1;
    }, [embeddings, spreadFactor]);

    // Built from the visible points, so the legend reflects what is on screen.
    const tagScale = useMemo(
      () => buildTagColorScale(visiblePoints, themeMode),
      [visiblePoints, themeMode],
    );
    const allTags = useMemo(() => {
      const tags = new Set<string>();
      visiblePoints.forEach((p) => p.tags.forEach((t) => tags.add(t)));
      return [...tags].sort((a, b) => a.localeCompare(b));
    }, [visiblePoints]);

    const { byId, errors, isLoading: connectionsLoading } = useConnectionsFor(chain);
    const connectedIds = useMemo(
      () => (chain.length > 0 ? collectConnectedIds(chain, byId, layers) : NO_CONNECTIONS),
      [chain, byId, layers],
    );

    const pointBuffers = useMemo(
      () =>
        buildPointBuffers(visiblePoints, {
          colorFor: tagScale.colorFor,
          scaleFactor,
          backgroundColor: BACKGROUNDS[themeMode],
          isolatedTag,
          selectedId,
          connectedIds,
        }),
      [visiblePoints, tagScale, scaleFactor, themeMode, isolatedTag, selectedId, connectedIds],
    );
    const ghostBuffers = useMemo(
      () =>
        ghostPoints.length > 0
          ? buildPointBuffers(ghostPoints, {
              colorFor: () => GHOST_COLOR[themeMode],
              scaleFactor,
              backgroundColor: BACKGROUNDS[themeMode],
              isolatedTag: null,
              selectedId: null,
              connectedIds: NO_CONNECTIONS,
            })
          : null,
      [ghostPoints, scaleFactor, themeMode],
    );
    const edgeBuffers = useMemo(
      () => buildEdgeBuffers(chain, byId, layers, pointBuffers),
      [chain, byId, layers, pointBuffers],
    );

    const handleSelect = useCallback((id: string) => {
      setChain([id]);
    }, []);
    const handleExpand = useCallback(
      (id: string) => {
        setChain((prev) => {
          if (prev.includes(id)) {
            return prev;
          }
          // Expanding only makes sense from an existing neighbourhood; a
          // double-click elsewhere starts a fresh path.
          return connectedIds.has(id) ? [...prev, id] : [id];
        });
      },
      [connectedIds],
    );
    const handleClearSelection = useCallback(() => setChain([]), []);
    const handleToggleLayer = useCallback(
      (kind: keyof LayerToggles) => setLayers((prev) => ({ ...prev, [kind]: !prev[kind] })),
      [],
    );

    const toggleFullscreen = useCallback(() => {
      if (!containerRef.current) {
        return;
      }
      if (!document.fullscreenElement) {
        containerRef.current
          .requestFullscreen()
          .then(() => setIsFullscreen(true))
          .catch(() => setIsFullscreen(false));
      } else {
        document
          .exitFullscreen()
          .then(() => setIsFullscreen(false))
          .catch(() => undefined);
      }
    }, []);

    const selectedPoint = useMemo(
      () => (selectedId ? (embeddings.find((p) => p.id === selectedId) ?? null) : null),
      [embeddings, selectedId],
    );
    const chainTitles = useMemo(
      () =>
        chain.map((id) => {
          const p = embeddings.find((e) => e.id === id);
          return p?.title || 'Untitled';
        }),
      [chain, embeddings],
    );
    const hoveredPoint = useMemo(
      () => (hover?.pointId ? (visiblePoints.find((p) => p.id === hover.pointId) ?? null) : null),
      [hover, visiblePoints],
    );

    if (error) {
      return <div className="visualization-empty">Error loading visualization: {error}</div>;
    }
    if (isLoading) {
      return <div className="visualization-loading">Loading visualization...</div>;
    }
    if (embeddings.length === 0) {
      return <div className="visualization-empty">No embeddings available for visualization.</div>;
    }
    if (visiblePoints.length === 0) {
      return <div className="visualization-empty">No points match the current filter criteria.</div>;
    }

    return (
      <div className="visualization-wrapper">
        <div
          className={`visualization-container ${hover?.pointId ? 'point-hover' : ''}`}
          ref={containerRef}
        >
          <button className="fullscreen-toggle" onClick={toggleFullscreen}>
            <span className="material-icons">{isFullscreen ? 'fullscreen_exit' : 'fullscreen'}</span>
          </button>

          <Scene
            points={pointBuffers}
            ghost={ghostBuffers}
            edges={edgeBuffers}
            isDark={themeMode === 'dark'}
            onHover={setHover}
            onSelect={handleSelect}
            onExpand={handleExpand}
            onClearSelection={handleClearSelection}
          />

          {hover && (hoveredPoint || hover.edge) && (
            <div className="viz-tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
              {hoveredPoint && (
                <>
                  <strong>{hoveredPoint.title || hoveredPoint.snippet || 'Untitled'}</strong>
                  {scoreById.has(hoveredPoint.id) && <div>{scoreById.get(hoveredPoint.id)}% match</div>}
                  {hoveredPoint.tags.length > 0 && <div>[{hoveredPoint.tags.join(', ')}]</div>}
                </>
              )}
              {hover.edge && <strong>{hover.edge.label}</strong>}
            </div>
          )}

          <SidePanel
            selected={selectedPoint}
            chainTitles={chainTitles}
            connections={selectedId ? (byId[selectedId] ?? null) : null}
            connectionsError={selectedId ? (errors[selectedId] ?? null) : null}
            connectionsLoading={connectionsLoading}
            layers={layers}
            onToggleLayer={handleToggleLayer}
            legend={tagScale.legend}
            isolatedTag={isolatedTag}
            onIsolateTag={setIsolatedTag}
            allTags={allTags}
            ghost={ghost}
            onToggleGhost={() => setGhost((g) => !g)}
            spreadFactor={spreadFactor}
            onSpreadChange={setSpreadFactor}
            onOpenNote={onSelectNote}
            onClearPath={() => setChain(chain.slice(0, 1))}
          />
        </div>
      </div>
    );
  },
);
```

Notes:
- `isAllNotesView` is accepted (API unchanged) but no longer branches — both views behave identically now. Keep it in the props interface, destructure without using it.
- `UNTAGGED_COLOR` import is unused in the final file — drop it from the import.
- The `.all-notes-visualization-wrapper` class is dropped; verify with `grep -rn "all-notes-visualization-wrapper" client/src` — if `AllNotes` CSS targets it, keep emitting the class conditionally instead.

- [ ] **Step 2: Delete the superseded components**

```bash
git rm client/src/components/Visualization/EmbeddingsVisualization.tsx client/src/components/Visualization/VisualizationControls.tsx
```

- [ ] **Step 3: Styles**

In `styles.css`: delete the rule blocks for `.visualization-controls`, `.visualization-toggle`, `.visualization-sliders`, `.slider-container` (superseded); keep `.visualization-wrapper`, `.visualization-container`, `.visualization-loading`, `.visualization-empty`, `.fullscreen-toggle`, `.viz-tag-legend`, `.viz-tag-swatch`. Add:

```css
.viz-side-panel {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 260px;
  max-height: calc(100% - 24px);
  overflow-y: auto;
  background: var(--card-bg, rgba(255, 255, 255, 0.92));
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
  z-index: 2;
}

[data-theme='dark'] .viz-side-panel {
  background: rgba(26, 26, 25, 0.92);
}

.viz-panel-section + .viz-panel-section {
  margin-top: 12px;
  border-top: 1px solid var(--border-color, #ddd);
  padding-top: 12px;
}

.viz-panel-section h4,
.viz-panel-section h5 {
  margin: 0 0 6px;
}

.viz-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  padding: 2px 4px;
  cursor: pointer;
  font: inherit;
  color: inherit;
  border-radius: 4px;
}

.viz-legend-item.isolated {
  outline: 2px solid currentColor;
}

span.viz-legend-item {
  cursor: default;
}

.viz-control-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 0;
}

.viz-tag-picker {
  width: 100%;
  margin-top: 6px;
}

.viz-edge-swatch {
  width: 14px;
  height: 3px;
  display: inline-block;
  border-radius: 2px;
}

.viz-tooltip {
  position: fixed;
  max-width: 280px;
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
  pointer-events: none;
  z-index: 10;
}

.viz-breadcrumb {
  word-break: break-word;
}

.viz-error {
  color: #d55e00;
}

.viz-muted {
  opacity: 0.7;
}

.viz-snippet {
  opacity: 0.85;
  font-size: 12px;
}
```

(Match the existing CSS variable names used elsewhere in `styles.css` — check what `.viz-tag-legend` already uses and reuse those variables instead of the fallbacks above if they differ.)

- [ ] **Step 4: Verify — typecheck, lint, full frontend suite**

Run: `cd client && npx tsc --noEmit && npm run lint --silent && npx vitest run`
Expected: clean; all suites pass (including untouched `AllNotes.test.tsx`).

- [ ] **Step 5: Commit**

```bash
git add -A client/src/components/Visualization client/src/const.ts
git commit -m "feat(viz): rebuild the 3D view around filtering, selection, and connection layers"
```

---

### Task 9: Full verification and manual smoke test

**Files:** none new.

- [ ] **Step 1: Full gates**

Run: `make test && make lint && make build`
Expected: all green. Fix anything that isn't before proceeding.

- [ ] **Step 2: Manual smoke test (real app, real GPU path)**

Run `make dev`, open the app, and verify by hand — this is the only place the WebGL path is exercised:
1. Switch to the 3D view in All Notes → points render, colors match the legend, panning/zooming is smooth (this is the 20k-point litmus test).
2. Apply a tag filter in All Notes → the cloud shrinks to the filtered set; enable "Ghost filtered-out notes" → the rest appears as faint gray.
3. Click a legend swatch → isolation; click again → back.
4. Click a note → panel populates, similarity edges appear; toggle the other two layers; hover an edge → label tooltip.
5. Double-click a connected note → path extends, breadcrumb updates; "Clear path" collapses to the first note; click empty space → selection clears.
6. Search view: run a search, switch to 3D → only results render; hover shows "% match".
7. Toggle dark mode → colors and panel adapt.

Do NOT paste note titles/content from this session anywhere (terminal output, commit messages) — report findings structurally ("hover label renders", not what it said).

- [ ] **Step 3: Final commit if fixes were needed**

```bash
git add -A && git commit -m "fix(viz): address smoke-test findings"
```

(Skip if the tree is clean.)
