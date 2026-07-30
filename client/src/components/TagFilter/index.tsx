import { useState, useCallback, useRef, useEffect } from 'react';

import { TagFilterState, isFiltering, tagFilterMode } from '@/tagFilter';
import { Tag } from '@/types';

import './styles.css';

interface TagFilterProps {
  tags: Tag[];
  /** Which tags are shown and hidden. A view filter over the notes list — not the
   *  search-wide exclusion behind /api/tags/excluded, which `useTags`' excluded-tags
   *  state owns. */
  filter: TagFilterState;
  onUpdateSelectedTags: (selectedTags: string[]) => void;
  /** Flip one tag's exclusion. The owner applies the transition, so the shown/hidden
   *  invariant is enforced in one place rather than re-derived here. */
  onToggleExcluded: (tagName: string) => void;
  /** Drop every filter at once. */
  onClearFilter: () => void;
  onRenameTag?: (oldName: string, newName: string) => void;
  onMergeTags?: (targetTag: string) => void | Promise<void>;
  onExportTag?: (tagName: string) => void;
}

export const TagFilter = ({
  tags,
  filter,
  onUpdateSelectedTags,
  onToggleExcluded,
  onClearFilter,
  onRenameTag,
  onMergeTags,
  onExportTag,
}: TagFilterProps) => {
  const { included: selectedTags, excluded: excludedTags } = filter;
  const [isExpanded, setIsExpanded] = useState(false);
  const [editingTag, setEditingTag] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [isMergeSelectorOpen, setIsMergeSelectorOpen] = useState(false);
  const editCommittedRef = useRef(false);

  useEffect(() => {
    if (selectedTags.length < 2) {
      setIsMergeSelectorOpen(false);
    }
  }, [selectedTags]);

  const handleToggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  const handleTagToggle = useCallback(
    (tagName: string) => {
      const isCurrentlySelected = selectedTags.includes(tagName);
      const newSelectedTags = isCurrentlySelected
        ? selectedTags.filter((tag) => tag !== tagName)
        : [...selectedTags, tagName];

      onUpdateSelectedTags(newSelectedTags);
    },
    [selectedTags, onUpdateSelectedTags],
  );

  const handleSelectAll = useCallback(() => {
    onUpdateSelectedTags(tags.map((tag) => tag.name));
  }, [tags, onUpdateSelectedTags]);

  const handleClearAll = onClearFilter;

  const createExcludeHandler = useCallback(
    (tagName: string) => (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      onToggleExcluded(tagName);
    },
    [onToggleExcluded],
  );

  const handleToggleMergeSelector = useCallback(() => {
    setIsMergeSelectorOpen((prev) => !prev);
  }, []);

  const handleMergeSelect = useCallback(
    (targetTag: string) => {
      if (!onMergeTags) {
        return;
      }

      const sourceTags = selectedTags.filter((tag) => tag !== targetTag);
      if (
        window.confirm(
          `Merge ${sourceTags.join(
            ', ',
          )} into "${targetTag}"? All notes with the other selected tags will use "${targetTag}" instead.`,
        )
      ) {
        void onMergeTags(targetTag);
      }

      setIsMergeSelectorOpen(false);
    },
    [onMergeTags, selectedTags],
  );

  const createTagChangeHandler = useCallback(
    (tagName: string) => (e: React.MouseEvent) => {
      e.stopPropagation();
      handleTagToggle(tagName);
    },
    [handleTagToggle],
  );

  const createMergeHandler = useCallback(
    (tagName: string) => () => handleMergeSelect(tagName),
    [handleMergeSelect],
  );

  const handleStartRename = useCallback((e: React.MouseEvent, tagName: string) => {
    e.stopPropagation();
    e.preventDefault();
    editCommittedRef.current = false;
    setEditingTag(tagName);
    setEditValue(tagName);
  }, []);

  const handleRenameSubmit = useCallback(
    (oldName: string) => {
      const trimmed = editValue.trim();
      if (trimmed && trimmed !== oldName && onRenameTag && !editCommittedRef.current) {
        editCommittedRef.current = true;
        onRenameTag(oldName, trimmed);
      } else {
        editCommittedRef.current = true;
      }
      setEditingTag(null);
    },
    [editValue, onRenameTag],
  );

  const handleRenameKeyDown = useCallback(
    (e: React.KeyboardEvent, oldName: string) => {
      if (e.key === 'Enter') {
        handleRenameSubmit(oldName);
      } else if (e.key === 'Escape') {
        editCommittedRef.current = true;
        setEditingTag(null);
      }
    },
    [handleRenameSubmit],
  );

  const handleRenameBlur = useCallback(
    (oldName: string) => {
      if (!editCommittedRef.current) {
        handleRenameSubmit(oldName);
      } else {
        setEditingTag(null);
      }
    },
    [handleRenameSubmit],
  );

  const handleRenameInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setEditValue(e.target.value);
  }, []);

  const createRenameKeyDownHandler = useCallback(
    (oldName: string) => (e: React.KeyboardEvent) => handleRenameKeyDown(e, oldName),
    [handleRenameKeyDown],
  );

  const createRenameBlurHandler = useCallback(
    (oldName: string) => () => handleRenameBlur(oldName),
    [handleRenameBlur],
  );

  const createRenameSubmitMouseDownHandler = useCallback(
    (oldName: string) => (e: React.MouseEvent) => {
      e.preventDefault();
      handleRenameSubmit(oldName);
    },
    [handleRenameSubmit],
  );

  const handleRenameCancelMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    editCommittedRef.current = true;
    setEditingTag(null);
  }, []);

  const createStartRenameHandler = useCallback(
    (tagName: string) => (e: React.MouseEvent) => handleStartRename(e, tagName),
    [handleStartRename],
  );

  const stopPropagation = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
  }, []);

  const createExportTagHandler = useCallback(
    (tagName: string) => () => onExportTag?.(tagName),
    [onExportTag],
  );

  if (tags.length === 0) {
    return null;
  }

  const canMergeSelectedTags = Boolean(onMergeTags) && selectedTags.length > 1;
  // With a filter on, the panel sticks to the top of the viewport: the filtered list can be
  // long, and turning a tag off meant scrolling back up to reach this control.
  const filtering = isFiltering(filter);

  return (
    <div className={`tag-filter${filtering ? ' sticky' : ''}`}>
      <div className="tag-filter-header" onClick={handleToggleExpanded}>
        <div className="tag-filter-title">
          <span className="material-icons">filter_list</span>
          <span>Filter by Tags</span>
          {!filtering && <span className="selected-count">all notes</span>}
        </div>

        {/* Active filters live in the header, so they can be read and dropped while the panel
            is collapsed and stuck to the top of a long list. */}
        {filtering && (
          <div className="active-filter-chips" onClick={stopPropagation}>
            {selectedTags.map((tagName) => (
              <button
                key={`in-${tagName}`}
                className="filter-chip include"
                onClick={createTagChangeHandler(tagName)}
                title={`Stop showing only "${tagName}"`}
                aria-label={`Stop showing only "${tagName}"`}
              >
                <span className="material-icons">visibility</span>
                <span className="chip-label">{tagName}</span>
                <span className="material-icons chip-dismiss">close</span>
              </button>
            ))}
            {excludedTags.map((tagName) => (
              <button
                key={`ex-${tagName}`}
                className="filter-chip exclude"
                onClick={createExcludeHandler(tagName)}
                title={`Stop hiding "${tagName}"`}
                aria-label={`Stop hiding "${tagName}"`}
              >
                <span className="material-icons">visibility_off</span>
                <span className="chip-label">{tagName}</span>
                <span className="material-icons chip-dismiss">close</span>
              </button>
            ))}
            <button className="filter-chip clear-all" onClick={handleClearAll}>
              Clear all
            </button>
          </div>
        )}

        <span className={`material-icons expand-icon ${isExpanded ? 'expanded' : ''}`}>
          expand_more
        </span>
      </div>

      {isExpanded && (
        <div className="tag-filter-content">
          <div className="tag-filter-controls">
            <button className="control-button" onClick={handleSelectAll}>
              Select All
            </button>
            {canMergeSelectedTags && (
              <button
                className={`control-button merge-button ${isMergeSelectorOpen ? 'active' : ''}`}
                onClick={handleToggleMergeSelector}
                type="button"
              >
                Merge Selected
              </button>
            )}
          </div>

          {canMergeSelectedTags && isMergeSelectorOpen && (
            <div className="tag-filter-merge-selector">
              <span className="merge-label">Keep this tag:</span>
              <div className="tag-filter-merge-targets">
                {selectedTags.map((tagName) => (
                  <button
                    key={tagName}
                    className="merge-target-btn"
                    onClick={createMergeHandler(tagName)}
                    type="button"
                  >
                    {tagName}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="tag-list">
            {tags.map((tag) => {
              const mode = tagFilterMode(filter, tag.name);
              const isSelected = mode === 'included';
              const isExcluded = mode === 'excluded';
              const isEditing = editingTag === tag.name;
              return (
                <div key={tag.name} className="tag-item">
                  {isEditing ? (
                    <div className="tag-rename-row">
                      <div className="tag-rename-input-group">
                        <input
                          type="text"
                          className="tag-rename-input"
                          value={editValue}
                          onChange={handleRenameInputChange}
                          onKeyDown={createRenameKeyDownHandler(tag.name)}
                          onBlur={createRenameBlurHandler(tag.name)}
                          autoFocus
                        />
                        <button
                          className="tag-rename-confirm"
                          onMouseDown={createRenameSubmitMouseDownHandler(tag.name)}
                        >
                          <span className="material-icons">check</span>
                        </button>
                        <button
                          className="tag-rename-cancel"
                          onMouseDown={handleRenameCancelMouseDown}
                        >
                          <span className="material-icons">close</span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div
                      className={`tag-item-row${isSelected ? ' included' : ''}${
                        isExcluded ? ' excluded' : ''
                      }`}
                    >
                      <span className="tag-info">
                        <span className="tag-name">{tag.name}</span>
                        <span className="tag-count">{tag.count} notes</span>
                      </span>
                      <div className="tag-row-actions">
                        {onRenameTag && (
                          <button
                            className="tag-rename-button"
                            onClick={createStartRenameHandler(tag.name)}
                            title={`Rename tag "${tag.name}"`}
                            aria-label={`Rename tag "${tag.name}"`}
                          >
                            <span className="material-icons">edit</span>
                          </button>
                        )}
                        {onExportTag && (
                          <button
                            className="export-tag-button"
                            onClick={createExportTagHandler(tag.name)}
                            title={`Export all notes tagged "${tag.name}"`}
                            aria-label={`Export all notes tagged "${tag.name}"`}
                          >
                            <span className="material-icons">download</span>
                          </button>
                        )}
                        {/* One segmented control per row rather than a checkbox plus a
                            separate exclude button: show and hide are two values of the
                            same decision, so they belong in one control. */}
                        <div className="tag-state-toggle" role="group">
                          <button
                            className={`tag-state-option include${isSelected ? ' active' : ''}`}
                            onClick={createTagChangeHandler(tag.name)}
                            aria-pressed={isSelected}
                            title={
                              isSelected
                                ? `Stop showing only "${tag.name}"`
                                : `Show only notes tagged "${tag.name}"`
                            }
                            aria-label={`Show only notes tagged "${tag.name}"`}
                          >
                            <span className="material-icons">visibility</span>
                          </button>
                          <button
                            className={`tag-state-option exclude${isExcluded ? ' active' : ''}`}
                            onClick={createExcludeHandler(tag.name)}
                            aria-pressed={isExcluded}
                            title={
                              isExcluded
                                ? `Stop hiding "${tag.name}"`
                                : `Hide notes tagged "${tag.name}"`
                            }
                            aria-label={`Hide notes tagged "${tag.name}"`}
                          >
                            <span className="material-icons">visibility_off</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="tag-filter-help">
            <span className="material-icons">info</span>
            <span>
              Select tags to show only notes with those tags; when nothing is selected, all notes
              are displayed. The block icon hides a tag's notes instead, and wins over a selection.
              Select multiple tags to merge them into one of the selected tags.
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
