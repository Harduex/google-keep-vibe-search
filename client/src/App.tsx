import { useCallback, useMemo, useState } from 'react';

import { AllNotes } from '@/components/AllNotes';
import { Chat } from '@/components/Chat';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ErrorDisplay } from '@/components/ErrorDisplay';
import { GalleryProvider, GalleryOverlay } from '@/components/ImageGallery';
import { ImageSearchUpload } from '@/components/ImageSearchUpload';
import { NotesClusters } from '@/components/NotesClusters';
import { Results } from '@/components/Results';
import { SearchBar } from '@/components/SearchBar';
import { SearchModeToggle, type SearchMode } from '@/components/SearchModeToggle';
import { TabNavigation, TabId } from '@/components/TabNavigation';
import { UI_ELEMENTS } from '@/const';
import { formatStatsText, scrollToElement } from '@/helpers';
import { useSearch } from '@/hooks/useSearch';
import { useStats } from '@/hooks/useStats';
import { useTheme } from '@/hooks/useTheme';

import './App.css';
import { Note } from './types';

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
    setResults,
    setLoading,
    error: searchError,
  } = useSearch();

  // Add state for active tab
  const [activeTab, setActiveTab] = useState<TabId>('search');
  // Add state for search mode
  const [searchMode, setSearchMode] = useState<SearchMode>('text');

  const handleSearch = useCallback(
    (searchQuery: string) => {
      performSearch(searchQuery);
      setActiveTab('search'); // Switch to search tab when performing a search
      scrollToElement('.search-container', UI_ELEMENTS.SEARCH_OFFSET);
    },
    [performSearch],
  );

  const handleImageSearchResults = useCallback(
    (searchResults: Note[]) => {
      setResults(searchResults);
      setLoading(false);
      // Reset any refinement that might have been applied
      if (isRefined) {
        resetRefinement();
      }
    },
    [setResults, setLoading, isRefined, resetRefinement],
  );

  const handleImageSearchStart = useCallback(() => {
    setLoading(true);
  }, [setLoading]);

  const handleSearchModeChange = useCallback((mode: SearchMode) => {
    setSearchMode(mode);
  }, []);

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

  const handleResultsUpdate = useCallback(() => {
    // Re-perform the current search to get updated results
    if (query) {
      performSearch(query);
    }
  }, [query, performSearch]);

  const handleTabSwitch = useCallback((tab: string) => {
    setActiveTab(tab as TabId);
  }, []);

  const statsText = useMemo(() => {
    if (!stats) {
      return 'Loading notes...';
    }
    return formatStatsText(stats.total_notes, stats.archived_notes, stats.pinned_notes);
  }, [stats]);

  const error = statsError || searchError;

  const showImageSearchEnabled = useMemo(() => {
    return stats?.image_search?.enabled || false;
  }, [stats]);

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
        {activeTab === 'search' && showImageSearchEnabled && (
          <SearchModeToggle activeMode={searchMode} onChange={handleSearchModeChange} />
        )}

        {/* Text search */}
        {activeTab === 'search' && (!showImageSearchEnabled || searchMode === 'text') && (
          <SearchBar onSearch={handleSearch} currentQuery={query} />
        )}

        {/* Image search */}
        {activeTab === 'search' && showImageSearchEnabled && searchMode === 'image' && (
          <ImageSearchUpload
            onSearchResults={handleImageSearchResults}
            onError={handleDismissError}
            onSearchStart={handleImageSearchStart}
          />
        )}

        {/* Show content based on active tab */}
        {activeTab === 'search' && (
          <ErrorBoundary fallbackLabel="Search">
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
              onResultsUpdate={handleResultsUpdate}
            />
          </ErrorBoundary>
        )}

        {activeTab === 'all-notes' && (
          <ErrorBoundary fallbackLabel="All Notes">
            <AllNotes onShowRelated={handleSearch} />
          </ErrorBoundary>
        )}

        {activeTab === 'clusters' && (
          <ErrorBoundary fallbackLabel="Clusters">
            <NotesClusters query={query} onShowRelated={handleSearch} />
          </ErrorBoundary>
        )}

        {activeTab === 'chat' && (
          <ErrorBoundary fallbackLabel="Chat">
            <Chat query={query} onShowRelated={handleSearch} />
          </ErrorBoundary>
        )}

        <ErrorDisplay error={error} onDismiss={handleDismissError} />
        <GalleryOverlay
          onSearchSimilarResults={handleImageSearchResults}
          onError={handleDismissError}
          onSwitchTab={handleTabSwitch}
        />
      </div>
    </GalleryProvider>
  );
};

export default App;
