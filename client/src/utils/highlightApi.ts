/**
 * CSS Custom Highlight API wrapper with <mark> fallback.
 *
 * Uses the CSS Custom Highlight API (Chrome 105+) when available.
 * Falls back to wrapping matched ranges in <mark> elements for
 * browsers that don't support it (Firefox, older Safari).
 */

export interface HighlightRange {
  start: number;
  end: number;
}

const HIGHLIGHT_NAME = 'citation-active';

/**
 * Returns true when CSS.highlights is usable.
 */
export function isHighlightApiSupported(): boolean {
  return typeof CSS !== 'undefined' && 'highlights' in CSS;
}

/**
 * Apply a highlight to a text node within a container element.
 *
 * @param container  The DOM element containing the text
 * @param range      The character range to highlight
 */
export function applyHighlight(
  container: HTMLElement,
  range: HighlightRange,
): void {
  clearHighlights(container);

  if (isHighlightApiSupported()) {
    applyNativeHighlight(container, range);
  } else {
    applyMarkFallback(container, range);
  }
}

/**
 * Remove all active highlights from the container.
 */
export function clearHighlights(container: HTMLElement): void {
  if (isHighlightApiSupported()) {
    (CSS as any).highlights.delete(HIGHLIGHT_NAME);
  }

  // Always clean up fallback marks
  const marks = container.querySelectorAll('mark[data-citation-highlight]');
  marks.forEach((mark) => {
    const parent = mark.parentNode;
    if (parent) {
      parent.replaceChild(document.createTextNode(mark.textContent || ''), mark);
      parent.normalize();
    }
  });
}

/**
 * Scroll the container so the highlighted range is visible.
 */
export function scrollToHighlight(container: HTMLElement): void {
  const target =
    container.querySelector('mark[data-citation-highlight]') ||
    container.querySelector('[data-highlight-anchor]');

  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

// -----------------------------------------------------------------------
// Internal helpers
// -----------------------------------------------------------------------

function applyNativeHighlight(
  container: HTMLElement,
  range: HighlightRange,
): void {
  const textNodes = getTextNodes(container);
  let charCount = 0;
  let startNode: Text | null = null;
  let startOffset = 0;
  let endNode: Text | null = null;
  let endOffset = 0;

  for (const node of textNodes) {
    const nodeLen = node.textContent?.length || 0;
    const nodeStart = charCount;
    const nodeEnd = charCount + nodeLen;

    if (!startNode && range.start < nodeEnd) {
      startNode = node;
      startOffset = range.start - nodeStart;
    }
    if (!endNode && range.end <= nodeEnd) {
      endNode = node;
      endOffset = range.end - nodeStart;
      break;
    }

    charCount = nodeEnd;
  }

  if (startNode && endNode) {
    const domRange = document.createRange();
    domRange.setStart(startNode, startOffset);
    domRange.setEnd(endNode, endOffset);

    const highlight = new (window as any).Highlight(domRange);
    (CSS as any).highlights.set(HIGHLIGHT_NAME, highlight);
  }
}

function applyMarkFallback(
  container: HTMLElement,
  range: HighlightRange,
): void {
  const textNodes = getTextNodes(container);
  let charCount = 0;

  for (const node of textNodes) {
    const nodeLen = node.textContent?.length || 0;
    const nodeStart = charCount;
    const nodeEnd = charCount + nodeLen;

    // Check overlap with requested range
    const overlapStart = Math.max(range.start, nodeStart);
    const overlapEnd = Math.min(range.end, nodeEnd);

    if (overlapStart < overlapEnd) {
      const localStart = overlapStart - nodeStart;
      const localEnd = overlapEnd - nodeStart;
      const text = node.textContent || '';

      const before = document.createTextNode(text.slice(0, localStart));
      const mark = document.createElement('mark');
      mark.setAttribute('data-citation-highlight', 'true');
      mark.textContent = text.slice(localStart, localEnd);
      const after = document.createTextNode(text.slice(localEnd));

      const parent = node.parentNode;
      if (parent) {
        parent.insertBefore(before, node);
        parent.insertBefore(mark, node);
        parent.insertBefore(after, node);
        parent.removeChild(node);
      }
    }

    charCount = nodeEnd;
    if (charCount >= range.end) break;
  }
}

function getTextNodes(element: HTMLElement): Text[] {
  const nodes: Text[] = [];
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let node: Text | null;
  while ((node = walker.nextNode() as Text | null)) {
    nodes.push(node);
  }
  return nodes;
}
