import { memo, useState, useCallback } from 'react';

import { ProposalState } from '@/types';

interface ProposalCardProps {
  state: ProposalState;
  index: number;
  allProposals: ProposalState[];
  onApprove: (index: number) => void;
  onReject: (index: number) => void;
  onRename: (index: number, newName: string) => void;
  onMerge: (sourceIndex: number, targetIndex: number) => void;
}

export const ProposalCard = memo(
  ({ state, index, allProposals, onApprove, onReject, onRename, onMerge }: ProposalCardProps) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [isRenaming, setIsRenaming] = useState(false);
    const [renameValue, setRenameValue] = useState(state.proposal.tag_name);
    const [isMerging, setIsMerging] = useState(false);

    const handleRenameSubmit = useCallback(() => {
      if (renameValue.trim() && renameValue !== state.proposal.tag_name) {
        onRename(index, renameValue.trim());
      }
      setIsRenaming(false);
    }, [renameValue, state.proposal.tag_name, index, onRename]);

    const handleMergeSelect = useCallback(
      (targetIndex: number) => {
        onMerge(index, targetIndex);
        setIsMerging(false);
      },
      [index, onMerge],
    );

    const confidenceColor =
      state.proposal.confidence >= 0.7
        ? '#0f9d58'
        : state.proposal.confidence >= 0.4
          ? '#f9ab00'
          : '#ea4335';

    const actionClass =
      state.action === 'approve'
        ? 'approved'
        : state.action === 'reject'
          ? 'rejected'
          : state.action === 'rename'
            ? 'renamed'
            : state.action === 'merge'
              ? 'merged'
              : '';

    return (
      <div className={`proposal-card ${actionClass}`}>
        <div className="proposal-header">
          <div className="proposal-tag-info">
            {isRenaming ? (
              <div className="rename-input-group">
                <input
                  type="text"
                  className="rename-input"
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      handleRenameSubmit();
                    }
                    if (e.key === 'Escape') {
                      setIsRenaming(false);
                    }
                  }}
                  autoFocus
                />
                <button className="rename-confirm" onClick={handleRenameSubmit}>
                  <span className="material-icons">check</span>
                </button>
                <button className="rename-cancel" onClick={() => setIsRenaming(false)}>
                  <span className="material-icons">close</span>
                </button>
              </div>
            ) : (
              <div className="proposal-tag-name">
                <span className="material-icons">label</span>
                <span className="tag-name-text">
                  {state.action === 'rename' && state.newName
                    ? `${state.newName}`
                    : state.proposal.tag_name}
                </span>
                {state.action === 'rename' && state.newName && (
                  <span className="original-name">(was: {state.proposal.tag_name})</span>
                )}
                {state.action === 'merge' && state.mergeTarget && (
                  <span className="merge-info">
                    <span className="material-icons">merge_type</span>
                    into {state.mergeTarget}
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="proposal-meta">
            <span className="proposal-count">
              <span className="material-icons">description</span>
              {state.proposal.note_count}
            </span>
            <span className="proposal-confidence" style={{ color: confidenceColor }}>
              {Math.round(state.proposal.confidence * 100)}%
            </span>
          </div>
        </div>

        <div className="proposal-actions">
          <button
            className={`proposal-action-btn approve ${state.action === 'approve' ? 'active' : ''}`}
            onClick={() => onApprove(index)}
            title="Approve"
          >
            <span className="material-icons">check</span>
          </button>
          <button
            className="proposal-action-btn rename"
            onClick={() => {
              setRenameValue(state.proposal.tag_name);
              setIsRenaming(true);
            }}
            title="Rename"
          >
            <span className="material-icons">edit</span>
          </button>
          <button
            className={`proposal-action-btn merge ${isMerging ? 'active' : ''}`}
            onClick={() => setIsMerging(!isMerging)}
            title="Merge into another tag"
          >
            <span className="material-icons">merge_type</span>
          </button>
          <button
            className={`proposal-action-btn reject ${state.action === 'reject' ? 'active' : ''}`}
            onClick={() => onReject(index)}
            title="Reject"
          >
            <span className="material-icons">close</span>
          </button>
        </div>

        {isMerging && (
          <div className="merge-selector">
            <span className="merge-label">Merge into:</span>
            {allProposals
              .filter((_, i) => i !== index)
              .map((p) => {
                const originalIndex = allProposals.findIndex((ap) => ap === p);
                return (
                  <button
                    key={originalIndex}
                    className="merge-target-btn"
                    onClick={() => handleMergeSelect(originalIndex)}
                  >
                    {p.proposal.tag_name}
                  </button>
                );
              })}
          </div>
        )}

        <button className="proposal-preview-toggle" onClick={() => setIsExpanded(!isExpanded)}>
          <span className="material-icons">{isExpanded ? 'expand_less' : 'expand_more'}</span>
          {isExpanded ? 'Hide' : 'Preview'} notes
        </button>

        {isExpanded && (
          <div className="proposal-preview-notes">
            {state.proposal.sample_notes.map((note) => (
              <div key={note.id} className="preview-note">
                {note.title && <div className="preview-note-title">{note.title}</div>}
                <div className="preview-note-content">{note.content}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  },
);
