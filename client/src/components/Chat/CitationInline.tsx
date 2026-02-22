import { memo, useCallback, useState } from 'react';

import type { GroundedCitation } from '@/types';

interface CitationInlineProps {
  citationId: string;
  displayNumber: number;
  citation: GroundedCitation;
  onCitationClick: (citationId: string) => void;
}

/**
 * Inline superscript citation chip rendered within message text.
 * Shows a hover tooltip with the note title and snippet.
 */
export const CitationInline = memo(
  ({ citationId, displayNumber, citation, onCitationClick }: CitationInlineProps) => {
    const [showTooltip, setShowTooltip] = useState(false);

    const handleClick = useCallback(
      (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        onCitationClick(citationId);
      },
      [citationId, onCitationClick],
    );

    return (
      <span
        className="citation-inline-wrapper"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <button
          className="citation-inline"
          onClick={handleClick}
          title={citation.note_title || citationId}
          aria-label={`Citation ${displayNumber}: ${citation.note_title || citationId}`}
        >
          {displayNumber}
        </button>

        {showTooltip && (
          <div className="citation-tooltip">
            <div className="citation-tooltip-title">{citation.note_title || 'Unknown note'}</div>
            {citation.text_snippet && (
              <div className="citation-tooltip-snippet">{citation.text_snippet}</div>
            )}
          </div>
        )}
      </span>
    );
  },
);
