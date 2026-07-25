/**
 * Tag colour assignment for the 3D map.
 *
 * The palette and the three-slot cap are not taste. A scatter plot puts every pair of
 * colours side by side, so the palette has to clear colour-vision separation on *all*
 * pairs, not just adjacent ones — and only the first three categorical slots do. Both
 * trios below were validated with the data-viz palette checker at all-pairs:
 *
 *   light (#fcfcfb surface): CVD ΔE 9.2, normal-vision ΔE 24.0 — all checks pass
 *   dark  (#1a1a19 surface): CVD ΔE 9.4, normal-vision ΔE 20.9 — all checks pass
 *
 * A fourth hue would put yellow next to orange and fail. So the three most common tags
 * get a hue each and everything else folds into "Other tags"; identity is never colour
 * alone — the legend labels every swatch and hovering a point names its tags.
 */

export const UNTAGGED_COLOR = '#9e9e9e';
export const OTHER_TAGS_COLOR = '#6b7280';

const CATEGORICAL = {
  light: ['#2a78d6', '#eb6834', '#1baf7a'],
  dark: ['#3987e5', '#d95926', '#199e70'],
} as const;

/** How many tags get a hue of their own before the rest fold into "Other tags". */
export const MAX_TAG_SLOTS = 3;

export interface TagLegendEntry {
  label: string;
  color: string;
}

export interface TagColorScale {
  /** Colour for one point, by the tags it carries. */
  colorFor: (tags: string[] | undefined) => string;
  /** Swatches to render, in slot order, ending with Other/Untagged when they apply. */
  legend: TagLegendEntry[];
}

/**
 * Build a colour scale from the tags actually present on the points.
 *
 * Slots go to the most common tags, ties broken alphabetically so the same corpus always
 * produces the same colours — a point must not change hue because the fetch order did.
 * A note with several tags is coloured by its highest-ranked one.
 */
export const buildTagColorScale = (
  points: { tags?: string[] }[],
  mode: 'light' | 'dark' = 'light',
): TagColorScale => {
  const counts = new Map<string, number>();
  points.forEach((point) => {
    (point.tags || []).forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1));
  });

  const ranked = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([tag]) => tag);

  const palette = CATEGORICAL[mode];
  const slots = new Map<string, string>();
  ranked.slice(0, MAX_TAG_SLOTS).forEach((tag, i) => slots.set(tag, palette[i]));

  const hasOther = ranked.length > MAX_TAG_SLOTS;
  const hasUntagged = points.some((point) => !point.tags || point.tags.length === 0);

  const colorFor = (tags: string[] | undefined): string => {
    if (!tags || tags.length === 0) {
      return UNTAGGED_COLOR;
    }
    for (const tag of ranked) {
      if (tags.includes(tag)) {
        return slots.get(tag) || OTHER_TAGS_COLOR;
      }
    }
    return OTHER_TAGS_COLOR;
  };

  const legend: TagLegendEntry[] = [...slots.entries()].map(([label, color]) => ({ label, color }));
  if (hasOther) {
    legend.push({ label: 'Other tags', color: OTHER_TAGS_COLOR });
  }
  if (hasUntagged) {
    legend.push({ label: 'Untagged', color: UNTAGGED_COLOR });
  }

  return { colorFor, legend };
};
