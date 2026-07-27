import { useCallback, useMemo, useState } from 'react';

/** How many tags the chip row offers before "show all" — the vocabulary can be large. */
const VISIBLE_TAG_LIMIT = 12;

export interface ChatScopeProps {
  availableTags: { name: string; count: number }[];
  selectedTags: string[];
  onSelectedTagsChange: (tags: string[]) => void;
  dateRange: { start?: string; end?: string };
  onDateRangeChange: (range: { start?: string; end?: string }) => void;
  disabled?: boolean;
}

/**
 * Tag + date scope for chat retrieval, the replacement for the old Topic input.
 *
 * Whatever is set here bounds every probe the agent makes, so an empty scope means "the
 * whole corpus" — the same default as before.
 */
export const ChatScope = ({
  availableTags,
  selectedTags,
  onSelectedTagsChange,
  dateRange,
  onDateRangeChange,
  disabled = false,
}: ChatScopeProps) => {
  const [expanded, setExpanded] = useState(false);
  const [showAllTags, setShowAllTags] = useState(false);

  const activeCount = selectedTags.length + (dateRange.start || dateRange.end ? 1 : 0);

  // Selected tags stay visible even when they fall outside the top slice, otherwise
  // collapsing the list would hide an active filter.
  const shownTags = useMemo(() => {
    if (showAllTags) {
      return availableTags;
    }
    const top = availableTags.slice(0, VISIBLE_TAG_LIMIT);
    const missing = availableTags.filter(
      (tag) => selectedTags.includes(tag.name) && !top.some((t) => t.name === tag.name),
    );
    return [...top, ...missing];
  }, [availableTags, selectedTags, showAllTags]);

  const toggleTag = useCallback(
    (name: string) => {
      onSelectedTagsChange(
        selectedTags.includes(name)
          ? selectedTags.filter((t) => t !== name)
          : [...selectedTags, name],
      );
    },
    [selectedTags, onSelectedTagsChange],
  );

  const clearScope = useCallback(() => {
    onSelectedTagsChange([]);
    onDateRangeChange({});
  }, [onSelectedTagsChange, onDateRangeChange]);

  return (
    <div className="chat-scope">
      <div className="chat-scope-controls">
        <button
          type="button"
          className="chat-scope-toggle"
          onClick={() => setExpanded((prev) => !prev)}
          aria-expanded={expanded}
          title={expanded ? 'Hide search scope' : 'Limit which notes are searched'}
        >
          <span className="material-icons">{expanded ? 'expand_less' : 'expand_more'}</span>
          <span>Scope</span>
          {activeCount > 0 && <span className="chat-scope-badge">{activeCount}</span>}
        </button>
        {activeCount > 0 && (
          <button type="button" className="chat-scope-clear" onClick={clearScope}>
            Clear
          </button>
        )}
      </div>

      {expanded && (
        <div className="chat-scope-panel">
          {availableTags.length > 0 ? (
            <div className="chat-scope-tags">
              {shownTags.map((tag) => (
                <button
                  key={tag.name}
                  type="button"
                  className={`chat-scope-chip${selectedTags.includes(tag.name) ? ' selected' : ''}`}
                  onClick={() => toggleTag(tag.name)}
                  disabled={disabled}
                  aria-pressed={selectedTags.includes(tag.name)}
                >
                  {tag.name}
                  <span className="chat-scope-chip-count">{tag.count}</span>
                </button>
              ))}
              {availableTags.length > VISIBLE_TAG_LIMIT && (
                <button
                  type="button"
                  className="chat-scope-more"
                  onClick={() => setShowAllTags((prev) => !prev)}
                >
                  {showAllTags ? 'Show fewer' : `+${availableTags.length - VISIBLE_TAG_LIMIT} more`}
                </button>
              )}
            </div>
          ) : (
            <p className="chat-scope-empty">No tags yet — categorize your notes to scope by tag.</p>
          )}

          <div className="chat-scope-dates">
            <label htmlFor="chat-scope-start">Created from</label>
            <input
              id="chat-scope-start"
              name="scope_start"
              type="date"
              value={dateRange.start || ''}
              max={dateRange.end || undefined}
              disabled={disabled}
              onChange={(e) =>
                onDateRangeChange({ ...dateRange, start: e.target.value || undefined })
              }
            />
            <label htmlFor="chat-scope-end">to</label>
            <input
              id="chat-scope-end"
              name="scope_end"
              type="date"
              value={dateRange.end || ''}
              min={dateRange.start || undefined}
              disabled={disabled}
              onChange={(e) =>
                onDateRangeChange({ ...dateRange, end: e.target.value || undefined })
              }
            />
          </div>
        </div>
      )}
    </div>
  );
};
