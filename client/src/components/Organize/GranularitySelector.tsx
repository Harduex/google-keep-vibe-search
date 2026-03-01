import { memo } from 'react';

import { Granularity } from '@/types';

interface GranularitySelectorProps {
  value: Granularity;
  onChange: (granularity: Granularity) => void;
  disabled?: boolean;
}

export const GranularitySelector = memo(
  ({ value, onChange, disabled }: GranularitySelectorProps) => {
    return (
      <div className="granularity-selector">
        <button
          className={`granularity-option ${value === 'broad' ? 'active' : ''}`}
          onClick={() => onChange('broad')}
          disabled={disabled}
        >
          <span className="material-icons">category</span>
          <div className="granularity-text">
            <span className="granularity-label">Broad Categories</span>
            <span className="granularity-desc">Fewer, larger groups</span>
          </div>
        </button>
        <button
          className={`granularity-option ${value === 'specific' ? 'active' : ''}`}
          onClick={() => onChange('specific')}
          disabled={disabled}
        >
          <span className="material-icons">tune</span>
          <div className="granularity-text">
            <span className="granularity-label">Specific Tags</span>
            <span className="granularity-desc">More, smaller groups</span>
          </div>
        </button>
      </div>
    );
  },
);
