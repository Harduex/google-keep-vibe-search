import { useState, useCallback } from 'react';

import { Tag } from '@/types';

import './styles.css';

interface TagManagerProps {
  tags: Tag[];
  excludedTags: string[];
  onUpdateExcludedTags: (excludedTags: string[]) => void;
  onRemoveTagFromAll?: (tagName: string) => void;
}

export const TagManager = ({
  tags,
  excludedTags,
  onUpdateExcludedTags,
  onRemoveTagFromAll,
}: TagManagerProps) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleToggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  const handleTagToggle = useCallback(
    (tagName: string) => {
      const isCurrentlyExcluded = excludedTags.includes(tagName);
      const newExcludedTags = isCurrentlyExcluded
        ? excludedTags.filter((tag) => tag !== tagName)
        : [...excludedTags, tagName];

      onUpdateExcludedTags(newExcludedTags);
    },
    [excludedTags, onUpdateExcludedTags],
  );

  const handleSelectAll = useCallback(() => {
    onUpdateExcludedTags(tags.map((tag) => tag.name));
  }, [tags, onUpdateExcludedTags]);

  const handleClearAll = useCallback(() => {
    onUpdateExcludedTags([]);
  }, [onUpdateExcludedTags]);

  const createTagChangeHandler = useCallback(
    (tagName: string) => () => handleTagToggle(tagName),
    [handleTagToggle],
  );

  const handleRemoveTagFromAll = useCallback(
    (tagName: string) => {
      if (
        onRemoveTagFromAll &&
        window.confirm(`Are you sure you want to remove the tag "${tagName}" from all notes?`)
      ) {
        onRemoveTagFromAll(tagName);
      }
    },
    [onRemoveTagFromAll],
  );

  const createRemoveTagHandler = useCallback(
    (tagName: string) => () => handleRemoveTagFromAll(tagName),
    [handleRemoveTagFromAll],
  );

  if (tags.length === 0) {
    return null;
  }

  const excludedCount = excludedTags.length;

  return (
    <div className="tag-manager">
      <div className="tag-manager-header" onClick={handleToggleExpanded}>
        <div className="tag-manager-title">
          <span className="material-icons">label</span>
          <span>Tag Filters</span>
          {excludedCount > 0 && <span className="excluded-count">({excludedCount} excluded)</span>}
        </div>
        <span className={`material-icons expand-icon ${isExpanded ? 'expanded' : ''}`}>
          expand_more
        </span>
      </div>

      {isExpanded && (
        <div className="tag-manager-content">
          <div className="tag-manager-controls">
            <button className="control-button" onClick={handleSelectAll}>
              Exclude All
            </button>
            <button className="control-button" onClick={handleClearAll}>
              Include All
            </button>
          </div>

          <div className="tag-list">
            {tags.map((tag) => {
              const isExcluded = excludedTags.includes(tag.name);
              return (
                <div key={tag.name} className="tag-item">
                  <label className="tag-checkbox">
                    <input
                      type="checkbox"
                      checked={isExcluded}
                      onChange={createTagChangeHandler(tag.name)}
                    />
                    <span className="checkmark"></span>
                    <span className="tag-info">
                      <span className="tag-name">{tag.name}</span>
                      <span className="tag-count">({tag.count} notes)</span>
                    </span>
                  </label>
                  {onRemoveTagFromAll && (
                    <button
                      className="remove-tag-button"
                      onClick={createRemoveTagHandler(tag.name)}
                    >
                      <span className="material-icons">remove_circle</span>
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          <div className="tag-manager-help">
            <span className="material-icons">info</span>
            <span>
              Excluded tags will be hidden from search results. Use this to progressively categorize
              your notes. Click the red button to permanently remove a tag from all notes that have
              it.
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
