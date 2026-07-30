import {
  Dispatch,
  SetStateAction,
  memo,
  useState,
  useCallback,
  useMemo,
  useEffect,
  useRef,
} from 'react';

import { NoteCard } from '@/components/NoteCard';
import { NoteSkeleton } from '@/components/NoteSkeleton';
import { RefinementSearchBar } from '@/components/RefinementSearchBar';
import { ScrollToTop } from '@/components/ScrollToTop';
import { TagDialog } from '@/components/TagDialog';
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
import { Note, ViewMode } from '@/types';
import './styles.css';

export type NotesSortBy = 'relevance' | 'edited' | 'created';
type DateSort = 'edited' | 'created';

const PAGE_SIZE = 20;

interface NotesProps {
  /** Active query text; empty for image search results. */
  query: string;
  /** Ranked (and possibly refined) search results. */
  results: Note[];
  originalResults: Note[];
  refinementKeywords: string;
  isSearchLoading: boolean;
  /** True while any search (text or image) is active — the mode switch. */
  hasSearched: boolean;
  isRefined: boolean;
  onRefine: (keywords: string) => void;
  onResetRefinement: () => void;
  onClearSearch: () => void;
  /** Re-run the active search after a mutation changes note-tag membership. */
  onResultsUpdate: () => void;
  onShowRelated: (content: string) => void;
  /** Which tags the list shows and hides. Owned by App: Organize's Explore points this
   *  list at a single tag, so it cannot live here. Every transition goes through the
   *  calculations in `@/tagFilter`. */
  tagFilter: TagFilterState;
  onTagFilterChange: Dispatch<SetStateAction<TagFilterState>>;
}

