import { memo, useState, useEffect, useCallback, useRef } from 'react';

import { NoteCard } from '@/components/NoteCard';
import { NoteSkeleton } from '@/components/NoteSkeleton';
import { RefinementSearchBar } from '@/components/RefinementSearchBar';
import { TagDialog } from '@/components/TagDialog';
import { TagManager } from '@/components/TagManager';
import { ViewToggle } from '@/components/ViewToggle';
import { Visualization } from '@/components/Visualization';
import { VIEW_MODES } from '@/const';
import { useTags } from '@/hooks/useTags';
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
  onResultsUpdate?: () => void;
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
    onResultsUpdate,
  }: ResultsProps) => {
    const [viewMode, setViewMode] = useState<ViewMode>(VIEW_MODES.LIST);
    const [showRefinement, setShowRefinement] = useState<boolean>(false);
    const [selectedNoteIds, setSelectedNoteIds] = useState<string[]>([]);
    const [isTagDialogOpen, setIsTagDialogOpen] = useState(false);
    const prevQueryRef = useRef<string>(query);

    const {
      tags,
      excludedTags,
      tagNotes,
      updateExcludedTags,
      removeTagFromAllNotes,
      removeTagFromNote,
    } = useTags(onResultsUpdate);

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
      // Clear selected notes when new search is performed
      setSelectedNoteIds([]);
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

    const handleNoteSelection = useCallback((noteId: string, isSelected: boolean) => {
      setSelectedNoteIds((prev) => {
        if (isSelected) {
          return [...prev, noteId];
        } else {
          return prev.filter((id) => id !== noteId);
        }
      });
    }, []);

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
          // Trigger results update if callback provided
          if (onResultsUpdate) {
            onResultsUpdate();
          }
        } catch (error) {
          console.error('Failed to tag notes:', error);
        }
      },
      [selectedNoteIds, tagNotes, onResultsUpdate],
    );

    const handleSelectAll = useCallback(() => {
      const allNoteIds = results.map((note) => note.id);
      setSelectedNoteIds(allNoteIds);
    }, [results]);

    const handleDeselectAll = useCallback(() => {
      setSelectedNoteIds([]);
    }, []);

    const handleExcludedTagsUpdate = useCallback(
      async (newExcludedTags: string[]) => {
        try {
          await updateExcludedTags(newExcludedTags);
          // Trigger results update if callback provided
          if (onResultsUpdate) {
            onResultsUpdate();
          }
        } catch (error) {
          console.error('Failed to update excluded tags:', error);
        }
      },
      [updateExcludedTags, onResultsUpdate],
    );

    const handleRemoveTagFromAll = useCallback(
      (tagName: string) => {
        removeTagFromAllNotes(tagName);
        // No need to call onResultsUpdate here as it's already passed to useTags
      },
      [removeTagFromAllNotes],
    );

    if (isLoading) {
      // choose skeleton style based on the current view mode so the
      // loading animation doesn't jump when the user toggles views
      const layout = viewMode === VIEW_MODES.LIST ? 'list' : 'grid';
      return (
        <div className="results-container">
          <NoteSkeleton count={6} layout={layout} />
        </div>
      );
    }

    return (
      <div className="results-container">
        {/* Tag Manager - shown when there are tags available */}
        {tags.length > 0 && (
          <TagManager
            tags={tags}
            excludedTags={excludedTags}
            onUpdateExcludedTags={handleExcludedTagsUpdate}
            onRemoveTagFromAll={handleRemoveTagFromAll}
          />
        )}

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
              {/* Selection Controls */}
              {results.length > 0 && (
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
                </div>
              )}

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
                <NoteCard
                  note={note}
                  query={query}
                  refinementKeywords={refinementKeywords}
                  isSelectable={true}
                  isSelected={selectedNoteIds.includes(note.id)}
                  onShowRelated={onShowRelated}
                  onSelectNote={handleNoteSelection}
                  onRemoveTag={removeTagFromNote}
                />
              </div>
            ))}
          </div>
        )}

        {viewMode === VIEW_MODES.VISUALIZATION && hasSearched && results.length > 0 && (
          <div id="results-visualization">
            <Visualization searchResults={results} onSelectNote={handleSelectNote} />
          </div>
        )}

        {/* Tag Dialog */}
        <TagDialog
          isOpen={isTagDialogOpen}
          selectedNoteIds={selectedNoteIds}
          existingTags={tags}
          onClose={handleCloseTagDialog}
          onConfirm={handleTagConfirm}
        />

        <ScrollToTop smooth={true} threshold={300} />
      </div>
    );
  },
);
