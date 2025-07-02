import { useState, useCallback } from 'react';

import { Tag } from '@/types';

import './styles.css';

interface TagFilterProps {
  tags: Tag[];
  selectedTags: string[];
  onUpdateSelectedTags: (selectedTags: string[]) => void;
}

export const TagFilter = ({ tags, selectedTags, onUpdateSelectedTags }: TagFilterProps) => {
  const [isExpanded, setIsExpanded] = useState(false);

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

  // Don't render if there are no tags
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
              return (
                <div key={tag.name} className="tag-item">
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
