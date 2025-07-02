import { useState, useCallback } from 'react';

import { Tag } from '@/types';

import './styles.css';

interface TagDialogProps {
  isOpen: boolean;
  selectedNoteIds: string[];
  existingTags: Tag[];
  onClose: () => void;
  onConfirm: (tagName: string) => void;
}

export const TagDialog = ({
  isOpen,
  selectedNoteIds,
  existingTags,
  onClose,
  onConfirm,
}: TagDialogProps) => {
  const [newTagName, setNewTagName] = useState('');
  const [selectedExistingTag, setSelectedExistingTag] = useState('');
  const [isCreatingNew, setIsCreatingNew] = useState(true);

  const handleConfirm = useCallback(() => {
    const tagName = isCreatingNew ? newTagName.trim() : selectedExistingTag;

    if (!tagName) {
      return;
    }

    onConfirm(tagName);
    setNewTagName('');
    setSelectedExistingTag('');
    setIsCreatingNew(true);
  }, [isCreatingNew, newTagName, selectedExistingTag, onConfirm]);

  const handleCancel = useCallback(() => {
    setNewTagName('');
    setSelectedExistingTag('');
    setIsCreatingNew(true);
    onClose();
  }, [onClose]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleConfirm();
      } else if (e.key === 'Escape') {
        handleCancel();
      }
    },
    [handleConfirm, handleCancel],
  );

  const handleDialogClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
  }, []);

  const handleCreateNewClick = useCallback(() => {
    setIsCreatingNew(true);
  }, []);

  const handleExistingTagClick = useCallback(() => {
    setIsCreatingNew(false);
  }, []);

  const handleNewTagChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setNewTagName(e.target.value);
  }, []);

  const handleExistingTagChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedExistingTag(e.target.value);
  }, []);

  if (!isOpen) {
    return null;
  }

  const canConfirm = isCreatingNew ? newTagName.trim().length > 0 : selectedExistingTag.length > 0;

  return (
    <div className="tag-dialog-overlay" onClick={handleCancel}>
      <div className="tag-dialog" onClick={handleDialogClick}>
        <div className="tag-dialog-header">
          <h3>Tag Notes</h3>
          <button className="close-button" onClick={handleCancel}>
            <span className="material-icons">close</span>
          </button>
        </div>

        <div className="tag-dialog-content">
          <p>
            Tagging {selectedNoteIds.length} note{selectedNoteIds.length === 1 ? '' : 's'}
          </p>

          <div className="tag-option-toggle">
            <button
              className={`toggle-button ${isCreatingNew ? 'active' : ''}`}
              onClick={handleCreateNewClick}
            >
              Create New Tag
            </button>
            <button
              className={`toggle-button ${!isCreatingNew ? 'active' : ''}`}
              onClick={handleExistingTagClick}
              disabled={existingTags.length === 0}
            >
              Use Existing Tag
            </button>
          </div>

          {isCreatingNew ? (
            <div className="new-tag-input">
              <input
                type="text"
                value={newTagName}
                onChange={handleNewTagChange}
                onKeyDown={handleKeyDown}
                placeholder="Enter tag name..."
                autoFocus
                maxLength={50}
              />
            </div>
          ) : (
            <div className="existing-tag-select">
              <select
                value={selectedExistingTag}
                onChange={handleExistingTagChange}
                onKeyDown={handleKeyDown}
              >
                <option value="">Select an existing tag...</option>
                {existingTags.map((tag) => (
                  <option key={tag.name} value={tag.name}>
                    {tag.name} ({tag.count} notes)
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="tag-dialog-footer">
          <button className="cancel-button" onClick={handleCancel}>
            Cancel
          </button>
          <button className="confirm-button" onClick={handleConfirm} disabled={!canConfirm}>
            Tag Notes
          </button>
        </div>
      </div>
    </div>
  );
};
