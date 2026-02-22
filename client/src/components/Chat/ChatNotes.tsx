import { memo, useState } from 'react';

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
  /** Total number of notes in the system. */
  totalNotes?: number;
}

export const ChatNotes = memo(
  ({ notes, query, onShowRelated, contextItems = [], intent, totalNotes = 0 }: ChatNotesProps) => {
    const { removeTagFromNote } = useTags();
    const [showInfo, setShowInfo] = useState(false);

    const hasContext = contextItems.length > 0 || (notes && notes.length > 0);

    // Count unique notes (context items may have multiple chunks per note)
    const uniqueNoteCount = new Set(contextItems.map((item) => item.note_id)).size;

    if (!hasContext) {
      return (
        <div className="chat-notes">
          <h3 className="notes-header">
            <span className="material-icons">auto_stories</span>
            Context Notes
          </h3>
          <div className="empty-notes">
            <p>No notes are being used for context yet.</p>
            <p className="empty-notes-hint">
              Send a message to retrieve relevant notes from your collection.
            </p>
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
          <span className="notes-header-text">
            Context
            {contextItems.length > 0 && totalNotes > 0 && (
              <span className="notes-count-badge">
                Top {uniqueNoteCount} of {totalNotes}
              </span>
            )}
          </span>
          {intent && <span className="context-intent-badge">{intent}</span>}
          <button
            className="context-info-toggle"
            onClick={() => setShowInfo((prev) => !prev)}
            title="How context retrieval works"
          >
            <span className="material-icons" style={{ fontSize: '16px' }}>
              {showInfo ? 'expand_less' : 'info_outline'}
            </span>
          </button>
        </h3>

        {showInfo && (
          <div className="context-info-panel">
            <p>
              Your question is matched against all{' '}
              {totalNotes > 0 ? totalNotes.toLocaleString() : ''} notes using semantic search. The
              top {uniqueNoteCount || 'N'} most relevant are sent as context to the AI to ground its
              response.
            </p>
          </div>
        )}

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
