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

/** How far the pointer may travel between press and release and still count as a
 *  click rather than a camera drag. */
export const DRAG_THRESHOLD_PX = 4;

/** What the pointer did between press and release. */
export interface PointerGesture {
  /** MouseEvent.button at press: 0 primary, 1 middle, 2 secondary. */
  button: number;
  /** Whether the pointer travelled past DRAG_THRESHOLD_PX while held. */
  dragged: boolean;
}

/**
 * Whether a gesture should change the selection.
 *
 * Only a primary-button click counts. OrbitControls binds the secondary button to
 * pan and the primary to orbit, and r3f reports every one of those as a plain
 * pointer event — so without this, panning or right-clicking the background read
 * as "clicked empty space" and wiped the selection mid-navigation.
 */
export const isSelectionGesture = (gesture: PointerGesture): boolean =>
  gesture.button === 0 && !gesture.dragged;

/** Bounds on the automatic point radius. The floor keeps a dense corpus's dots
 *  visible and clickable at the cost of some overlap — 20k non-overlapping points
 *  would be sub-pixel, which is worse than overlapping ones. The ceiling stops a
 *  two-note filter from rendering beach balls. */
const MIN_POINT_RADIUS = 0.05;
const MAX_POINT_RADIUS = 0.6;

/**
 * Point radius for a cloud of `count` points, in the world units of a ±14 layout.
 *
 * Dots are laid out across a roughly disc-shaped projection, so the area each one
 * can own goes as 1/count and the non-overlapping radius as 1/sqrt(count). The
 * coefficient is calibrated so a ~1000-note corpus lands on 0.063 — the size the
 * view was hand-tuned to before this became automatic.
 */
export const autoPointRadius = (count: number): number => {
  if (count <= 0) {
    return MIN_POINT_RADIUS;
  }
  const radius = 2 / Math.sqrt(count);
  return Math.min(MAX_POINT_RADIUS, Math.max(MIN_POINT_RADIUS, radius));
};

/** Per-instance size: the selection reads largest, its neighbourhood next, and
 *  anything faded out shrinks so it stops competing for attention. */
const pointScale = (isSelected: boolean, isConnected: boolean, faded: boolean): number => {
  if (isSelected) {
    return 2;
  }
  if (isConnected) {
    return 1.4;
  }
  return faded ? 0.7 : 1;
};

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

/** What the view is currently focused on, if anything. */
export interface FocusRule {
  isolatedTag: string | null;
  selectedId: string | null;
  connectedIds: ReadonlySet<string>;
}

/** Whether anything is focused. With no focus there is no "everything else", so
 *  hiding is a no-op rather than an empty screen. */
export const hasFocus = (rule: FocusRule): boolean =>
  rule.selectedId !== null || rule.isolatedTag !== null;

/**
 * Whether a point is in focus.
 *
 * Selection outranks tag isolation: once a note is selected the map is about its
 * neighbourhood, not about a tag. This is the single definition of "in focus" —
 * fading (buildPointBuffers) and hiding (the render filter) both read it, so the
 * two can never disagree about what is in and what is out.
 */
export const isPointFocused = (
  point: { id: string; tags?: string[] },
  rule: FocusRule,
): boolean => {
  if (rule.selectedId !== null) {
    return point.id === rule.selectedId || rule.connectedIds.has(point.id);
  }
  if (rule.isolatedTag !== null) {
    return (point.tags ?? []).includes(rule.isolatedTag);
  }
  return true;
};

interface PointBufferOpts extends FocusRule {
  colorFor: (tags: string[] | undefined) => string;
  scaleFactor: number;
  backgroundColor: string;
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

    const faded = !isPointFocused(point, { isolatedTag, selectedId, connectedIds });

    const hex = colorFor(point.tags);
    const rgb = faded ? fadeTowards(hex, backgroundColor, FADE) : hexToRgb(hex);
    colors[i * 3] = rgb[0];
    colors[i * 3 + 1] = rgb[1];
    colors[i * 3 + 2] = rgb[2];

    scales[i] = pointScale(
      point.id === selectedId,
      connectedIds.has(point.id) && selectedId !== null,
      faded,
    );
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
      conn.similar.forEach((n) =>
        push(id, n.id, 'similar', `${Math.round(n.score * 100)}% similar`),
      );
    }
    if (layers.tags) {
      conn.shared_tags.forEach((g) => g.notes.forEach((n) => push(id, n.id, 'tags', `#${g.tag}`)));
    }
    if (layers.entities) {
      conn.shared_entities.forEach((g) =>
        g.notes.forEach((n) => push(id, n.id, 'entities', g.entity)),
      );
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
