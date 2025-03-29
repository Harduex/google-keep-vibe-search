import { memo } from 'react';

import { NoteCard } from '@/components/NoteCard';
import { Note } from '@/types';

import './styles.css';

interface ChatNotesProps {
  notes: Note[];
  query: string;
  onShowRelated: (content: string) => void;
}

export const ChatNotes = memo(({ notes, query, onShowRelated }: ChatNotesProps) => {
  if (!notes || notes.length === 0) {
    return (
      <div className="chat-notes">
        <h3 className="notes-header">
          <span className="material-icons">auto_stories</span>
          Context Notes
        </h3>
        <div className="empty-notes">
          <p>No notes are being used for context yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-notes">
      <h3 className="notes-header">
        <span className="material-icons">auto_stories</span>
        Notes used for context
      </h3>
      <div className="notes-list">
        {notes.map((note) => (
          <NoteCard key={note.id} note={note} query={query} onShowRelated={onShowRelated} />
        ))}
      </div>
    </div>
  );
});
