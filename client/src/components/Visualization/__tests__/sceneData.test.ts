import { describe, expect, it } from 'vitest';

import { EmbeddingPoint } from '@/hooks/useEmbeddings';

import {
  autoPointRadius,
  buildEdgeBuffers,
  buildPointBuffers,
  collectConnectedIds,
  EDGE_COLORS,
  fadeTowards,
  hasFocus,
  hexToRgb,
  isPointFocused,
  isSelectionGesture,
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

describe('isPointFocused / hasFocus', () => {
  const NONE = { isolatedTag: null, selectedId: null, connectedIds: new Set<string>() };

  it('focuses everything when nothing is selected or isolated', () => {
    expect(hasFocus(NONE)).toBe(false);
    expect(isPointFocused({ id: 'a' }, NONE)).toBe(true);
  });

  it('focuses the tag when one is isolated and nothing is selected', () => {
    const rule = { ...NONE, isolatedTag: 'Keep' };
    expect(hasFocus(rule)).toBe(true);
    expect(isPointFocused({ id: 'a', tags: ['Keep'] }, rule)).toBe(true);
    expect(isPointFocused({ id: 'b', tags: ['Drop'] }, rule)).toBe(false);
    expect(isPointFocused({ id: 'c' }, rule)).toBe(false);
  });

  it('lets a selection outrank an isolated tag', () => {
    const rule = { isolatedTag: 'Keep', selectedId: 'sel', connectedIds: new Set(['conn']) };
    expect(isPointFocused({ id: 'sel', tags: [] }, rule)).toBe(true);
    expect(isPointFocused({ id: 'conn', tags: [] }, rule)).toBe(true);
    // Carries the isolated tag, but is outside the selection's neighbourhood.
    expect(isPointFocused({ id: 'other', tags: ['Keep'] }, rule)).toBe(false);
  });
});

describe('isSelectionGesture', () => {
  it('accepts only a primary-button click that did not drag', () => {
    expect(isSelectionGesture({ button: 0, dragged: false })).toBe(true);
  });

  it('rejects the camera controls', () => {
    // OrbitControls pans on the secondary button; r3f still reports it as a
    // pointer event that missed geometry, which used to wipe the selection.
    expect(isSelectionGesture({ button: 2, dragged: false })).toBe(false);
    expect(isSelectionGesture({ button: 2, dragged: true })).toBe(false);
    // Orbiting with the primary button ends in a release over empty space.
    expect(isSelectionGesture({ button: 0, dragged: true })).toBe(false);
    // Middle-button dolly.
    expect(isSelectionGesture({ button: 1, dragged: false })).toBe(false);
  });
});

describe('autoPointRadius', () => {
  it('shrinks as the cloud grows and holds the hand-tuned size at ~1000 points', () => {
    expect(autoPointRadius(1000)).toBeCloseTo(0.063, 3);
    expect(autoPointRadius(4000)).toBeLessThan(autoPointRadius(1000));
    expect(autoPointRadius(100)).toBeGreaterThan(autoPointRadius(1000));
  });

  it('clamps both ends so dense corpora stay clickable and tiny ones stay sane', () => {
    // Unclamped this would be 0.014 — sub-pixel, so unhoverable in practice.
    expect(autoPointRadius(20000)).toBe(0.05);
    expect(autoPointRadius(1)).toBe(0.6);
    // An empty cloud renders nothing, but must not produce NaN/Infinity.
    expect(autoPointRadius(0)).toBe(0.05);
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
    const ids = collectConnectedIds(['a', 'b'], byId, {
      similar: true,
      tags: false,
      entities: false,
    });
    expect(ids).toEqual(new Set(['a', 'b', 'x', 'y']));
  });

  it('respects layer toggles', () => {
    const byId = { a: conn('a', ['x']) };
    const ids = collectConnectedIds(['a'], byId, {
      similar: false,
      tags: false,
      entities: false,
    });
    expect(ids).toEqual(new Set(['a']));
  });
});

describe('buildEdgeBuffers', () => {
  const points = buildPointBuffers([pt('a', [0, 0, 0]), pt('x', [1, 0, 0])], baseOpts);

  it('draws one segment per enabled-layer connection with the layer colour', () => {
    const edges = buildEdgeBuffers(
      ['a'],
      { a: conn('a', ['x']) },
      { similar: true, tags: false, entities: false },
      points,
    );
    expect(edges.meta).toHaveLength(1);
    expect(edges.meta[0]).toMatchObject({ from: 'a', to: 'x', kind: 'similar' });
    expect(edges.positions).toHaveLength(6);
    // Compared channel-wise: the buffer is Float32, hexToRgb returns Float64.
    hexToRgb(EDGE_COLORS.similar).forEach((channel, i) => {
      expect(edges.colors[i]).toBeCloseTo(channel, 6);
    });
  });

  it('skips connections to points not currently visible', () => {
    const edges = buildEdgeBuffers(
      ['a'],
      { a: conn('a', ['ghost']) },
      { similar: true, tags: true, entities: true },
      points,
    );
    expect(edges.meta).toHaveLength(0);
  });

  it('dedupes the same pair within a kind but keeps distinct kinds', () => {
    const edges = buildEdgeBuffers(
      ['a'],
      { a: conn('a', ['x']) },
      { similar: true, tags: true, entities: false },
      points,
    );
    // conn() lists x under both similar and shared_tags: 1 similar + 1 tags edge.
    expect(edges.meta.map((e) => e.kind).sort()).toEqual(['similar', 'tags']);
  });
});
