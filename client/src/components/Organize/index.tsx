import { useCallback } from 'react';

import { useOrganize } from '@/hooks/useOrganize';
import { useTags } from '@/hooks/useTags';

import { CategorizationProgress } from './CategorizationProgress';
import { GranularitySelector } from './GranularitySelector';
import { ProposalDashboard } from './ProposalDashboard';
import { TagManagerDashboard } from './TagManagerDashboard';
import './styles.css';

export const Organize = () => {
  const {
    granularity,
    setGranularity,
    isProcessing,
    progress,
    proposals,
    isApplying,
    error,
    hasProposals,
    actionablCount,
    startCategorization,
    cancelCategorization,
    approveProposal,
    rejectProposal,
    renameProposal,
    mergeProposals,
    approveAll,
    resetProposals,
    applyProposals,
  } = useOrganize();

  const {
    tags,
    isLoading: isTagsLoading,
    renameTag,
    removeTagFromAllNotes,
    refetchTags: refetchTagList,
  } = useTags();

  const handleApplyProposals = useCallback(async () => {
    await applyProposals();
    refetchTagList();
  }, [applyProposals, refetchTagList]);

  const handleMerge = useCallback(
    async (source: string, target: string) => {
      await renameTag(source, target);
    },
    [renameTag],
  );

  return (
    <div className="organize-container">
      <div className="organize-header">
        <h2>
          <span className="material-icons">auto_awesome</span>
          Smart Tags
        </h2>
        <p className="organize-description">
          Automatically discover and organize your notes into meaningful categories using AI-powered
          topic detection.
        </p>
      </div>

      {!isProcessing && !hasProposals && (
        <>
          <GranularitySelector
            value={granularity}
            onChange={setGranularity}
            disabled={isProcessing}
          />

          <div className="organize-start">
            <button
              className="start-categorization-btn"
              onClick={startCategorization}
              disabled={isProcessing}
            >
              <span className="material-icons">auto_awesome</span>
              Auto-Categorize Notes
            </button>
          </div>
        </>
      )}

      {isProcessing && progress && (
        <CategorizationProgress progress={progress} onCancel={cancelCategorization} />
      )}

      {error && (
        <div className="organize-error">
          <span className="material-icons">error</span>
          <span>{error}</span>
        </div>
      )}

      {hasProposals && !isProcessing && (
        <ProposalDashboard
          proposals={proposals}
          actionableCount={actionablCount}
          isApplying={isApplying}
          onApprove={approveProposal}
          onReject={rejectProposal}
          onRename={renameProposal}
          onMerge={mergeProposals}
          onApproveAll={approveAll}
          onReset={resetProposals}
          onApply={handleApplyProposals}
          onRecategorize={startCategorization}
        />
      )}

      <div className="tag-manager-section">
        <div className="organize-header">
          <h2>
            <span className="material-icons">sell</span>
            Tag Manager
          </h2>
          <p className="organize-description">
            View, rename, merge, and remove tags across all your notes.
          </p>
        </div>

        <TagManagerDashboard
          tags={tags}
          isLoading={isTagsLoading}
          onRename={renameTag}
          onMerge={handleMerge}
          onRemove={removeTagFromAllNotes}
        />
      </div>
    </div>
  );
};
