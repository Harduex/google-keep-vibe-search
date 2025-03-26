import { memo, useState, useEffect, useCallback, useRef } from 'react';

import { Note, ViewMode } from '@/types/index';
import { VIEW_MODES } from '@/const';

import { NoteCard } from '@/components/NoteCard';
import { ViewToggle } from '@/components/ViewToggle';
import { Visualization } from '@/components/Visualization';
import { NotesClusters } from '@/components/NotesClusters';
import { ClustersButton } from '@/components/ClustersButton';

interface ResultsProps {
  query: string;
  results: Note[];
  isLoading: boolean;
  hasSearched: boolean;
  onShowRelated: (content: string) => void;
}

export const Results = memo(
  ({ query, results, isLoading, hasSearched, onShowRelated }: ResultsProps) => {
    const [viewMode, setViewMode] = useState<ViewMode>(VIEW_MODES.LIST);
    const [showClusters, setShowClusters] = useState<boolean>(false);
    const [showScrollToTop, setShowScrollToTop] = useState<boolean>(false);
    const prevQueryRef = useRef<string>(query);

    useEffect(() => {
      if (results.length === 0 || !hasSearched) {
        setViewMode(VIEW_MODES.LIST);
        setShowClusters(false);
      }
    }, [results.length, hasSearched]);

    // Toggle off clusters tab when query changes (a new search is performed)
    useEffect(() => {
      if (prevQueryRef.current !== query && hasSearched) {
        setShowClusters(false);
        prevQueryRef.current = query;
      }
    }, [query, hasSearched]);

    useEffect(() => {
      const handleScroll = () => {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const shouldShow = scrollTop > 300;

        if (shouldShow !== showScrollToTop) {
          setShowScrollToTop(shouldShow);
        }
      };

      window.addEventListener('scroll', handleScroll);
      // Initial check
      handleScroll();

      return () => window.removeEventListener('scroll', handleScroll);
    }, [showScrollToTop]);

    const handleViewChange = useCallback((newMode: ViewMode) => {
      setViewMode(newMode);
      setShowClusters(false);
    }, []);

    const handleScrollToTop = useCallback(() => {
      window.scrollTo({
        top: 0,
        behavior: 'smooth',
      });
    }, []);

    const handleSelectNote = useCallback(
      (noteId: string) => {
        // Find the note in results
        const selectedNote = results.find((note) => note.id === noteId);
        if (selectedNote) {
          // Scroll to the note in list view
          setViewMode(VIEW_MODES.LIST);
          setTimeout(() => {
            const element = document.getElementById(`note-${noteId}`);
            if (element) {
              element.scrollIntoView({ behavior: 'smooth', block: 'center' });
              element.classList.add('highlighted-note');
              setTimeout(() => {
                element.classList.remove('highlighted-note');
              }, 2000);
            }
          }, 100);
        }
      },
      [results]
    );

    const handleToggleClusters = useCallback(() => {
      setShowClusters(prev => !prev);
      if (!showClusters) {
        // Only reset view mode when turning clusters on
        setViewMode(VIEW_MODES.LIST);
      }
    }, [showClusters]);

    if (isLoading) {
      return (
        <div className="results-container">
          <div id="loading">Searching...</div>
        </div>
      );
    }

    return (
      <div className="results-container">
        <div className="results-header">
          {hasSearched && results.length === 0 ? (
            <div id="no-results">No matching notes found.</div>
          ) : (
            hasSearched && (
              <div id="results-count">
                Found {results.length} matching note{results.length === 1 ? '' : 's'}
              </div>
            )
          )}

          <div className="controls-container">
            <ClustersButton onClick={handleToggleClusters} isActive={showClusters} />
            {results.length > 0 && !showClusters && <ViewToggle currentView={viewMode} onChange={handleViewChange} />}
          </div>
        </div>

        {!showClusters && viewMode === VIEW_MODES.LIST && hasSearched && results.length > 0 && (
          <div id="results-list">
            {results.map((note) => (
              <div id={`note-${note.id}`} key={note.id}>
                <NoteCard note={note} query={query} onShowRelated={onShowRelated} />
              </div>
            ))}
          </div>
        )}

        {!showClusters && viewMode === VIEW_MODES.VISUALIZATION && hasSearched && results.length > 0 && (
          <div id="results-visualization">
            <Visualization searchResults={results} onSelectNote={handleSelectNote} />
          </div>
        )}

        {showClusters && (
          <div id="results-clusters">
            <NotesClusters query={query} onShowRelated={onShowRelated} />
          </div>
        )}

        {showScrollToTop && (
          <div className="scroll-to-top" role="button" aria-label="Scroll to top">
            <button onClick={handleScrollToTop} title="Scroll to top">
              <span className="material-icons">arrow_upward</span>
            </button>
          </div>
        )}
      </div>
    );
  }
);

Results.displayName = 'Results';
