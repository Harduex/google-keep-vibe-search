import { memo, useEffect, useRef, useCallback } from 'react';

import type { GroundedContext } from '@/types';
import { applyHighlight, clearHighlights, scrollToHighlight } from '@/utils/highlightApi';
import { findBestMatch } from '@/utils/levenshteinMatcher';

interface DocumentViewerProps {
  /** The full note to display. */
  noteId: string;
  noteTitle: string;
  noteContent: string;
  /** The active context item that should be highlighted. */
  activeContext: GroundedContext | null;
  /** Callback to close the viewer. */
  onClose: () => void;
}

/**
 * Side panel that shows the full text of a note with the cited
 * region highlighted and scrolled into view.
 */
export const DocumentViewer = memo(
  ({ noteTitle, noteContent, activeContext, onClose }: DocumentViewerProps) => {
    const contentRef = useRef<HTMLDivElement>(null);

    // Apply highlight whenever the active context changes
    useEffect(() => {
      const el = contentRef.current;
      if (!el) {
        return;
      }

      clearHighlights(el);

      if (!activeContext) {
        return;
      }

      // Primary: use character offsets
      if (
        activeContext.start_char_idx != null &&
        activeContext.end_char_idx != null &&
        activeContext.start_char_idx < activeContext.end_char_idx
      ) {
        applyHighlight(el, {
          start: activeContext.start_char_idx,
          end: activeContext.end_char_idx,
        });
        scrollToHighlight(el);
        return;
      }

      // Fallback: Levenshtein approximate matching on the snippet text
      if (activeContext.text) {
        const match = findBestMatch(activeContext.text, noteContent);
        if (match) {
          applyHighlight(el, { start: match.start, end: match.end });
          scrollToHighlight(el);
        }
      }
    }, [activeContext, noteContent]);

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') {
          onClose();
        }
      },
      [onClose],
    );

    return (
      <div
        className="document-viewer"
        role="complementary"
        aria-label="Document viewer"
        onKeyDown={handleKeyDown}
      >
        <div className="document-viewer-header">
          <div className="document-viewer-title">
            <span className="material-icons">description</span>
            <span>{noteTitle || 'Untitled Note'}</span>
          </div>
          <button
            className="document-viewer-close"
            onClick={onClose}
            aria-label="Close document viewer"
            title="Close"
          >
            <span className="material-icons">close</span>
          </button>
        </div>

        <div className="document-viewer-content" ref={contentRef}>
          {noteContent || 'No content.'}
        </div>
      </div>
    );
  },
);
