import { memo, useCallback } from 'react';

export type SearchMode = 'text' | 'image';

interface SearchModeToggleProps {
  activeMode: SearchMode;
  onChange: (mode: SearchMode) => void;
}

export const SearchModeToggle = memo(({ activeMode, onChange }: SearchModeToggleProps) => {
  const onTextSearchClick = useCallback(() => {
    onChange('text');
  }, [onChange]);

  const onImageSearchClick = useCallback(() => {
    onChange('image');
  }, [onChange]);

  return (
    <div className="search-mode-toggle">
      <button
        type="button"
        className={`search-mode-button ${activeMode === 'text' ? 'active' : ''}`}
        onClick={onTextSearchClick}
        aria-label="Search by text"
      >
        <span className="material-icons">text_fields</span>
        <span>Text Search</span>
      </button>
      <button
        type="button"
        className={`search-mode-button ${activeMode === 'image' ? 'active' : ''}`}
        onClick={onImageSearchClick}
        aria-label="Search by image"
      >
        <span className="material-icons">image_search</span>
        <span>Image Search</span>
      </button>
    </div>
  );
});
