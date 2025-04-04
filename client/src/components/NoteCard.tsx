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
  onShowRelated: (content: string) => void;
}

export const NoteCard = memo(
  ({ note, query, refinementKeywords, onShowRelated }: NoteCardProps) => {
    const scorePercentage = calculateScorePercentage(note.score);
    const highlightedTitle = highlightMatches(note.title, query, refinementKeywords);

    const handleRelatedClick = useCallback(() => {
      const noteContent = `${note.title} ${note.content}`;
      onShowRelated(noteContent);
    }, [note.title, note.content, onShowRelated]);

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
      <div className={`note-card ${note.color !== 'DEFAULT' ? `color-${note.color}` : ''}`}>
        <div className="note-header">
          {/* Badges */}
          {note.pinned && <span className="note-badge badge-pinned">Pinned</span>}
          {note.archived && <span className="note-badge badge-archived">Archived</span>}
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
