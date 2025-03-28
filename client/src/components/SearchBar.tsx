import { FormEvent, useState, memo, useCallback, useEffect } from 'react';

interface SearchBarProps {
  onSearch: (query: string) => void;
  currentQuery?: string;
  semanticWeight: number;
  onSemanticWeightChange: (weight: number) => void;
  threshold: number;
  onThresholdChange: (threshold: number) => void;
}

export const SearchBar = memo(
  ({
    onSearch,
    currentQuery = '',
    semanticWeight,
    onSemanticWeightChange,
    threshold,
    onThresholdChange,
  }: SearchBarProps) => {
    const [inputValue, setInputValue] = useState(currentQuery);
    const [showAdvanced, setShowAdvanced] = useState(false);

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

    const handleSemanticWeightChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        onSemanticWeightChange(parseFloat(e.target.value));
      },
      [onSemanticWeightChange],
    );

    const handleThresholdChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        onThresholdChange(parseFloat(e.target.value));
      },
      [onThresholdChange],
    );

    const toggleAdvanced = useCallback(() => {
      setShowAdvanced((prev) => !prev);
    }, []);

    return (
      <div className="search-container">
        <form onSubmit={handleSubmit}>
          <div className="search-input-container">
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
          </div>

          <div className="search-advanced">
            <button type="button" className="advanced-toggle" onClick={toggleAdvanced}>
              <span className="material-icons">{showAdvanced ? 'expand_less' : 'expand_more'}</span>
              Advanced Settings
            </button>

            {showAdvanced && (
              <div className="search-options">
                <div className="search-balance-slider">
                  <label htmlFor="semantic-slider">
                    Search Type: {Math.round((1 - semanticWeight) * 100)}% Keyword -{' '}
                    {Math.round(semanticWeight * 100)}% Semantic
                  </label>
                  <input
                    id="semantic-slider"
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={semanticWeight}
                    onChange={handleSemanticWeightChange}
                    className="slider"
                  />
                  <div className="slider-labels">
                    <span>Keyword Only</span>
                    <span>Balanced</span>
                    <span>Semantic Only</span>
                  </div>
                </div>

                <div className="search-threshold-slider">
                  <label htmlFor="threshold-slider">
                    Result Quality Threshold: {Math.round(threshold * 100)}%
                  </label>
                  <input
                    id="threshold-slider"
                    type="range"
                    min="0"
                    max="0.9"
                    step="0.1"
                    value={threshold}
                    onChange={handleThresholdChange}
                    className="slider"
                  />
                  <div className="slider-labels">
                    <span>Show All</span>
                    <span>Balanced</span>
                    <span>High Quality Only</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </form>
      </div>
    );
  },
);
