import { memo, useCallback, useState } from 'react';

import { ChatSessionSummary } from '@/types';

interface SessionListProps {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  onNewChat: () => void;
  onLoadSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void;
}

export const SessionList = memo(
  ({
    sessions,
    activeSessionId,
    onNewChat,
    onLoadSession,
    onDeleteSession,
    onRenameSession,
  }: SessionListProps) => {
    const [renamingId, setRenamingId] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState('');

    const startRename = useCallback((session: ChatSessionSummary) => {
      setRenamingId(session.id);
      setRenameValue(session.title);
    }, []);

    const submitRename = useCallback(() => {
      if (renamingId && renameValue.trim()) {
        onRenameSession(renamingId, renameValue.trim());
      }
      setRenamingId(null);
      setRenameValue('');
    }, [renamingId, renameValue, onRenameSession]);

    const handleRenameKeyDown = useCallback(
      (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
          submitRename();
        } else if (e.key === 'Escape') {
          setRenamingId(null);
        }
      },
      [submitRename],
    );

    const formatDate = (dateStr: string) => {
      if (!dateStr) return '';
      try {
        const d = new Date(dateStr);
        const now = new Date();
        const diffMs = now.getTime() - d.getTime();
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) return 'Today';
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays}d ago`;
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      } catch {
        return '';
      }
    };

    return (
      <div className="session-list">
        <div className="session-list-header">
          <button className="new-chat-button" onClick={onNewChat} title="Start a new chat">
            <span className="material-icons">add</span>
            New Chat
          </button>
        </div>

        <div className="session-list-items">
          {sessions.length === 0 ? (
            <div className="session-list-empty">
              <span className="material-icons">forum</span>
              <p>No conversations yet</p>
            </div>
          ) : (
            sessions.map((session) => (
              <div
                key={session.id}
                className={`session-item ${activeSessionId === session.id ? 'active' : ''}`}
                onClick={() => onLoadSession(session.id)}
              >
                {renamingId === session.id ? (
                  <input
                    className="session-rename-input"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={handleRenameKeyDown}
                    onBlur={submitRename}
                    autoFocus
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <>
                    <div className="session-item-content">
                      <span className="session-title">{session.title}</span>
                      <span className="session-meta">
                        {session.message_count} msgs
                        {session.updated_at && ` · ${formatDate(session.updated_at)}`}
                      </span>
                    </div>
                    <div className="session-actions">
                      <button
                        className="session-action-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          startRename(session);
                        }}
                        title="Rename"
                      >
                        <span className="material-icons">edit</span>
                      </button>
                      <button
                        className="session-action-btn delete"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(session.id);
                        }}
                        title="Delete"
                      >
                        <span className="material-icons">delete_outline</span>
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    );
  },
);
