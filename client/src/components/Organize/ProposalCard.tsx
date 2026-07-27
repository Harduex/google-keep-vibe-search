import { memo, useState, useCallback } from 'react';

import { ProposalState, isInfoProposal, isMergeProposal, isAssignProposal } from '@/types';

interface ProposalCardProps {
  state: ProposalState;
  index: number;
  allProposals: ProposalState[];
  /** Approve/reject take the card's stable id: a tag name for classic proposals (the list
   * grows underneath the user, so an index would shift), or an array index for dashboard
   * cards (info/merge/assign), which arrive together at the end of the run. */
  onApprove: (id: string | number) => void;
  onReject: (id: string | number) => void;
  onRename: (id: string | number, newName: string) => void;
  /** Merge is keyed by tag name only — classic proposals. Dashboard cards are never merge
   * sources or targets, so this never receives an index. */
  onMerge: (sourceTagName: string, targetTagName: string) => void;
}

/** Approve / reject controls shared by the gray-zone merge and review cards.
 *
 * `labels` makes the two outcomes explicit in words. A merge card needs it: with a bare
 * check and cross, "reject" reads as *discard these tags*, when it actually means *keep
 * them as two separate tags*. Naming the outcome is the whole difference between a
 * reversible-looking choice and a destructive-looking one. Icon-only cards keep the
 * tooltips they had. */
const ApproveRejectActions = memo(
  ({
    id,
    action,
    onApprove,
    onReject,
    labels,
  }: {
    id: string | number;
    action: ProposalState['action'];
    onApprove: (id: string | number) => void;
    onReject: (id: string | number) => void;
    labels?: { approve: string; reject: string };
  }) => (
    <div className="proposal-actions">
      <button
        className={`proposal-action-btn approve ${action === 'approve' ? 'active' : ''}`}
        onClick={() => onApprove(id)}
        title={labels?.approve ?? 'Approve'}
      >
        <span className="material-icons">check</span>
        {labels && <span className="proposal-action-label">{labels.approve}</span>}
      </button>
      <button
        className={`proposal-action-btn reject ${action === 'reject' ? 'active' : ''}`}
        onClick={() => onReject(id)}
        title={labels?.reject ?? 'Reject'}
      >
        <span className="material-icons">close</span>
        {labels && <span className="proposal-action-label">{labels.reject}</span>}
      </button>
    </div>
  ),
);

