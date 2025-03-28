import { useState, memo, useCallback, useEffect } from 'react';

interface RefinementSearchBarProps {
  onRefine: (keywords: string) => void;
  isVisible: boolean;
}

export const RefinementSearchBar = memo(({ onRefine, isVisible }: RefinementSearchBarProps) => {
  const [inputValue, setInputValue] = useState('');

  // Apply refinement filtering with each keystroke
  useEffect(() => {
    onRefine(inputValue);
  }, [inputValue, onRefine]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  }, []);

  const handleClearInput = useCallback(() => {
    setInputValue('');
  }, []);

  if (!isVisible) {
    return null;
  }

  return (
    <div className="refinement-search-container">
      <div className="refinement-input-wrapper">
        <span className="material-icons refinement-search-icon">filter_alt</span>
        <input
          type="text"
          id="refinement-search-input"
          placeholder="Refine results with keywords (comma separated)..."
          value={inputValue}
          onChange={handleInputChange}
          autoFocus
        />
        {inputValue && (
          <button
            className="refinement-clear-button"
            onClick={handleClearInput}
            title="Clear refinement"
          >
            <span className="material-icons">close</span>
          </button>
        )}
      </div>
    </div>
  );
});
