import { FormEvent, useState, memo, useCallback, useEffect } from 'react';

interface SearchBarProps {
  onSearch: (query: string) => void;
  currentQuery?: string;
}

export const SearchBar = memo(({ onSearch, currentQuery = '' }: SearchBarProps) => {
  const [inputValue, setInputValue] = useState(currentQuery);

  useEffect(() => {
    setInputValue(currentQuery);
  }, [currentQuery]);

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      onSearch(inputValue);
    },
    [inputValue, onSearch]
  );

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  }, []);

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
        <button id="search-button" type="submit">
          Search
        </button>
      </form>
    </div>
  );
});

SearchBar.displayName = 'SearchBar';