export const ProposalCard = memo(
  ({ state, index, allProposals, onApprove, onReject, onRename, onMerge }: ProposalCardProps) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [isRenaming, setIsRenaming] = useState(false);
    const [renameValue, setRenameValue] = useState(state.proposal.tag_name ?? '');
    const [isMerging, setIsMerging] = useState(false);

    const proposal = state.proposal;

    // The stable id for approve/reject/rename: tag name for classic proposals, index for
    // dashboard cards (which arrive together at the end, so an index is stable for them).
    // Classic proposals stream in one at a time, so a positional index would shift when
    // new cards arrive and silently retarget a click.
    const cardId: string | number = proposal.tag_name ?? index;

    const handleRenameSubmit = useCallback(() => {
      if (renameValue.trim() && renameValue !== proposal.tag_name) {
        onRename(cardId, renameValue.trim());
      }
      setIsRenaming(false);
    }, [renameValue, proposal.tag_name, cardId, onRename]);

    const handleMergeSelect = useCallback(
      (targetTagName: string) => {
        onMerge(proposal.tag_name ?? '', targetTagName);
        setIsMerging(false);
      },
      [proposal.tag_name, onMerge],
    );

    const confidence = proposal.confidence ?? 1;
    const confidenceColor =
      confidence >= 0.7 ? '#0f9d58' : confidence >= 0.4 ? '#f9ab00' : '#ea4335';

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

    // Read-only auto-merge notice — no buttons.
    if (isInfoProposal(proposal)) {
      return (
        <div className="proposal-card info-card">
          <div className="proposal-header">
            <div className="proposal-tag-info">
              <span className="material-icons info-icon">info</span>
              <span className="info-message">
                {proposal.message ||
                  `Auto-merged '${proposal.source_tag}' into '${proposal.target_tag}'`}
              </span>
            </div>
          </div>
        </div>
      );
    }

    // Gray-zone merge: "Merge X into Y?" with approve/reject only.
    if (isMergeProposal(proposal)) {
      return (
        <div className={`proposal-card ${actionClass}`}>
          <div className="proposal-header">
            <div className="proposal-tag-info">
              <div className="proposal-tag-name">
                <span className="material-icons">merge_type</span>
                <span className="tag-name-text">
                  Merge &lsquo;{proposal.source_tag}&rsquo; into &lsquo;{proposal.target_tag}
                  &rsquo;?
                </span>
              </div>
            </div>
            <div className="proposal-meta">
              {proposal.note_count != null && (
                <span className="proposal-count">
                  <span className="material-icons">description</span>
                  {proposal.note_count}
                </span>
              )}
              <span className="proposal-confidence" style={{ color: confidenceColor }}>
                {Math.round(confidence * 100)}%
              </span>
            </div>
          </div>
          <ApproveRejectActions
            id={cardId}
            action={state.action}
            onApprove={onApprove}
            onReject={onReject}
            labels={{ approve: 'Merge', reject: 'Keep separate' }}
          />
        </div>
      );
    }

    // Review queue: low-confidence note-to-tag assignment with approve/reject.
    if (isAssignProposal(proposal)) {
      return (
        <div className={`proposal-card ${actionClass}`}>
          <div className="proposal-header">
            <div className="proposal-tag-info">
              <div className="proposal-tag-name">
                <span className="material-icons">label</span>
                <span className="tag-name-text">
                  Note &ldquo;{proposal.note_title || 'Untitled'}&rdquo;: suggest #{proposal.tag}
                </span>
              </div>
            </div>
            <div className="proposal-meta">
              <span className="proposal-confidence" style={{ color: confidenceColor }}>
                {Math.round(confidence * 100)}%
              </span>
            </div>
          </div>
          <ApproveRejectActions
            id={cardId}
            action={state.action}
            onApprove={onApprove}
            onReject={onReject}
          />
        </div>
      );
    }

    // Classic cluster tag proposal — full approve / rename / merge / reject.
    // Merge targets are the classic proposals that have already arrived, keyed by tag name.
    // Not positional: in a list that grows underneath the user, indices shift and a staged
    // merge would silently retarget (item 6). Tag names are unique within a vocabulary.
    const mergeTargets = allProposals.filter(
      (p) =>
        p.proposal.tag_name !== undefined &&
        p.proposal.tag_name !== proposal.tag_name &&
        !isInfoProposal(p.proposal) &&
        !isMergeProposal(p.proposal) &&
        !isAssignProposal(p.proposal),
    );

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
                  {state.action === 'rename' && state.newName ? state.newName : proposal.tag_name}
                </span>
                {state.action === 'rename' && state.newName && (
                  <span className="original-name">(was: {proposal.tag_name})</span>
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
              {proposal.note_count ?? 0}
            </span>
            <span className="proposal-confidence" style={{ color: confidenceColor }}>
              {Math.round(confidence * 100)}%
            </span>
          </div>
        </div>

        <div className="proposal-actions">
          <button
            className={`proposal-action-btn approve ${state.action === 'approve' ? 'active' : ''}`}
            onClick={() => onApprove(cardId)}
            title="Approve"
          >
            <span className="material-icons">check</span>
          </button>
          <button
            className="proposal-action-btn rename"
            onClick={() => {
              setRenameValue(proposal.tag_name ?? '');
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
            onClick={() => onReject(cardId)}
            title="Reject"
          >
            <span className="material-icons">close</span>
          </button>
        </div>

        {isMerging && (
          <div className="merge-selector">
            <span className="merge-label">Merge into:</span>
            {mergeTargets.map((p) => (
              <button
                key={p.proposal.tag_name}
                className="merge-target-btn"
                onClick={() => handleMergeSelect(p.proposal.tag_name!)}
              >
                {p.proposal.tag_name}
              </button>
            ))}
          </div>
        )}

        <button className="proposal-preview-toggle" onClick={() => setIsExpanded(!isExpanded)}>
          <span className="material-icons">{isExpanded ? 'expand_less' : 'expand_more'}</span>
          {isExpanded ? 'Hide' : 'Preview'} notes
        </button>

        {isExpanded && (
          <div className="proposal-preview-notes">
            {(proposal.sample_notes ?? []).map((note) => (
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
