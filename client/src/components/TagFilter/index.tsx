import { useState, useCallback, useRef, useEffect } from 'react';

import { Tag } from '@/types';

import './styles.css';

interface TagFilterProps {
  tags: Tag[];
  selectedTags: string[];
  onUpdateSelectedTags: (selectedTags: string[]) => void;
  onRenameTag?: (oldName: string, newName: string) => void;
  onMergeTags?: (targetTag: string) => void | Promise<void>;
}

export const TagFilter = ({
  tags,
  selectedTags,
  onUpdateSelectedTags,
  onRenameTag,
  onMergeTags,
}: TagFilterProps) => {
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

  const handleClearAll = useCallback(() => {
    onUpdateSelectedTags([]);
  }, [onUpdateSelectedTags]);

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
          `Merge ${sourceTags.join(', ')} into "${targetTag}"? All notes with the other selected tags will use "${targetTag}" instead.`,
        )
      ) {
        void onMergeTags(targetTag);
      }

      setIsMergeSelectorOpen(false);
    },
    [onMergeTags, selectedTags],
  );

  const createTagChangeHandler = useCallback(
    (tagName: string) => () => handleTagToggle(tagName),
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

  if (tags.length === 0) {
    return null;
  }

  const selectedCount = selectedTags.length;
  const canMergeSelectedTags = Boolean(onMergeTags) && selectedCount > 1;

  return (
    <div className="tag-filter">
      <div className="tag-filter-header" onClick={handleToggleExpanded}>
        <div className="tag-filter-title">
          <span className="material-icons">filter_list</span>
          <span>Filter by Tags</span>
          {selectedCount > 0 && <span className="selected-count">({selectedCount} selected)</span>}
        </div>
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
            <button className="control-button" onClick={handleClearAll}>
              Clear All
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
              const isSelected = selectedTags.includes(tag.name);
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
                    <div className="tag-item-row">
                      <label className="tag-checkbox">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={createTagChangeHandler(tag.name)}
                        />
                        <span className="checkmark"></span>
                        <span className="tag-info">
                          <span className="tag-name">{tag.name}</span>
                          <span className="tag-count">({tag.count} notes)</span>
                        </span>
                      </label>
                      {onRenameTag && (
                        <button
                          className="tag-rename-button"
                          onClick={createStartRenameHandler(tag.name)}
                          title={`Rename tag "${tag.name}"`}
                        >
                          <span className="material-icons">edit</span>
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="tag-filter-help">
            <span className="material-icons">info</span>
            <span>
              Select tags to show only notes with those tags. When no tags are selected, all notes
              are displayed. Select multiple tags to merge them into one of the selected tags.
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
