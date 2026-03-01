import { memo } from 'react';

import { ProposalState } from '@/types';

import { ProposalCard } from './ProposalCard';

interface ProposalDashboardProps {
  proposals: ProposalState[];
  actionableCount: number;
  isApplying: boolean;
  onApprove: (index: number) => void;
  onReject: (index: number) => void;
  onRename: (index: number, newName: string) => void;
  onMerge: (sourceIndex: number, targetIndex: number) => void;
  onApproveAll: () => void;
  onReset: () => void;
  onApply: () => void;
  onRecategorize: () => void;
}

export const ProposalDashboard = memo(
  ({
    proposals,
    actionableCount,
    isApplying,
    onApprove,
    onReject,
    onRename,
    onMerge,
    onApproveAll,
    onReset,
    onApply,
    onRecategorize,
  }: ProposalDashboardProps) => {
    const approved = proposals.filter((p) => p.action === 'approve').length;
    const renamed = proposals.filter((p) => p.action === 'rename').length;
    const rejected = proposals.filter((p) => p.action === 'reject').length;
    const pending = proposals.filter((p) => p.action === 'pending').length;
    const totalNotes = proposals.reduce((sum, p) => {
      if (p.action !== 'reject') {
        return sum + p.proposal.note_count;
      }
      return sum;
    }, 0);

    return (
      <div className="proposal-dashboard">
        <div className="dashboard-header">
          <div className="dashboard-stats">
            <span className="stat">
              <span className="material-icons">auto_awesome</span>
              {proposals.length} tags proposed
            </span>
            <span className="stat">
              <span className="material-icons">description</span>
              {totalNotes} notes
            </span>
            {approved > 0 && <span className="stat stat-approved">{approved} approved</span>}
            {renamed > 0 && <span className="stat stat-renamed">{renamed} renamed</span>}
            {rejected > 0 && <span className="stat stat-rejected">{rejected} rejected</span>}
            {pending > 0 && <span className="stat stat-pending">{pending} pending</span>}
          </div>

          <div className="dashboard-actions">
            <button className="dashboard-btn secondary" onClick={onRecategorize}>
              <span className="material-icons">refresh</span>
              Re-categorize
            </button>
            <button
              className="dashboard-btn secondary"
              onClick={onApproveAll}
              disabled={pending === 0}
            >
              <span className="material-icons">done_all</span>
              Approve All
            </button>
            <button className="dashboard-btn secondary" onClick={onReset}>
              <span className="material-icons">restart_alt</span>
              Reset
            </button>
            <button
              className="dashboard-btn primary"
              onClick={onApply}
              disabled={actionableCount === 0 || isApplying}
            >
              {isApplying ? (
                <>
                  <span className="material-icons spinning">autorenew</span>
                  Applying...
                </>
              ) : (
                <>
                  <span className="material-icons">check_circle</span>
                  Apply {actionableCount} Tags
                </>
              )}
            </button>
          </div>
        </div>

        <div className="proposals-list">
          {proposals.map((state, index) => (
            <ProposalCard
              key={`${state.proposal.tag_name}-${index}`}
              state={state}
              index={index}
              allProposals={proposals}
              onApprove={onApprove}
              onReject={onReject}
              onRename={onRename}
              onMerge={onMerge}
            />
          ))}
        </div>
      </div>
    );
  },
);
