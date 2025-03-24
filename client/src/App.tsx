import { useCallback, useMemo } from 'react';

import { UI_ELEMENTS } from '@/const';
import { useSearch } from '@/hooks/useSearch';
import { useStats } from '@/hooks/useStats';
import { useTheme } from '@/hooks/useTheme';
import { formatStatsText, scrollToElement } from '@/helpers';

import { ErrorDisplay } from '@/components/ErrorDisplay';
import { Results } from '@/components/Results';
import { SearchBar } from '@/components/SearchBar';
import { GalleryProvider, GalleryOverlay } from '@/components/ImageGallery';

import './App.css';

const App = () => {
  const { theme, toggleTheme } = useTheme();
  const { stats, error: statsError, refetchStats } = useStats();
  const { query, results, isLoading, hasSearched, performSearch, error: searchError } = useSearch();

  const handleSearch = useCallback(
    (searchQuery: string) => {
      performSearch(searchQuery);
      scrollToElement('.search-container', UI_ELEMENTS.SEARCH_OFFSET);
    },
    [performSearch]
  );

  const statsText = useMemo(() => {
    if (!stats) {
      return 'Loading notes...';
    }
    return formatStatsText(stats.total_notes, stats.archived_notes, stats.pinned_notes);
  }, [stats]);

  const error = statsError || searchError;

  return (
    <GalleryProvider>
      <div className="container">
        <header>
          <h1>Google Keep Vibe Search</h1>
          <div className="stats" id="stats">
            {statsText}
          </div>
          <button
            id="theme-toggle"
            className="theme-toggle"
            aria-label="Toggle dark mode"
            onClick={toggleTheme}
          >
            <span className="material-icons">{theme === 'DARK' ? 'light_mode' : 'dark_mode'}</span>
          </button>
        </header>

        <SearchBar onSearch={handleSearch} currentQuery={query} />
        <Results
          query={query}
          results={results}
          isLoading={isLoading}
          hasSearched={hasSearched}
          onShowRelated={handleSearch}
        />

        <ErrorDisplay error={error} onDismiss={statsError ? refetchStats : () => {}} />
        <GalleryOverlay />
      </div>
    </GalleryProvider>
  );
};

export default App;
