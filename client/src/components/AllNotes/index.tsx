import { Dispatch, SetStateAction, memo, useState, useCallback, useMemo, useEffect } from 'react';

import { NoteCard } from '@/components/NoteCard';
import { NoteSkeleton } from '@/components/NoteSkeleton';
import { ScrollToTop } from '@/components/ScrollToTop';
import { TagFilter } from '@/components/TagFilter';
import { ViewToggle } from '@/components/ViewToggle';
import { Visualization } from '@/components/Visualization';
import { VIEW_MODES } from '@/const';
import { exportNotes, todayDateStr } from '@/exportUtils';
import { useAllNotes } from '@/hooks/useAllNotes';
import { useTags } from '@/hooks/useTags';
import {
  TagFilterState,
  applyTagFilter,
  clearTagFilter,
  describeTagFilter,
  isFiltering,
  renameTagInFilter,
  setIncluded,
  toggleExcluded,
  toggleIncluded,
} from '@/tagFilter';
import { ViewMode } from '@/types';
import './styles.css';

interface AllNotesProps {
  onShowRelated: (content: string) => void;
  /** Which tags the list shows and hides. Owned by App: a tag chip in the search results or
   *  Explore in the Organize tab points this list at a single tag, so it cannot live here.
   *  Every transition goes through the calculations in `@/tagFilter`, which is what keeps
   *  the shown and hidden sets from ever holding the same tag. */
  tagFilter: TagFilterState;
  onTagFilterChange: Dispatch<SetStateAction<TagFilterState>>;
}

