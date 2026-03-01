import { useOrganize } from '@/hooks/useOrganize';

import { CategorizationProgress } from './CategorizationProgress';
import { GranularitySelector } from './GranularitySelector';
import { ProposalDashboard } from './ProposalDashboard';
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
          onApply={applyProposals}
          onRecategorize={startCategorization}
        />
      )}
    </div>
  );
};
