import { memo } from 'react';

import { CategorizationProgress as ProgressType } from '@/types';

interface CategorizationProgressProps {
  progress: ProgressType;
  onCancel: () => void;
}

const STAGES = [
  { key: 'reducing', label: 'Analyzing' },
  { key: 'clustering', label: 'Grouping' },
  { key: 'naming', label: 'Naming' },
];

export const CategorizationProgress = memo(
  ({ progress, onCancel }: CategorizationProgressProps) => {
    const currentStageIndex = STAGES.findIndex((s) => s.key === progress.stage);

    return (
      <div className="categorization-progress">
        <div className="progress-stages">
          {STAGES.map((stage, index) => (
            <div
              key={stage.key}
              className={`progress-stage ${
                index < currentStageIndex
                  ? 'completed'
                  : index === currentStageIndex
                    ? 'active'
                    : ''
              }`}
            >
              <div className="stage-indicator">
                {index < currentStageIndex ? (
                  <span className="material-icons">check_circle</span>
                ) : index === currentStageIndex ? (
                  <span className="material-icons spinning">autorenew</span>
                ) : (
                  <span className="material-icons">radio_button_unchecked</span>
                )}
              </div>
              <span className="stage-label">{stage.label}</span>
            </div>
          ))}
        </div>

        <div className="progress-bar-container">
          <div
            className="progress-bar-fill"
            style={{ width: `${Math.round(progress.progress * 100)}%` }}
          />
        </div>

        <div className="progress-info">
          <span className="progress-message">{progress.message}</span>
          {progress.current && progress.total && (
            <span className="progress-count">
              {progress.current} / {progress.total}
            </span>
          )}
        </div>

        <button className="progress-cancel-button" onClick={onCancel}>
          <span className="material-icons">close</span>
          Cancel
        </button>
      </div>
    );
  },
);
