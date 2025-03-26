import { memo } from 'react';

interface ClustersButtonProps {
  onClick: () => void;
  isActive: boolean;
}

export const ClustersButton = memo(({ onClick, isActive }: ClustersButtonProps) => {
  return (
    <button
      className={`clusters-button ${isActive ? 'active' : ''}`}
      onClick={onClick}
      title="View Note Clusters"
    >
      <span className="material-icons">bubble_chart</span>
      <span>Clusters</span>
    </button>
  );
});

ClustersButton.displayName = 'ClustersButton';
