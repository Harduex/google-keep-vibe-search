import { memo } from 'react';

import { Note } from '@/types/index';

import { NoteCard } from '@/components/NoteCard';

interface ResultsProps {
  query: string;
  results: Note[];
  isLoading: boolean;
  hasSearched: boolean;
  onShowRelated: (content: string) => void;
}

export const Results = memo(
  ({ query, results, isLoading, hasSearched, onShowRelated }: ResultsProps) => {
    if (isLoading) {
      return (
        <div className="results-container">
          <div id="loading">Searching...</div>
        </div>
      );
    }

    if (hasSearched && results.length === 0) {
      return (
        <div className="results-container">
          <div id="no-results">No matching notes found.</div>
        </div>
      );
    }

    return (
      <div className="results-container">
        {results.length > 0 && (
          <div id="results-count">
            Found {results.length} matching note{results.length === 1 ? '' : 's'}
          </div>
        )}
        <div id="results-list">
          {results.map((note) => (
            <NoteCard key={note.id} note={note} query={query} onShowRelated={onShowRelated} />
          ))}
        </div>
      </div>
    );
  }
);

Results.displayName = 'Results';
