/**
 * Parse [citation:ID] markers from LLM response text.
 *
 * Returns a ParsedContent object containing:
 * - cleanText: text with citation markers stripped
 * - citations: unique GroundedCitation objects found
 * - segments: ordered list of text/citation segments for rendering
 */

import type { ContentSegment, GroundedCitation, GroundedContext, ParsedContent } from '@/types';

const CITATION_PATTERN = /\[citation:([^\]]+)\]/g;

/**
 * Parse inline [citation:ID] markers from response text.
 */
export function parseCitations(
  text: string,
  contextItems: GroundedContext[],
): ParsedContent {
  const contextMap = new Map<string, GroundedContext>();
  for (const item of contextItems) {
    contextMap.set(item.citation_id, item);
  }

  const segments: ContentSegment[] = [];
  const citationMap = new Map<string, GroundedCitation>();

  let lastIndex = 0;
  let match: RegExpExecArray | null;
  const regex = new RegExp(CITATION_PATTERN.source, 'g');

  while ((match = regex.exec(text)) !== null) {
    // Add preceding plain text
    if (match.index > lastIndex) {
      segments.push({
        type: 'text',
        text: text.slice(lastIndex, match.index),
      });
    }

    const citationId = match[1].trim();
    const ctx = contextMap.get(citationId);

    if (!citationMap.has(citationId)) {
      citationMap.set(citationId, {
        citation_id: citationId,
        note_id: ctx?.note_id ?? '',
        note_title: ctx?.note_title ?? '',
        start_char_idx: ctx?.start_char_idx ?? null,
        end_char_idx: ctx?.end_char_idx ?? null,
        text_snippet: ctx ? (ctx.text.length > 200 ? ctx.text.slice(0, 200) + '...' : ctx.text) : '',
      });
    }

    segments.push({
      type: 'citation',
      text: match[0],
      citationId,
    });

    lastIndex = regex.lastIndex;
  }

  // Add trailing text
  if (lastIndex < text.length) {
    segments.push({
      type: 'text',
      text: text.slice(lastIndex),
    });
  }

  // Build clean text (citations stripped)
  const cleanText = text.replace(CITATION_PATTERN, '').replace(/\s{2,}/g, ' ').trim();

  return {
    cleanText,
    citations: Array.from(citationMap.values()),
    segments,
  };
}

/**
 * Assign sequential display numbers to citation IDs.
 * Returns a map of citationId -> display number (1-indexed).
 */
export function buildCitationNumberMap(
  citations: GroundedCitation[],
): Map<string, number> {
  const map = new Map<string, number>();
  let n = 1;
  for (const c of citations) {
    if (!map.has(c.citation_id)) {
      map.set(c.citation_id, n++);
    }
  }
  return map;
}
