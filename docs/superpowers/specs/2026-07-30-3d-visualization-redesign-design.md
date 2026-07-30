# 3D Visualization Redesign — Design

**Date:** 2026-07-30
**Status:** Approved

## Problem

The current 3D view (`client/src/components/Visualization/`) is unusable at real corpus scale (5,000–20,000+ notes):

- Every note is an individual React `<mesh>` sphere → thousands of draw calls → severe lag.
- Positions come from PCA, which preserves global variance, not cluster structure → one undifferentiated blob.
- Filters (tags, search, archived) only dim non-matches; the view never reflects what the list view shows.
- Tag coloring caps at 3 hues; no way to explore other tags.
- No way to discover relationships between notes.

## Goals

1. The view renders exactly the filtered note set, reacting to all filters.
2. Notes are visually distinguishable by tag, with every tag explorable.
3. Smooth interaction at 20k points.
4. Selecting a note reveals its meaningful connections (semantic similarity, shared tags, shared entities) with multi-hop exploration.

## Chosen approach

Rebuild on the existing react-three-fiber stack: a single `instancedMesh` for all points (one draw call, native instance raycasting), one `LineSegments` geometry for edges, UMAP layout server-side, and a new per-note connections endpoint. Rejected: `3d-force-graph` (owns its own renderer, fights R3F and the custom legend/layers) and raw shader points with GPU picking (more work than 20k points needs).

## Design

### 1. Backend

- **Layout:** `/api/embeddings` switches from PCA to **UMAP 3D** (new `umap-learn` dependency). Cached by embedding-matrix hash via `lru_cache`, exactly like the current PCA caching in `app/routes/embeddings.py`. If UMAP fails, fall back to PCA with a logged warning (structural metadata only — never note text, per privacy rules).
- **Payload trim:** each point ships `id`, `title`, a ~120-char content snippet, `tags`, `coordinates`. No full `content` — at 20k notes the full-content payload is many MB and is never displayed in full.
- **New endpoint `GET /api/notes/{id}/connections`:** computed on demand from in-memory data, returns:
  - `similar`: top-K (default 10, query param `k`) cosine neighbors from the embedding matrix, with scores.
  - `shared_tags`: notes sharing ≥1 tag with the target, grouped by tag, capped per tag.
  - `shared_entities`: notes linked via the entity index, with the shared entity names.
  - 404 for unknown note id; per-section empty lists are valid results, not errors.

### 2. Rendering

- One `instancedMesh` for all visible points. Per-instance color attribute; hover and selection expressed via per-instance scale. Raycasting uses the native `instanceId` hit info.
- Hover tooltip is an **HTML overlay** (title + tags + match score when relevant), not a 3D `<Text>` billboard.
- Fog and size attenuation for depth perception.

### 3. Filtering

- The scene renders **only the currently filtered notes** (AllNotes passes `visibleNotes`; search view passes results). A **"ghost context" toggle** renders excluded notes as a second, non-interactive, low-opacity gray `instancedMesh`.
- Coordinates are fixed by the global UMAP projection — filtering never re-lays-out the map, preserving spatial memory.
- The "show all points" toggle and match-threshold slider are removed (superseded by filtering + ghost toggle). The spread slider stays.

### 4. Tag colors & legend

- `buildTagColorScale` extends from 3 to **8 categorical slots** (validated 8-hue palettes per light/dark theme); remaining tags gray, untagged lighter gray. Scale is built from the **visible** notes so the legend reflects the screen.
- **Interactive legend:** clicking a swatch isolates/highlights that tag (non-matching points fade to ~10% opacity); clicking again clears. Tags without a hue slot are reachable via a searchable tag picker in the side panel.

### 5. Connections discovery

- **Click a point** → selection. Side panel shows title/snippet/tags plus three **layer toggles** — Similarity / Shared tags / Shared entities — each with a distinct edge color and a count badge. Enabled layers draw edges from the selected note; connected points scale up, the rest fade.
- Hovering an edge shows its label (similarity %, tag name, or entity name).
- **Multi-hop:** double-clicking a connected point expands the graph from it as well; the panel shows a breadcrumb trail of hops and a "clear path" button.
- An "open note" action in the panel invokes the existing `onSelectNote` flow.
- Connections are fetched lazily per note and cached client-side (`useConnections`).

### 6. Component structure

```
client/src/components/Visualization/
  index.tsx          — data fetching, filter wiring, state
  Scene.tsx          — Canvas, instanced points, edges, picking
  SidePanel.tsx      — selection details, layer toggles, legend, tag picker
  useConnections.ts  — per-note connections fetch + cache
  tagColors.ts       — extended 8-slot color scale
```

### 7. Error handling

- Connections fetch failure renders inline in the side panel; the scene stays interactive.
- Empty filtered set shows the existing "no points match" empty state.
- UMAP → PCA server-side fallback as above.

### 8. Testing

- Frontend: color scale (8 slots, ties, untagged/other), visible-set derivation from filters, `useConnections` with mocked API, legend isolate/clear behavior.
- Backend: connections endpoint with **synthetic fixture notes only** (isolated cache via the autouse `isolate_cache_dir` fixture — never the real cache), covering top-K, shared tags, shared entities, unknown id.
- Note: the stubbed `SentenceTransformer` in `tests/conftest.py` means UMAP output shape is tested against synthetic matrices, not real model output.

## Out of scope

- Coloring by HDBSCAN cluster.
- Editing tags from the 3D view.
- Persisting exploration paths across sessions.
