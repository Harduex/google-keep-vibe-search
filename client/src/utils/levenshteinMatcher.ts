/**
 * Levenshtein-based approximate string matching.
 *
 * Used as a fallback when exact character offsets are unavailable:
 * slide a window across the source document, computing normalised
 * Levenshtein distance against the claim text, and return the position
 * of the best match.
 */

export interface MatchResult {
  /** Start index in the source text. */
  start: number;
  /** End index in the source text (exclusive). */
  end: number;
  /** Normalised distance (0 = exact match, 1 = completely different). */
  distance: number;
}

/**
 * Compute the Levenshtein distance between two strings.
 */
export function levenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;

  // Use single-row optimisation
  let prev = new Array(n + 1);
  let curr = new Array(n + 1);

  for (let j = 0; j <= n; j++) prev[j] = j;

  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(
        prev[j] + 1,      // deletion
        curr[j - 1] + 1,  // insertion
        prev[j - 1] + cost, // substitution
      );
    }
    [prev, curr] = [curr, prev];
  }

  return prev[n];
}

/**
 * Find the best approximate match of `claim` within `source`.
 *
 * Uses a sliding window with sizes ranging from 0.8x to 1.2x the
 * claim length. Returns null if no match meets the threshold
 * (default: normalised distance <= 0.3).
 */
export function findBestMatch(
  claim: string,
  source: string,
  threshold = 0.3,
): MatchResult | null {
  if (!claim || !source) return null;

  const claimLower = claim.toLowerCase();
  const sourceLower = source.toLowerCase();

  // Try exact substring match first
  const exactIdx = sourceLower.indexOf(claimLower);
  if (exactIdx !== -1) {
    return { start: exactIdx, end: exactIdx + claim.length, distance: 0 };
  }

  const claimLen = claimLower.length;
  const minWindow = Math.max(1, Math.floor(claimLen * 0.8));
  const maxWindow = Math.min(sourceLower.length, Math.ceil(claimLen * 1.2));

  let best: MatchResult | null = null;

  for (let winSize = minWindow; winSize <= maxWindow; winSize++) {
    for (let i = 0; i <= sourceLower.length - winSize; i++) {
      const window = sourceLower.slice(i, i + winSize);
      const dist = levenshtein(claimLower, window);
      const normDist = dist / Math.max(claimLen, winSize);

      if (normDist <= threshold && (best === null || normDist < best.distance)) {
        best = { start: i, end: i + winSize, distance: normDist };
      }

      // Early exit for exact match
      if (normDist === 0) return best;
    }
  }

  return best;
}
