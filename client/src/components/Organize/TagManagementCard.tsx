import { memo, useState, useCallback } from 'react';

import { Tag } from '@/types';

interface TagManagementCardProps {
  tag: Tag;
  allTags: Tag[];
  onRename: (oldName: string, newName: string) => void;
  onMerge: (sourceTag: string, targetTag: string) => void;
  onRemove: (tagName: string) => void;
}

export const TagManagementCard = memo(
  ({ tag, allTags, onRename, onMerge, onRemove }: TagManagementCardProps) => {
    const [isRenaming, setIsRenaming] = useState(false);
    const [renameValue, setRenameValue] = useState(tag.name);
    const [isMerging, setIsMerging] = useState(false);

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
      </div>
    );
  },
);
