import { memo, useState, useEffect, useCallback, useRef } from 'react';

import { Note, ViewMode } from '@/types/index';
import { VIEW_MODES } from '@/const';

import { NoteCard } from '@/components/NoteCard';
import { ViewToggle } from '@/components/ViewToggle';
import { Visualization } from '@/components/Visualization';

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
    const [showScrollToTop, setShowScrollToTop] = useState<boolean>(false);
    const prevQueryRef = useRef<string>(query);

    useEffect(() => {
      if (results.length === 0 || !hasSearched) {
        setViewMode(VIEW_MODES.LIST);
      }
    }, [results.length, hasSearched]);

    // Update query reference when it changes
    useEffect(() => {
      prevQueryRef.current = query;
    }, [query]);

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

          {results.length > 0 && (
            <div className="controls-container">
              <ViewToggle currentView={viewMode} onChange={handleViewChange} />
            </div>
          )}
        </div>

        {viewMode === VIEW_MODES.LIST && hasSearched && results.length > 0 && (
          <div id="results-list">
            {results.map((note) => (
              <div id={`note-${note.id}`} key={note.id}>
                <NoteCard note={note} query={query} onShowRelated={onShowRelated} />
              </div>
            ))}
          </div>
        )}

        {viewMode === VIEW_MODES.VISUALIZATION && hasSearched && results.length > 0 && (
          <div id="results-visualization">
            <Visualization searchResults={results} onSelectNote={handleSelectNote} />
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
