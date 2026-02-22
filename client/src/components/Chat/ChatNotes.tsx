import { memo } from 'react';

import { NoteCard } from '@/components/NoteCard';
import { useTags } from '@/hooks/useTags';
import { GroundedContext, Note } from '@/types';

import './styles.css';

interface ChatNotesProps {
  notes: Note[];
  query: string;
  onShowRelated: (content: string) => void;
  /** Grounded context items from the Router Agent. */
  contextItems?: GroundedContext[];
  /** Retrieval intent classification. */
  intent?: string;
}

export const ChatNotes = memo(
  ({ notes, query, onShowRelated, contextItems = [], intent }: ChatNotesProps) => {
    const { removeTagFromNote } = useTags();

    const hasContext = contextItems.length > 0 || (notes && notes.length > 0);

    if (!hasContext) {
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

    // Group context items by note_id
    const noteGroups = new Map<string, GroundedContext[]>();
    for (const item of contextItems) {
      const existing = noteGroups.get(item.note_id) || [];
      existing.push(item);
      noteGroups.set(item.note_id, existing);
    }

    return (
      <div className="chat-notes">
        <h3 className="notes-header">
          <span className="material-icons">auto_stories</span>
          Context
          {intent && <span className="context-intent-badge">{intent}</span>}
        </h3>

        {/* Grounded context items grouped by note */}
        {contextItems.length > 0 && (
          <div className="context-items-list">
            {Array.from(noteGroups.entries()).map(([noteId, items]) => (
              <div key={noteId} className="context-note-group">
                <div className="context-note-title">
                  <span className="material-icons" style={{ fontSize: '16px' }}>
                    description
                  </span>
                  {items[0].note_title || 'Untitled'}
                  <span className="context-score">
                    {Math.round(items[0].relevance_score * 100)}%
                  </span>
                </div>
                {items.map((item) => (
                  <div key={item.citation_id} className="context-item">
                    <div className="context-item-text">
                      {item.text.length > 150 ? item.text.slice(0, 150) + '...' : item.text}
                    </div>
                    {item.heading_trail.length > 0 && (
                      <div className="context-item-trail">{item.heading_trail.join(' > ')}</div>
                    )}
                    <div className="context-item-meta">
                      <span className="context-item-source">{item.source_type}</span>
                      <span className="context-item-id">{item.citation_id}</span>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* Legacy: full NoteCards when no grounded context */}
        {contextItems.length === 0 && notes && notes.length > 0 && (
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
        )}
      </div>
    );
  },
);
