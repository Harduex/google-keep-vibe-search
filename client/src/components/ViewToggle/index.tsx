import { memo, useCallback } from 'react';

import { VIEW_MODES } from '@/const';
import { ViewMode } from '@/types';
import './styles.css';

interface ViewToggleProps {
  currentView: ViewMode;
  onChange: (view: ViewMode) => void;
}

export const ViewToggle = memo(({ currentView, onChange }: ViewToggleProps) => {
  const handleShowListView = useCallback(() => {
    onChange(VIEW_MODES.LIST);
  }, [onChange]);

  const handleShowVisualizationView = useCallback(() => {
    onChange(VIEW_MODES.VISUALIZATION);
  }, [onChange]);

  return (
    <div className="view-toggle">
      <button
        className={`view-toggle-btn ${currentView === VIEW_MODES.LIST ? 'active' : ''}`}
        onClick={handleShowListView}
        aria-label="List view"
        title="List view"
      >
        <span className="material-icons">view_list</span>
      </button>
      <button
        className={`view-toggle-btn ${currentView === VIEW_MODES.VISUALIZATION ? 'active' : ''}`}
        onClick={handleShowVisualizationView}
        aria-label="3D visualization view"
        title="3D visualization view"
      >
        <span className="material-icons">bubble_chart</span>
      </button>
    </div>
  );
});
