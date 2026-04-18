import { useState } from 'react';

import { GroundingResult } from '@/types';

import './styles.css';

interface GroundingScoreProps {
  result: GroundingResult;
}

const getScoreColor = (score: number): string => {
  if (score >= 0.7) return '#4caf50';
  if (score >= 0.4) return '#ff9800';
  return '#f44336';
};

const getVerdictIcon = (verdict: string): string => {
  switch (verdict) {
    case 'supported':
      return 'check_circle';
    case 'contradicted':
      return 'cancel';
    case 'neutral':
      return 'help';
    case 'unsupported':
      return 'warning';
    default:
      return 'help';
  }
};

const getVerdictColor = (verdict: string): string => {
  switch (verdict) {
    case 'supported':
      return '#4caf50';
    case 'contradicted':
      return '#f44336';
    case 'neutral':
      return '#ff9800';
    case 'unsupported':
      return '#9e9e9e';
    default:
      return '#9e9e9e';
  }
};

export const GroundingScore = ({ result }: GroundingScoreProps) => {
  const [expanded, setExpanded] = useState(false);
  const pct = Math.round(result.overall_score * 100);
  const scoreColor = getScoreColor(result.overall_score);

  return (
    <div className="grounding-score">
      <button
        className="grounding-badge"
        onClick={() => setExpanded(!expanded)}
        title={`${result.grounded_count}/${result.total_claims} claims grounded`}
      >
        <span className="material-icons grounding-icon" style={{ color: scoreColor }}>
          verified
        </span>
        <span className="grounding-pct" style={{ color: scoreColor }}>
          {pct}%
        </span>
        <span className="grounding-label">grounded</span>
        <span className="material-icons grounding-expand">
          {expanded ? 'expand_less' : 'expand_more'}
        </span>
      </button>

      {expanded && result.claims.length > 0 && (
        <div className="grounding-claims">
          {result.claims.map((claim, idx) => (
            <div key={idx} className="grounding-claim">
              <span
                className="material-icons grounding-claim-icon"
                style={{ color: getVerdictColor(claim.verdict) }}
              >
                {getVerdictIcon(claim.verdict)}
              </span>
              <span className="grounding-claim-text">{claim.text}</span>
              {claim.cited_note && (
                <span className="grounding-claim-cite">[Note #{claim.cited_note}]</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
