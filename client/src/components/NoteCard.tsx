import { memo, useCallback } from 'react';

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
  onRemoveTag?: (noteId: string) => void;
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
  }: NoteCardProps) => {
    const scorePercentage = calculateScorePercentage(note.score);
    const highlightedTitle = highlightMatches(note.title, query, refinementKeywords);

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
      (e: React.MouseEvent) => {
        e.stopPropagation();
        if (onRemoveTag && note.tag) {
          if (window.confirm(`Remove tag "${note.tag}" from this note?`)) {
            onRemoveTag(note.id);
          }
        }
      },
      [note.id, note.tag, onRemoveTag],
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
          {note.tag && (
            <span className="note-badge badge-tag" title={`Tagged: ${note.tag}`}>
              <span className="material-icons">label</span>
              {note.tag}
              {onRemoveTag && (
                <button
                  className="tag-remove-button"
                  onClick={handleRemoveTag}
                  title="Remove tag"
                  aria-label={`Remove tag ${note.tag}`}
                >
                  <span className="material-icons">close</span>
                </button>
              )}
            </span>
          )}
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
