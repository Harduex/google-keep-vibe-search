import { useCallback, useMemo, useState } from 'react';

import { Chat } from '@/components/Chat';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ErrorDisplay } from '@/components/ErrorDisplay';
import { GalleryProvider, GalleryOverlay } from '@/components/ImageGallery';
import { ImageSearchUpload } from '@/components/ImageSearchUpload';
import { LoadingScreen } from '@/components/LoadingScreen';
import { Notes } from '@/components/Notes';
import { Organize } from '@/components/Organize';
import { SearchBar } from '@/components/SearchBar';
import { SearchModeToggle, type SearchMode } from '@/components/SearchModeToggle';
import { TabNavigation, TabId } from '@/components/TabNavigation';
import { UI_ELEMENTS } from '@/const';
import { formatStatsText, scrollToElement } from '@/helpers';
import { useBackendReady } from '@/hooks/useBackendReady';
import { useSearch } from '@/hooks/useSearch';
import { useStats } from '@/hooks/useStats';
import { useTheme } from '@/hooks/useTheme';
import { EMPTY_TAG_FILTER, focusTag } from '@/tagFilter';

import './App.css';
import { Note } from './types';

const App = () => {
  const { theme, toggleTheme } = useTheme();

  // wait for backend to finish its startup work before rendering the rest of the
  // application.  useBackendReady will poll `/api/ready` until the server reports
  // it has finished indexing, at which point we can safely fetch stats and other
  // resources.
  const { ready: backendReady } = useBackendReady();

  // fetch stats only after server is ready; the `enabled` flag prevents
  // useStats from firing too early and producing an error banner during the
  // initial warm‑up period.
  const { stats, error: statsError, refetchStats } = useStats(backendReady);
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
    clearSearch,
    error: searchError,
  } = useSearch();

  // Add state for active tab
  const [activeTab, setActiveTab] = useState<TabId>('notes');
  // Add state for search mode
  const [searchMode, setSearchMode] = useState<SearchMode>('text');
  // Which tags the notes list shows and hides. Owned here, not by Notes, so a tag chip in
  // the notes list or Explore in the Organize tab can point the notes list at one tag.
  // Purely a view filter — unrelated to the search-wide exclusion behind /api/tags/excluded.
  const [tagFilter, setTagFilter] = useState(EMPTY_TAG_FILTER);

  const handleSearch = useCallback(
    (searchQuery: string) => {
      performSearch(searchQuery);
      setActiveTab('notes'); // Switch to the notes tab when performing a search
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

  /** Show exactly the notes carrying `tagName`.
   *  Lifted to App because the include filter is owned by App and rendered by the
   *  Notes tab; the only external caller is Explore in the Organize tag manager
   *  (tag chips on cards filter in place inside Notes). */
  const handleExploreTag = useCallback((tagName: string) => {
    setTagFilter((prev) => focusTag(prev, tagName));
    setActiveTab('notes');
    scrollToElement('.tab-navigation', UI_ELEMENTS.SEARCH_OFFSET);
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

  if (!backendReady) {
    // backend isn't available yet; show a full screen spinner rather than the
    // normal chrome so that users don't interact with a half‑initialized
    // application.  If we have encountered a connection error we surface it
    // beneath the spinner so the user understands what is going on.
    return <LoadingScreen message="Indexing your notes…" />;
  }

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

        {/* Show search bar only in the notes tab */}
        {activeTab === 'notes' && showImageSearchEnabled && (
          <SearchModeToggle activeMode={searchMode} onChange={handleSearchModeChange} />
        )}

        {/* Text search */}
        {activeTab === 'notes' && (!showImageSearchEnabled || searchMode === 'text') && (
          <SearchBar onSearch={handleSearch} onClear={clearSearch} currentQuery={query} />
        )}

        {/* Image search */}
        {activeTab === 'notes' && showImageSearchEnabled && searchMode === 'image' && (
          <ImageSearchUpload
            onSearchResults={handleImageSearchResults}
            onError={handleDismissError}
            onSearchStart={handleImageSearchStart}
          />
        )}

        {/* Show content based on active tab */}
        {activeTab === 'notes' && (
          <ErrorBoundary fallbackLabel="Notes">
            <Notes
              query={query}
              results={results}
              originalResults={originalResults}
              refinementKeywords={refinementKeywords}
              isSearchLoading={isLoading}
              hasSearched={hasSearched}
              isRefined={isRefined}
              onRefine={handleRefinement}
              onResetRefinement={resetRefinement}
              onClearSearch={clearSearch}
              onResultsUpdate={handleResultsUpdate}
              onShowRelated={handleSearch}
              tagFilter={tagFilter}
              onTagFilterChange={setTagFilter}
            />
          </ErrorBoundary>
        )}

        {activeTab === 'chat' && (
          <ErrorBoundary fallbackLabel="Chat">
            <Chat query={query} onShowRelated={handleSearch} />
          </ErrorBoundary>
        )}

        {activeTab === 'organize' && (
          <ErrorBoundary fallbackLabel="Organize">
            <Organize onExploreTag={handleExploreTag} />
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
