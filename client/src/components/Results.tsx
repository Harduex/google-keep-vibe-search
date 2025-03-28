import { memo, useState, useEffect, useCallback, useRef } from 'react';

import { NoteCard } from '@/components/NoteCard';
import { RefinementSearchBar } from '@/components/RefinementSearchBar';
import { ViewToggle } from '@/components/ViewToggle';
import { Visualization } from '@/components/Visualization';
import { VIEW_MODES } from '@/const';
import { Note, ViewMode } from '@/types/index';

import { ScrollToTop } from './ScrollToTop';

interface ResultsProps {
  query: string;
  results: Note[];
  originalResults: Note[];
  refinementKeywords: string;
  isLoading: boolean;
  hasSearched: boolean;
  isRefined: boolean;
  onShowRelated: (content: string) => void;
  onRefine: (keywords: string) => void;
  onResetRefinement: () => void;
}

export const Results = memo(
  ({
    query,
    results,
    originalResults,
    refinementKeywords,
    isLoading,
    hasSearched,
    isRefined,
    onShowRelated,
    onRefine,
    onResetRefinement,
  }: ResultsProps) => {
    const [viewMode, setViewMode] = useState<ViewMode>(VIEW_MODES.LIST);
    const prevQueryRef = useRef<string>(query);
    const [showRefinement, setShowRefinement] = useState<boolean>(false);

    useEffect(() => {
      if (results.length === 0 || !hasSearched) {
        setViewMode(VIEW_MODES.LIST);
      }
    }, [results.length, hasSearched]);

    // Update query reference when it changes
    useEffect(() => {
      prevQueryRef.current = query;
      // Hide refinement search when new search is performed
      setShowRefinement(false);
    }, [query]);

    const handleViewChange = useCallback((newMode: ViewMode) => {
      setViewMode(newMode);
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
      [results],
    );

    const handleRefineSubmit = useCallback(
      (keywords: string) => {
        onRefine(keywords);
      },
      [onRefine],
    );

    const toggleRefinement = useCallback(() => {
      setShowRefinement((prev) => !prev);

      // When toggling refinement off, reset any existing refinement
      if (showRefinement && refinementKeywords) {
        onResetRefinement();
      }
    }, [showRefinement, refinementKeywords, onResetRefinement]);

    if (isLoading) {
      return (
        <div className="results-container">
          <div id="loading">Searching...</div>
        </div>
      );
    }

    return (
      <div className="results-container">
        {/* Show refinement search bar when toggled and we have search results */}
        {showRefinement && hasSearched && originalResults.length > 0 && (
          <RefinementSearchBar onRefine={handleRefineSubmit} isVisible={true} />
        )}

        <div className="results-header">
          {hasSearched && results.length === 0 ? (
            <div id="no-results">No matching notes found.</div>
          ) : (
            hasSearched && (
              <div id="results-count">
                Found {results.length} matching note{results.length === 1 ? '' : 's'}
                {isRefined && (
                  <span className="refined-filter-info">(filtered by: {refinementKeywords})</span>
                )}
              </div>
            )
          )}

          {hasSearched && originalResults.length > 0 && (
            <div className="controls-container">
              {/* Refinement Toggle Button */}
              <button
                className={`refinement-toggle-button ${showRefinement ? 'active' : ''}`}
                onClick={toggleRefinement}
                title={showRefinement ? 'Hide refinement search' : 'Refine search results'}
              >
                <span className="material-icons">filter_list</span>
                <span>Refine</span>
              </button>

              {/* View Mode Toggle (only show when we have results) */}
              {results.length > 0 && (
                <ViewToggle currentView={viewMode} onChange={handleViewChange} />
              )}
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

        <ScrollToTop smooth={true} threshold={300} />
      </div>
    );
  },
);
