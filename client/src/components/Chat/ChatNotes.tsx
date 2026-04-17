import { memo } from 'react';

import { NoteCard } from '@/components/NoteCard';
import { useTags } from '@/hooks/useTags';
import { ConflictInfo, Note } from '@/types';

import './styles.css';

interface ChatNotesProps {
  notes: Note[];
  conflicts?: ConflictInfo[];
  query: string;
  onShowRelated: (content: string) => void;
}

export const ChatNotes = memo(({ notes, conflicts, query, onShowRelated }: ChatNotesProps) => {
  const { removeTagFromNote } = useTags();

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
      {conflicts && conflicts.length > 0 && (
        <div className="conflict-banner">
          <span className="material-icons">warning</span>
          <div>
            <strong>Conflicting notes detected</strong>
            {conflicts.map((c, i) => (
              <div key={i} className="conflict-detail">
                Note #{c.note_a_index} vs Note #{c.note_b_index} (
                {Math.round(c.contradiction_score * 100)}% contradiction)
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="notes-list">
        {notes.map((note) => (
          <NoteCard
            key={note.id}
            note={note}
            query={query}
            onShowRelated={onShowRelated}
            onRemoveTag={removeTagFromNote}
          />
        ))}
      </div>
    </div>
  );
});
