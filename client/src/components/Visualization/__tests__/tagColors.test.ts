import { describe, expect, it } from 'vitest';

import { buildTagColorScale, MAX_TAG_SLOTS, OTHER_TAGS_COLOR, UNTAGGED_COLOR } from '../tagColors';

const point = (tags?: string[]) => ({ tags });

describe('buildTagColorScale', () => {
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

  it('colours untagged notes with the neutral and lists them last', () => {
    const scale = buildTagColorScale([point(['Recipes']), point(), point([])], 'light');

    expect(scale.colorFor(undefined)).toBe(UNTAGGED_COLOR);
    expect(scale.colorFor([])).toBe(UNTAGGED_COLOR);
    expect(scale.legend.at(-1)).toEqual({ label: 'Untagged', color: UNTAGGED_COLOR });
  });

  it('is deterministic under ties and independent of input order', () => {
    const a = buildTagColorScale([point(['Beta']), point(['Alpha'])], 'light');
    const b = buildTagColorScale([point(['Alpha']), point(['Beta'])], 'light');

    // Equal counts break alphabetically, so a point cannot change hue because the
    // fetch order changed.
    expect(a.colorFor(['Alpha'])).toBe(b.colorFor(['Alpha']));
    expect(a.legend.map((e) => e.label)).toEqual(['Alpha', 'Beta']);
  });

  it('colours a multi-tag note by its highest ranked tag', () => {
    const points = [point(['Recipes']), point(['Recipes']), point(['Travel'])];
    const scale = buildTagColorScale(points, 'light');

    expect(scale.colorFor(['Travel', 'Recipes'])).toBe(scale.colorFor(['Recipes']));
  });

  it('uses the dark-mode steps when the document is dark', () => {
    const points = [point(['Recipes'])];

    expect(buildTagColorScale(points, 'dark').colorFor(['Recipes'])).not.toBe(
      buildTagColorScale(points, 'light').colorFor(['Recipes']),
    );
  });
});
