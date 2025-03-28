import { memo, useState, useCallback, useMemo } from 'react';

import { NoteCard } from '@/components/NoteCard';
import { ViewToggle } from '@/components/ViewToggle';
import { Visualization } from '@/components/Visualization';
import { VIEW_MODES } from '@/const';
import { useAllNotes } from '@/hooks/useAllNotes';
import { ViewMode } from '@/types';
import './styles.css';

interface AllNotesProps {
  onShowRelated: (content: string) => void;
}

export const AllNotes = memo(({ onShowRelated }: AllNotesProps) => {
  const { notes, isLoading, error } = useAllNotes();
  const [viewMode, setViewMode] = useState<ViewMode>(VIEW_MODES.LIST);
  const [sortBy, setSortBy] = useState<'edited' | 'created'>('edited');
  const [filterArchived, setFilterArchived] = useState<boolean>(false);
  const [filterPinned, setFilterPinned] = useState<boolean>(false);

  // Sort and filter notes
  const filteredNotes = useMemo(() => {
    let filtered = [...notes];

    // Apply filters
    if (filterArchived) {
      filtered = filtered.filter((note) => note.archived);
    }

    if (filterPinned) {
      filtered = filtered.filter((note) => note.pinned);
    }

    // Apply sorting
    filtered.sort((a, b) => {
      const dateA = new Date(sortBy === 'edited' ? a.edited : a.created);
      const dateB = new Date(sortBy === 'edited' ? b.edited : b.created);
      return dateB.getTime() - dateA.getTime(); // Newest first
    });

    return filtered;
  }, [notes, sortBy, filterArchived, filterPinned]);

  const handleSelectNote = useCallback((noteId: string) => {
    const element = document.getElementById(`note-${noteId}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      element.classList.add('highlighted-note');
      setTimeout(() => {
        element.classList.remove('highlighted-note');
      }, 2000);
    }
  }, []);

  const handleViewChange = useCallback((newMode: ViewMode) => {
    setViewMode(newMode);
  }, []);

  // New callback functions for form controls
  const handleSortChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setSortBy(e.target.value as 'edited' | 'created');
  }, []);

  const handlePinnedFilterChange = useCallback(() => {
    setFilterPinned((prev) => !prev);
  }, []);

  const handleArchivedFilterChange = useCallback(() => {
    setFilterArchived((prev) => !prev);
  }, []);

  if (isLoading) {
    return <div className="all-notes-loading">Loading notes...</div>;
  }

  if (error) {
    return <div className="all-notes-error">Error: {error}</div>;
  }

  return (
    <div className="all-notes-container">
      <div className="all-notes-header">
        <div className="all-notes-count">
          {filteredNotes.length} note{filteredNotes.length === 1 ? '' : 's'}
        </div>

        <div className="all-notes-controls">
          <div className="all-notes-filters">
            <select value={sortBy} onChange={handleSortChange} className="all-notes-select">
              <option value="edited">Sort by Last Edited</option>
              <option value="created">Sort by Created Date</option>
            </select>

            <label className="filter-checkbox">
              <input type="checkbox" checked={filterPinned} onChange={handlePinnedFilterChange} />
              Pinned Only
            </label>

            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={filterArchived}
                onChange={handleArchivedFilterChange}
              />
              Archived Only
            </label>
          </div>

          <ViewToggle currentView={viewMode} onChange={handleViewChange} />
        </div>
      </div>

      {viewMode === VIEW_MODES.LIST ? (
        <div className="all-notes-list">
          {filteredNotes.length === 0 ? (
            <div className="all-notes-empty">No notes to display with current filters</div>
          ) : (
            filteredNotes.map((note) => (
              <div id={`note-${note.id}`} key={note.id}>
                <NoteCard note={note} query="" onShowRelated={onShowRelated} />
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="all-notes-visualization">
          <Visualization searchResults={filteredNotes} onSelectNote={handleSelectNote} />
        </div>
      )}
    </div>
  );
});
