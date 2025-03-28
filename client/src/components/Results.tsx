import { memo, useState, useEffect, useCallback, useRef } from 'react';

import { NoteCard } from '@/components/NoteCard';
import { ViewToggle } from '@/components/ViewToggle';
import { Visualization } from '@/components/Visualization';
import { VIEW_MODES } from '@/const';
import { Note, ViewMode } from '@/types/index';

import { ScrollToTop } from './ScrollToTop';

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

        <ScrollToTop smooth={true} threshold={300} />
      </div>
    );
  },
);
