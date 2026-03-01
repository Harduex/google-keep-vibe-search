import { useState, useCallback, useRef } from 'react';

import { Tag } from '@/types';

import './styles.css';

interface TagFilterProps {
  tags: Tag[];
  selectedTags: string[];
  onUpdateSelectedTags: (selectedTags: string[]) => void;
  onRenameTag?: (oldName: string, newName: string) => void;
}

export const TagFilter = ({
  tags,
  selectedTags,
  onUpdateSelectedTags,
  onRenameTag,
}: TagFilterProps) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [editingTag, setEditingTag] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const editCommittedRef = useRef(false);

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

  const createTagChangeHandler = useCallback(
    (tagName: string) => () => handleTagToggle(tagName),
    [handleTagToggle],
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

  if (tags.length === 0) {
    return null;
  }

  const selectedCount = selectedTags.length;

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
          </div>

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
                          onChange={(e) => setEditValue(e.target.value)}
                          onKeyDown={(e) => handleRenameKeyDown(e, tag.name)}
                          onBlur={() => handleRenameBlur(tag.name)}
                          autoFocus
                        />
                        <button
                          className="tag-rename-confirm"
                          onMouseDown={(e) => {
                            e.preventDefault();
                            handleRenameSubmit(tag.name);
                          }}
                        >
                          <span className="material-icons">check</span>
                        </button>
                        <button
                          className="tag-rename-cancel"
                          onMouseDown={(e) => {
                            e.preventDefault();
                            editCommittedRef.current = true;
                            setEditingTag(null);
                          }}
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
                          onClick={(e) => handleStartRename(e, tag.name)}
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
              are displayed.
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