export const Notes = memo(
  ({
    query,
    results,
    originalResults,
    refinementKeywords,
    isSearchLoading,
    hasSearched,
    isRefined,
    onRefine,
    onResetRefinement,
    onClearSearch,
    onResultsUpdate,
    onShowRelated,
    tagFilter,
    onTagFilterChange,
  }: NotesProps) => {
    const { notes: allNotes, isLoading: isNotesLoading, error, refetch } = useAllNotes();
    const { tags, tagNotes, removeTagFromNote, renameTag } = useTags(
      hasSearched ? onResultsUpdate : refetch,
    );

    const [viewMode, setViewMode] = useState<ViewMode>(VIEW_MODES.LIST);
    const [sortBy, setSortBy] = useState<NotesSortBy>('edited');
    const [filterArchived, setFilterArchived] = useState<boolean>(false);
    const [filterPinned, setFilterPinned] = useState<boolean>(false);
    const [visibleNotesCount, setVisibleNotesCount] = useState<number>(PAGE_SIZE);
    const [selectedNoteIds, setSelectedNoteIds] = useState<string[]>([]);
    const [focusNoteId, setFocusNoteId] = useState<string | null>(null);
    const [showRefinement, setShowRefinement] = useState<boolean>(false);
    const [isTagDialogOpen, setIsTagDialogOpen] = useState(false);
    // Where sorting returns when a search ends: Relevance stops existing without a query.
    const lastDateSortRef = useRef<DateSort>('edited');

    const searchActive = hasSearched;
    const sourceNotes = searchActive ? results : allNotes;
    const isLoading = searchActive ? isSearchLoading : isNotesLoading;

    // Entering search mode defaults the order to relevance; leaving it restores the
    // last explicitly chosen date sort.
    useEffect(() => {
      setSortBy(searchActive ? 'relevance' : lastDateSortRef.current);
      setSelectedNoteIds([]);
      setShowRefinement(false);
      setVisibleNotesCount(PAGE_SIZE);
    }, [searchActive]);

    // A new query is a new result set: paging and selection restart.
    useEffect(() => {
      setSelectedNoteIds([]);
      setVisibleNotesCount(PAGE_SIZE);
      setShowRefinement(false);
    }, [query]);

    const filteredNotes = useMemo(() => {
      let filtered = applyTagFilter(sourceNotes, tagFilter);

      if (filterArchived) {
        filtered = filtered.filter((note) => note.archived);
      }
      if (filterPinned) {
        filtered = filtered.filter((note) => note.pinned);
      }

      if (sortBy === 'relevance') {
        // Relevance is the arrival order of the results; filtering preserves it.
        return filtered;
      }

      return [...filtered].sort((a, b) => {
        const dateA = new Date(sortBy === 'edited' ? a.edited : a.created);
        const dateB = new Date(sortBy === 'edited' ? b.edited : b.created);
        return dateB.getTime() - dateA.getTime(); // Newest first
      });
    }, [sourceNotes, sortBy, filterArchived, filterPinned, tagFilter]);

    const visibleNotes = useMemo(
      () => filteredNotes.slice(0, visibleNotesCount),
      [filteredNotes, visibleNotesCount],
    );

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
      const value = e.target.value as NotesSortBy;
      if (value !== 'relevance') {
        lastDateSortRef.current = value;
      }
      setSortBy(value);
    }, []);

    const handlePinnedFilterChange = useCallback(() => {
      setFilterPinned((prev) => !prev);
    }, []);

    const handleArchivedFilterChange = useCallback(() => {
      setFilterArchived((prev) => !prev);
    }, []);

    const handleLoadMore = useCallback(() => {
      setVisibleNotesCount((prev) => prev + PAGE_SIZE);
    }, []);

    const handleTagsChange = useCallback(
      (newSelectedTags: string[]) => {
        onTagFilterChange((prev) => setIncluded(prev, newSelectedTags));
      },
      [onTagFilterChange],
    );

    /** A tag chip on a card filters in place — in both modes. Both directions reset
     *  paging: the first page of a different result set is what the user asked to see. */
    const handleIncludeTagInList = useCallback(
      (tagName: string) => {
        onTagFilterChange((prev) => toggleIncluded(prev, tagName));
        setVisibleNotesCount(PAGE_SIZE);
      },
      [onTagFilterChange],
    );

    const handleExcludeTagInList = useCallback(
      (tagName: string) => {
        onTagFilterChange((prev) => toggleExcluded(prev, tagName));
        setVisibleNotesCount(PAGE_SIZE);
      },
      [onTagFilterChange],
    );

    const handleClearFilter = useCallback(() => {
      onTagFilterChange(clearTagFilter());
      setVisibleNotesCount(PAGE_SIZE);
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

    /** Export a tag's notes from the full corpus, regardless of the current mode. */
    const handleExportByTag = useCallback(
      (tagName: string) => {
        const tagNotesList = allNotes.filter((note) => note.tags?.includes(tagName));
        exportNotes(tagNotesList, `notes-export-${tagName}.txt`);
      },
      [allNotes],
    );

    const handleOpenTagDialog = useCallback(() => {
      if (selectedNoteIds.length > 0) {
        setIsTagDialogOpen(true);
      }
    }, [selectedNoteIds]);

    const handleCloseTagDialog = useCallback(() => {
      setIsTagDialogOpen(false);
    }, []);

    const handleTagConfirm = useCallback(
      async (tagName: string) => {
        try {
          await tagNotes(selectedNoteIds, tagName);
          setIsTagDialogOpen(false);
          setSelectedNoteIds([]);
          if (hasSearched) {
            onResultsUpdate();
          }
        } catch (err) {
          console.error('Failed to tag notes:', err);
        }
      },
      [selectedNoteIds, tagNotes, hasSearched, onResultsUpdate],
    );

    const toggleRefinement = useCallback(() => {
      setShowRefinement((prev) => !prev);
      // Toggling refinement off also resets any applied refinement.
      if (showRefinement && refinementKeywords) {
        onResetRefinement();
      }
    }, [showRefinement, refinementKeywords, onResetRefinement]);

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
      // choose skeleton style from the current view mode so the loading
      // animation doesn't jump when the user re-searches from the 3D view
      const layout = viewMode === VIEW_MODES.LIST ? 'list' : 'grid';
      return (
        <div className="all-notes-container">
          <NoteSkeleton count={12} layout={layout} />
        </div>
      );
    }

    if (!searchActive && error) {
      return <div className="all-notes-error">Error: {error}</div>;
    }

    return (
      <div className="all-notes-container">
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

        {showRefinement && searchActive && originalResults.length > 0 && (
          <RefinementSearchBar onRefine={onRefine} isVisible={true} />
        )}

        <div className="all-notes-header">
          <div className="all-notes-count">
            {searchActive && filteredNotes.length === 0 ? (
              <span id="no-results">No matching notes found.</span>
            ) : (
              <>
                {searchActive ? 'Found ' : ''}
                {filteredNotes.length} note{filteredNotes.length === 1 ? '' : 's'}
                {isFiltering(tagFilter) && (
                  <span className="tag-filter-status"> ({describeTagFilter(tagFilter)})</span>
                )}
                {isRefined && (
                  <span className="refined-filter-info"> (filtered by: {refinementKeywords})</span>
                )}
              </>
            )}
            {searchActive && (
              <button
                className="clear-search-button"
                onClick={onClearSearch}
                title="Clear the search and browse all notes"
                aria-label="Clear search"
              >
                <span className="material-icons">close</span>
                <span>Clear search</span>
              </button>
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
                    onClick={handleOpenTagDialog}
                    title={`Tag ${selectedNoteIds.length} selected notes`}
                  >
                    <span className="material-icons">label</span>
                    <span>Tag ({selectedNoteIds.length})</span>
                  </button>
                )}

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

            {searchActive && originalResults.length > 0 && (
              <button
                className={`refinement-toggle-button ${showRefinement ? 'active' : ''}`}
                onClick={toggleRefinement}
                title={showRefinement ? 'Hide refinement search' : 'Refine search results'}
              >
                <span className="material-icons">filter_list</span>
                <span>Refine</span>
              </button>
            )}

            {viewMode === VIEW_MODES.LIST && (
              <div className="all-notes-filters">
                <select value={sortBy} onChange={handleSortChange} className="all-notes-select">
                  {searchActive && <option value="relevance">Sort by Relevance</option>}
                  <option value="edited">Sort by Last Edited</option>
                  <option value="created">Sort by Created Date</option>
                </select>

                <label className="filter-checkbox">
                  <input
                    type="checkbox"
                    checked={filterPinned}
                    onChange={handlePinnedFilterChange}
                  />
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
            {visibleNotes.length === 0
              ? !searchActive && (
                  <div className="all-notes-empty">No notes to display with current filters</div>
                )
              : visibleNotes.map((note) => (
                  <div id={`note-${note.id}`} key={note.id}>
                    <NoteCard
                      note={note}
                      query={searchActive ? query : ''}
                      refinementKeywords={searchActive ? refinementKeywords : undefined}
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
                ))}
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
              onShowRelated={onShowRelated}
              isAllNotesView={!searchActive}
              focusNoteId={focusNoteId}
            />
          </div>
        )}

        <TagDialog
          isOpen={isTagDialogOpen}
          selectedNoteIds={selectedNoteIds}
          existingTags={tags}
          onClose={handleCloseTagDialog}
          onConfirm={handleTagConfirm}
        />

        <ScrollToTop threshold={200} />
      </div>
    );
  },
);
