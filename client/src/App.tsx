import { useCallback, useMemo, useState } from 'react';

import { AllNotes } from '@/components/AllNotes';
import { Chat } from '@/components/Chat';
import { ErrorDisplay } from '@/components/ErrorDisplay';
import { GalleryProvider, GalleryOverlay } from '@/components/ImageGallery';
import { NotesClusters } from '@/components/NotesClusters';
import { Results } from '@/components/Results';
import { SearchBar } from '@/components/SearchBar';
import { TabNavigation, TabId } from '@/components/TabNavigation';
import { UI_ELEMENTS } from '@/const';
import { formatStatsText, scrollToElement } from '@/helpers';
import { useSearch } from '@/hooks/useSearch';
import { useStats } from '@/hooks/useStats';
import { useTheme } from '@/hooks/useTheme';

import './App.css';

const App = () => {
  const { theme, toggleTheme } = useTheme();
  const { stats, error: statsError, refetchStats } = useStats();
  const {
    query,
    results,
    originalResults,
    refinementKeywords,
    isLoading,
    hasSearched,
    isRefined,
    performSearch,
    refineResults,
    resetRefinement,
    error: searchError,
  } = useSearch();

  // Add state for active tab
  const [activeTab, setActiveTab] = useState<TabId>('search');

  const handleSearch = useCallback(
    (searchQuery: string) => {
      performSearch(searchQuery);
      setActiveTab('search'); // Switch to search tab when performing a search
      scrollToElement('.search-container', UI_ELEMENTS.SEARCH_OFFSET);
    },
    [performSearch],
  );

  const handleRefinement = useCallback(
    (keywords: string) => {
      refineResults(keywords);
    },
    [refineResults],
  );

  const handleDismissError = useCallback(() => {
    if (statsError) {
      refetchStats();
    }
  }, [statsError, refetchStats]);

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

        {/* Navigation tabs */}
        <TabNavigation activeTab={activeTab} onChange={setActiveTab} />

        {/* Show search bar only in search tab */}
        {activeTab === 'search' && <SearchBar onSearch={handleSearch} currentQuery={query} />}

        {/* Show content based on active tab */}
        {activeTab === 'search' && (
          <Results
            query={query}
            results={results}
            originalResults={originalResults}
            refinementKeywords={refinementKeywords}
            isLoading={isLoading}
            hasSearched={hasSearched}
            isRefined={isRefined}
            onShowRelated={handleSearch}
            onRefine={handleRefinement}
            onResetRefinement={resetRefinement}
          />
        )}

        {activeTab === 'all-notes' && <AllNotes onShowRelated={handleSearch} />}

        {activeTab === 'clusters' && <NotesClusters query={query} onShowRelated={handleSearch} />}

        {activeTab === 'chat' && <Chat query={query} onShowRelated={handleSearch} />}

        <ErrorDisplay error={error} onDismiss={handleDismissError} />
        <GalleryOverlay />
      </div>
    </GalleryProvider>
  );
};

export default App;
