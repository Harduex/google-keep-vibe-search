import { memo, useCallback, useRef, useState } from 'react';

import ImageGallery from '@/components/ImageGallery';
import { NoteContent } from '@/components/NoteContent';
import { API_ROUTES } from '@/const';
import { calculateScorePercentage, highlightMatches } from '@/helpers';
import { Note } from '@/types/index';

interface NoteCardProps {
  note: Note;
  query: string;
  refinementKeywords?: string;
  isSelectable?: boolean;
  isSelected?: boolean;
  onShowRelated: (content: string) => void;
  onSelectNote?: (noteId: string, isSelected: boolean) => void;
  onRemoveTag?: (noteId: string, tagName: string) => void;
  onRenameTag?: (oldTagName: string, newTagName: string) => void;
}

export const NoteCard = memo(
  ({
    note,
    query,
    refinementKeywords,
    isSelectable = false,
    isSelected = false,
    onShowRelated,
    onSelectNote,
    onRemoveTag,
    onRenameTag,
  }: NoteCardProps) => {
    const scorePercentage = calculateScorePercentage(note.score);
    const highlightedTitle = highlightMatches(note.title, query, refinementKeywords);

    const [editingTag, setEditingTag] = useState<string | null>(null);
    const [editValue, setEditValue] = useState('');
    const editInputRef = useRef<HTMLInputElement>(null);
    const editCommittedRef = useRef(false);

    const handleRelatedClick = useCallback(() => {
      const noteContent = `${note.title} ${note.content}`;
      onShowRelated(noteContent);
    }, [note.title, note.content, onShowRelated]);

    const handleSelectClick = useCallback(
      (e: React.MouseEvent) => {
        e.stopPropagation();
        if (onSelectNote) {
          onSelectNote(note.id, !isSelected);
        }
      },
      [note.id, isSelected, onSelectNote],
    );

    const handleRemoveTag = useCallback(
      (e: React.MouseEvent, tagName: string) => {
        e.stopPropagation();
        if (onRemoveTag) {
          if (window.confirm(`Remove tag "${tagName}" from this note?`)) {
            onRemoveTag(note.id, tagName);
          }
        }
      },
      [note.id, onRemoveTag],
    );

    const handleStartEditTag = useCallback((e: React.MouseEvent, tagName: string) => {
      e.stopPropagation();
      editCommittedRef.current = false;
      setEditingTag(tagName);
      setEditValue(tagName);
      setTimeout(() => editInputRef.current?.focus(), 0);
    }, []);

    const handleEditKeyDown = useCallback(
      (e: React.KeyboardEvent, oldName: string) => {
        if (e.key === 'Enter') {
          const trimmed = editValue.trim();
          if (trimmed && trimmed !== oldName && onRenameTag && !editCommittedRef.current) {
            editCommittedRef.current = true;
            onRenameTag(oldName, trimmed);
          } else {
            editCommittedRef.current = true;
          }
          setEditingTag(null);
        } else if (e.key === 'Escape') {
          editCommittedRef.current = true;
          setEditingTag(null);
        }
      },
      [editValue, onRenameTag],
    );

    const handleEditBlur = useCallback(
      (oldName: string) => {
        if (!editCommittedRef.current) {
          const trimmed = editValue.trim();
          if (trimmed && trimmed !== oldName && onRenameTag) {
            onRenameTag(oldName, trimmed);
          }
        }
        setEditingTag(null);
      },
      [editValue, onRenameTag],
    );

    const handleCardClick = useCallback(() => {
      if (isSelectable && onSelectNote) {
        onSelectNote(note.id, !isSelected);
      }
    }, [isSelectable, note.id, isSelected, onSelectNote]);

    // Create image gallery data from attachments
    const galleryImages =
      note.attachments
        ?.filter((attachment) => attachment.mimetype?.startsWith('image/'))
        .map((attachment) => ({
          src: `${API_ROUTES.IMAGE}/${encodeURIComponent(attachment.filePath)}`,
          alt: 'Note attachment',
          isMatching: note.matched_image === attachment.filePath,
        })) || [];

    // Check if any images match the search query
    const hasMatchingImages = note.has_matching_images === true;
    const matchedImage = note.matched_image;

    return (
      <div
        className={`note-card ${note.color !== 'DEFAULT' ? `color-${note.color}` : ''} ${
          isSelectable ? 'selectable' : ''
        } ${isSelected ? 'selected' : ''}`}
        onClick={handleCardClick}
      >
        {isSelectable && (
          <div className="note-select-checkbox" onClick={handleSelectClick}>
            <span className={`material-icons ${isSelected ? 'selected' : ''}`}>
              {isSelected ? 'check_box' : 'check_box_outline_blank'}
            </span>
          </div>
        )}

        <div className="note-header">
          {/* Badges */}
          {note.pinned && <span className="note-badge badge-pinned">Pinned</span>}
          {note.archived && <span className="note-badge badge-archived">Archived</span>}
          {note.tags?.map((tagName) => (
            <span
              key={tagName}
              className={`note-badge badge-tag${editingTag === tagName ? ' editing' : ''}`}
              title={`Tagged: ${tagName}`}
            >
              {editingTag === tagName ? (
                <>
                  <input
                    ref={editInputRef}
                    className="tag-edit-input"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={(e) => handleEditKeyDown(e, tagName)}
                    onBlur={() => handleEditBlur(tagName)}
                    onClick={(e) => e.stopPropagation()}
                  />
                </>
              ) : (
                <>
                  <span className="material-icons">label</span>
                  {tagName}
                  {onRenameTag && (
                    <button
                      className="tag-edit-button"
                      onClick={(e) => handleStartEditTag(e, tagName)}
                      title="Rename tag"
                      aria-label={`Rename tag ${tagName}`}
                    >
                      <span className="material-icons">edit</span>
                    </button>
                  )}
                  {onRemoveTag && (
                    <button
                      className="tag-remove-button"
                      onClick={(e) => handleRemoveTag(e, tagName)}
                      title="Remove tag"
                      aria-label={`Remove tag ${tagName}`}
                    >
                      <span className="material-icons">close</span>
                    </button>
                  )}
                </>
              )}
            </span>
          ))}
          {scorePercentage ? (
            <span className="note-badge badge-score">{scorePercentage}% match</span>
          ) : null}
          {hasMatchingImages && (
            <span className="note-badge badge-image-match">
              <span className="material-icons">image_search</span> Image match
            </span>
          )}

          {/* Title */}
          {note.title && (
            <div className="note-title" dangerouslySetInnerHTML={{ __html: highlightedTitle }} />
          )}
        </div>

        {/* Content */}
        <NoteContent content={note.content} query={query} refinementKeywords={refinementKeywords} />

        {/* Image Gallery - with possible match highlight */}
        {galleryImages.length > 0 && (
          <div className="note-images-container">
            <ImageGallery images={galleryImages} />
            {hasMatchingImages && matchedImage && (
              <div className="image-match-indicator">
                <span className="material-icons">image_search</span>
                Image content matches your search query
              </div>
            )}
          </div>
        )}

        {/* Annotations */}
        {renderAnnotations(note)}

        {/* Metadata */}
        <div className="note-meta">
          <span>Created: {note.created}</span>
          <span>Last edited: {note.edited}</span>
        </div>

        {/* Actions */}
        <div className="note-actions">
          <button className="show-related-button" onClick={handleRelatedClick}>
            <span className="material-icons">layers</span> Show related
          </button>
        </div>
      </div>
    );
  },
);

const renderAnnotations = (note: Note) => {
  if (!note.annotations?.length) {
    return null;
  }

  const links = note.annotations.filter((annotation) => !!annotation.url);

  if (!links.length) {
    return null;
  }

  return (
    <div className="note-annotations">
      {links.map((annotation, i) => (
        <span key={i} className="annotation">
          <a href={annotation.url} target="_blank" rel="noreferrer">
            {annotation.title || annotation.url}
          </a>
        </span>
      ))}
    </div>
  );
};