export const AllNotes = memo(({ onShowRelated, tagFilter, onTagFilterChange }: AllNotesProps) => {
  const { notes, isLoading, error, refetch } = useAllNotes();
  const { tags, removeTagFromNote, renameTag } = useTags(refetch);
  const [viewMode, setViewMode] = useState<ViewMode>(VIEW_MODES.LIST);
  const [sortBy, setSortBy] = useState<'edited' | 'created'>('edited');
  const [filterArchived, setFilterArchived] = useState<boolean>(false);
  const [filterPinned, setFilterPinned] = useState<boolean>(false);
  const [visibleNotesCount, setVisibleNotesCount] = useState<number>(20);
  const [selectedNoteIds, setSelectedNoteIds] = useState<string[]>([]);
  const [focusNoteId, setFocusNoteId] = useState<string | null>(null);

  // Sort and filter notes
  const filteredNotes = useMemo(() => {
    let filtered = [...applyTagFilter(notes, tagFilter)];

    // Apply other filters
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
  }, [notes, sortBy, filterArchived, filterPinned, tagFilter]);

  const visibleNotes = useMemo(
    () => filteredNotes.slice(0, visibleNotesCount),
    [filteredNotes, visibleNotesCount],
  );

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
    if (newMode === VIEW_MODES.LIST) {
      // Cleared on the way out so picking the same note again is a fresh change
      // the 3D view can react to, rather than an unchanged prop it ignores.
      setFocusNoteId(null);
    }
  }, []);

  /** "Show connections" on a card: jump to the 3D view centred on that note. */
  const handleShowConnections = useCallback((noteId: string) => {
    setFocusNoteId(noteId);
    setViewMode(VIEW_MODES.VISUALIZATION);
  }, []);

  const handleSortChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setSortBy(e.target.value as 'edited' | 'created');
  }, []);

  const handlePinnedFilterChange = useCallback(() => {
    setFilterPinned((prev) => !prev);
  }, []);

  const handleArchivedFilterChange = useCallback(() => {
    setFilterArchived((prev) => !prev);
  }, []);

  const handleLoadMore = useCallback(() => {
    setVisibleNotesCount((prev) => prev + 20);
  }, []);

  const handleTagsChange = useCallback(
    (newSelectedTags: string[]) => {
      onTagFilterChange((prev) => setIncluded(prev, newSelectedTags));
    },
    [onTagFilterChange],
  );

  /** A tag chip on a note filters in place — the list is already on screen, so there is
   *  nothing to navigate to. Both directions reset paging: the first page of a different
   *  result set is what the user asked to see. */
  const handleIncludeTagInList = useCallback(
    (tagName: string) => {
      onTagFilterChange((prev) => toggleIncluded(prev, tagName));
      setVisibleNotesCount(20);
    },
    [onTagFilterChange],
  );

  const handleExcludeTagInList = useCallback(
    (tagName: string) => {
      onTagFilterChange((prev) => toggleExcluded(prev, tagName));
      setVisibleNotesCount(20);
    },
    [onTagFilterChange],
  );

  const handleClearFilter = useCallback(() => {
    onTagFilterChange(clearTagFilter());
    setVisibleNotesCount(20);
  }, [onTagFilterChange]);

  const handleRenameTag = useCallback(
    async (oldName: string, newName: string) => {
      await renameTag(oldName, newName);
      // Keep the filter pointing at the tag the user renamed, not at a name that no
      // longer exists.
      onTagFilterChange((prev) => renameTagInFilter(prev, oldName, newName));
    },
    [renameTag, onTagFilterChange],
  );

  const handleMergeSelectedTags = useCallback(
    async (targetTag: string) => {
      const sourceTags = tagFilter.included.filter((tag) => tag !== targetTag);

      for (const sourceTag of sourceTags) {
        await renameTag(sourceTag, targetTag);
      }

      onTagFilterChange((prev) => setIncluded(prev, [targetTag]));
    },
    [renameTag, tagFilter, onTagFilterChange],
  );

  const handleNoteSelection = useCallback((noteId: string, isSelected: boolean) => {
    setSelectedNoteIds((prev) =>
      isSelected ? [...prev, noteId] : prev.filter((id) => id !== noteId),
    );
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedNoteIds(filteredNotes.map((note) => note.id));
  }, [filteredNotes]);

  const handleDeselectAll = useCallback(() => {
    setSelectedNoteIds([]);
  }, []);

  const handleExportSelected = useCallback(() => {
    const selected = filteredNotes.filter((note) => selectedNoteIds.includes(note.id));
    exportNotes(selected, `notes-export-${todayDateStr()}.txt`);
  }, [filteredNotes, selectedNoteIds]);

  const handleExportByTag = useCallback(
    (tagName: string) => {
      const tagNotesList = notes.filter((note) => note.tags?.includes(tagName));
      exportNotes(tagNotesList, `notes-export-${tagName}.txt`);
    },
    [notes],
  );

  useEffect(() => {
    const handleScroll = () => {
      if (
        window.innerHeight + document.documentElement.scrollTop >=
        document.documentElement.offsetHeight - 100
      ) {
        handleLoadMore();
      }
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, [handleLoadMore]);

  if (isLoading) {
    return (
      <div className="all-notes-container">
        {/* layout=list ensures the skeleton matches the vertical list that will
            be rendered once data arrives */}
        <NoteSkeleton count={12} layout="list" />
      </div>
    );
  }

  if (error) {
    return <div className="all-notes-error">Error: {error}</div>;
  }

  return (
    <div className="all-notes-container">
      {/* Tag Filter */}
      {tags.length > 0 && (
        <TagFilter
          tags={tags}
          filter={tagFilter}
          onUpdateSelectedTags={handleTagsChange}
          onToggleExcluded={handleExcludeTagInList}
          onClearFilter={handleClearFilter}
          onRenameTag={handleRenameTag}
          onMergeTags={handleMergeSelectedTags}
          onExportTag={handleExportByTag}
        />
      )}

      <div className="all-notes-header">
        <div className="all-notes-count">
          {filteredNotes.length} note{filteredNotes.length === 1 ? '' : 's'}
          {isFiltering(tagFilter) && (
            <span className="tag-filter-status"> ({describeTagFilter(tagFilter)})</span>
          )}
        </div>

        <div className="all-notes-controls">
          {viewMode === VIEW_MODES.LIST && filteredNotes.length > 0 && (
            <div className="selection-controls">
              <button
                className="selection-toggle-button"
                onClick={selectedNoteIds.length === 0 ? handleSelectAll : handleDeselectAll}
                title={selectedNoteIds.length === 0 ? 'Select all notes' : 'Deselect all notes'}
              >
                <span className="material-icons">
                  {selectedNoteIds.length === 0 ? 'check_box_outline_blank' : 'check_box'}
                </span>
                <span>{selectedNoteIds.length === 0 ? 'Select All' : 'Deselect All'}</span>
              </button>

              {selectedNoteIds.length > 0 && (
                <button
                  className="tag-button"
                  onClick={handleExportSelected}
                  title={`Export ${selectedNoteIds.length} selected notes`}
                >
                  <span className="material-icons">download</span>
                  <span>Export ({selectedNoteIds.length})</span>
                </button>
              )}
            </div>
          )}

          {viewMode === VIEW_MODES.LIST && (
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
          )}

          <ViewToggle currentView={viewMode} onChange={handleViewChange} />
        </div>
      </div>

      {viewMode === VIEW_MODES.LIST ? (
        <div className="all-notes-list">
          {visibleNotes.length === 0 ? (
            <div className="all-notes-empty">No notes to display with current filters</div>
          ) : (
            visibleNotes.map((note) => (
              <div id={`note-${note.id}`} key={note.id}>
                <NoteCard
                  note={note}
                  query=""
                  isSelectable={true}
                  isSelected={selectedNoteIds.includes(note.id)}
                  onShowRelated={onShowRelated}
                  onShowConnections={handleShowConnections}
                  onSelectNote={handleNoteSelection}
                  onRemoveTag={removeTagFromNote}
                  onRenameTag={renameTag}
                  onTagClick={handleIncludeTagInList}
                  onTagExclude={handleExcludeTagInList}
                  tagFilter={tagFilter}
                />
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="all-notes-visualization">
          {/* filteredNotes, not visibleNotes: `visibleNotes` is the card list's
              infinite-scroll window (20 at a time, grown by a scroll listener that
              never fires here because the list is not rendered in this mode). The
              3D view filters by what it is given, so handing it the paged slice
              showed a 20-point cloud. Tag/pinned/archived filters still apply —
              they are baked into filteredNotes. */}
          <Visualization
            searchResults={filteredNotes}
            onSelectNote={handleSelectNote}
            isAllNotesView={true}
            focusNoteId={focusNoteId}
          />
        </div>
      )}

      <ScrollToTop threshold={200} />
    </div>
  );
});
