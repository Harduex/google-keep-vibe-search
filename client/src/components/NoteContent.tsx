import { useEffect, useRef, useState, memo, useCallback } from 'react';

import { UI_ELEMENTS } from '@/const';
import { highlightMatches } from '@/helpers';

interface NoteContentProps {
  content: string;
  query: string;
  refinementKeywords?: string;
}

export const NoteContent = memo(({ content, query, refinementKeywords }: NoteContentProps) => {
  const [isCollapsed, setIsCollapsed] = useState(true);
  const [shouldCollapse, setShouldCollapse] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (contentRef.current && contentRef.current.scrollHeight > UI_ELEMENTS.NOTE_MAX_HEIGHT) {
      setShouldCollapse(true);
    } else {
      setShouldCollapse(false);
      setIsCollapsed(false);
    }
  }, [content]);

  const toggleCollapse = useCallback(() => {
    setIsCollapsed((prev) => !prev);

    // If collapsing, scroll back to the top of the note
    if (!isCollapsed && contentRef.current) {
      const noteCard = contentRef.current.closest('.note-card');
      noteCard?.scrollIntoView({
        behavior: UI_ELEMENTS.DEFAULT_SCROLL_BEHAVIOR,
        block: 'nearest',
      });
    }
  }, [isCollapsed]);

  const highlightedContent = highlightMatches(content, query, refinementKeywords);

  return (
    <>
      <div
        ref={contentRef}
        className={`note-content ${isCollapsed && shouldCollapse ? 'collapsed-content' : ''}`}
        dangerouslySetInnerHTML={{ __html: highlightedContent }}
      />

      {shouldCollapse && (
        <button className="collapse-button" onClick={toggleCollapse}>
          <span className="material-icons">{isCollapsed ? 'expand_more' : 'expand_less'}</span>
          {isCollapsed ? 'Read more' : 'Read less'}
        </button>
      )}
    </>
  );
});
