import { memo, useState, useCallback } from 'react';

import { API_ROUTES } from '@/const';
import { NoteSample, Tag } from '@/types';

interface TagManagementCardProps {
  tag: Tag;
  allTags: Tag[];
  onRename: (oldName: string, newName: string) => void;
  onMerge: (sourceTag: string, targetTag: string) => void;
  onRemove: (tagName: string) => void;
  /** Show every note carrying this tag in the notes list. */
  onExplore: (tagName: string) => void;
}

export const TagManagementCard = memo(
  ({ tag, allTags, onRename, onMerge, onRemove, onExplore }: TagManagementCardProps) => {
    const [isRenaming, setIsRenaming] = useState(false);
    const [renameValue, setRenameValue] = useState(tag.name);
    const [isMerging, setIsMerging] = useState(false);
    const [isExpanded, setIsExpanded] = useState(false);
    // A saved tag carries no sample notes (unlike a proposal, which ships its own), so the
    // preview fetches them on first open and keeps them for subsequent toggles.
    const [samples, setSamples] = useState<NoteSample[] | null>(null);
    const [previewError, setPreviewError] = useState<string | null>(null);

    const togglePreview = useCallback(async () => {
      const opening = !isExpanded;
      setIsExpanded(opening);
      if (!opening || samples !== null) {
        return;
      }
      setPreviewError(null);
      try {
        const params = new URLSearchParams({ tag: tag.name, limit: '5' });
        const response = await fetch(`${API_ROUTES.TAG_SAMPLE_NOTES}?${params}`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        setSamples(data.notes ?? []);
      } catch (err) {
        setPreviewError(`Could not load notes: ${(err as Error).message}`);
      }
    }, [isExpanded, samples, tag.name]);

    const handleRenameSubmit = useCallback(() => {
      const trimmed = renameValue.trim();
      if (trimmed && trimmed !== tag.name) {
        onRename(tag.name, trimmed);
      }
      setIsRenaming(false);
    }, [renameValue, tag.name, onRename]);

    const handleMergeSelect = useCallback(
      (targetName: string) => {
        if (
          window.confirm(
            `Merge "${tag.name}" into "${targetName}"? All notes with "${tag.name}" will be tagged as "${targetName}" instead.`,
          )
        ) {
          onMerge(tag.name, targetName);
        }
        setIsMerging(false);
      },
      [tag.name, onMerge],
    );

    const handleRemove = useCallback(() => {
      if (window.confirm(`Remove tag "${tag.name}" from all notes? This cannot be undone.`)) {
        onRemove(tag.name);
      }
    }, [tag.name, onRemove]);

    return (
      <div className="proposal-card">
        <div className="proposal-header">
          <div className="proposal-tag-info">
            {isRenaming ? (
              <div className="rename-input-group">
                <input
                  type="text"
                  className="rename-input"
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      handleRenameSubmit();
                    }
                    if (e.key === 'Escape') {
                      setIsRenaming(false);
                    }
                  }}
                  autoFocus
                />
                <button className="rename-confirm" onClick={handleRenameSubmit}>
                  <span className="material-icons">check</span>
                </button>
                <button className="rename-cancel" onClick={() => setIsRenaming(false)}>
                  <span className="material-icons">close</span>
                </button>
              </div>
            ) : (
              <div className="proposal-tag-name">
                <span className="material-icons">label</span>
                <span className="tag-name-text">{tag.name}</span>
              </div>
            )}
          </div>

          <div className="proposal-meta">
            <span className="proposal-count">
              <span className="material-icons">description</span>
              {tag.count}
            </span>
          </div>
        </div>

        <div className="proposal-actions">
          <button
            className="proposal-action-btn explore"
            onClick={() => onExplore(tag.name)}
            title="Explore tag: show these notes in the notes list"
          >
            <span className="material-icons">travel_explore</span>
          </button>
          <button
            className="proposal-action-btn rename"
            onClick={() => {
              setRenameValue(tag.name);
              setIsRenaming(true);
              setIsMerging(false);
            }}
            title="Rename tag"
          >
            <span className="material-icons">edit</span>
          </button>
          <button
            className={`proposal-action-btn merge ${isMerging ? 'active' : ''}`}
            onClick={() => {
              setIsMerging(!isMerging);
              setIsRenaming(false);
            }}
            title="Merge into another tag"
          >
            <span className="material-icons">merge_type</span>
          </button>
          <button
            className="proposal-action-btn remove"
            onClick={handleRemove}
            title="Remove tag from all notes"
          >
            <span className="material-icons">delete</span>
          </button>
        </div>

        {isMerging && (
          <div className="merge-selector">
            <span className="merge-label">Merge into:</span>
            {allTags
              .filter((t) => t.name !== tag.name)
              .map((t) => (
                <button
                  key={t.name}
                  className="merge-target-btn"
                  onClick={() => handleMergeSelect(t.name)}
                >
                  {t.name}
                </button>
              ))}
          </div>
        )}

        <button className="proposal-preview-toggle" onClick={togglePreview}>
          <span className="material-icons">{isExpanded ? 'expand_less' : 'expand_more'}</span>
          {isExpanded ? 'Hide' : 'Preview'} notes
        </button>

        {isExpanded && (
          <div className="proposal-preview-notes">
            {previewError && <div className="preview-note">{previewError}</div>}
            {!previewError && samples === null && <div className="preview-note">Loading...</div>}
            {samples?.map((note) => (
              <div key={note.id} className="preview-note">
                {note.title && <div className="preview-note-title">{note.title}</div>}
                <div className="preview-note-content">{note.content}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  },
);
