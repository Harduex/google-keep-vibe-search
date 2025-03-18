import { memo, useCallback } from 'react';

import { API_ROUTES } from '@/const';
import { Note } from '@/types/index';
import { calculateScorePercentage, highlightMatches } from '@/helpers';

import { NoteContent } from '@/components/NoteContent';

interface NoteCardProps {
  note: Note;
  query: string;
  onShowRelated: (content: string) => void;
}

export const NoteCard = memo(({ note, query, onShowRelated }: NoteCardProps) => {
  const scorePercentage = calculateScorePercentage(note.score);
  const highlightedTitle = highlightMatches(note.title, query);

  const handleRelatedClick = useCallback(() => {
    const noteContent = `${note.title} ${note.content}`;
    onShowRelated(noteContent);
  }, [note.title, note.content, onShowRelated]);

  const handleImageClick = useCallback(
    (filePath: string) => () => {
      window.open(`${API_ROUTES.IMAGE}/${encodeURIComponent(filePath)}`, '_blank');
    },
    []
  );

  return (
    <div className={`note-card ${note.color !== 'DEFAULT' ? `color-${note.color}` : ''}`}>
      <div className="note-header">
        {/* Badges */}
        {note.pinned && <span className="note-badge badge-pinned">Pinned</span>}
        {note.archived && <span className="note-badge badge-archived">Archived</span>}
        <span className="note-badge badge-score">{scorePercentage}% match</span>

        {/* Title */}
        {note.title && (
          <div className="note-title" dangerouslySetInnerHTML={{ __html: highlightedTitle }} />
        )}
      </div>

      {/* Content */}
      <NoteContent content={note.content} query={query} />

      {/* Attachments */}
      {renderAttachments(note, handleImageClick)}

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
});

const renderAttachments = (note: Note, handleImageClick: (filePath: string) => () => void) => {
  if (!note.attachments?.length) {
    return null;
  }

  const images = note.attachments.filter((attachment) => attachment.mimetype?.startsWith('image/'));

  if (!images.length) {
    return null;
  }

  return (
    <div className="note-attachments">
      {images.map((attachment, i) => (
        <div key={i} className="note-image-container">
          <img
            src={`${API_ROUTES.IMAGE}/${encodeURIComponent(attachment.filePath)}`}
            alt="Attached image"
            className="note-image"
            onClick={handleImageClick(attachment.filePath)}
          />
        </div>
      ))}
    </div>
  );
};

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

NoteCard.displayName = 'NoteCard';
