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
