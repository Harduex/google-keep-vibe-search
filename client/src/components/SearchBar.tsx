import { FormEvent, useState, memo, useCallback, useEffect } from 'react';

interface SearchBarProps {
  onSearch: (query: string) => void;
  /** Leave search mode: the owner drops the query and its results. */
  onClear?: () => void;
  currentQuery?: string;
}

export const SearchBar = memo(({ onSearch, onClear, currentQuery = '' }: SearchBarProps) => {
  const [inputValue, setInputValue] = useState(currentQuery);

  useEffect(() => {
    setInputValue(currentQuery);
  }, [currentQuery]);

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      onSearch(inputValue);
    },
    [inputValue, onSearch],
  );

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  }, []);

  const handleClear = useCallback(() => {
    setInputValue('');
    onClear?.();
  }, [onClear]);

  return (
    <div className="search-container">
      <form onSubmit={handleSubmit} style={{ display: 'flex', width: '100%' }}>
        <input
          type="text"
          id="search-input"
          placeholder="Search your notes by keywords or vibes..."
          value={inputValue}
          onChange={handleInputChange}
          autoFocus
        />
        {inputValue !== '' && (
          <button
            type="button"
            className="search-clear-button"
            onClick={handleClear}
            title="Clear search"
            aria-label="Clear search"
          >
            <span className="material-icons">close</span>
          </button>
        )}
        <button id="search-button" type="submit">
          Search
        </button>
      </form>
    </div>
  );
});
