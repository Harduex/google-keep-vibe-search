import { memo } from 'react';
import { ViewMode } from '@/types';
import { VIEW_MODES } from '@/const';
import './styles.css';

interface ViewToggleProps {
  currentView: ViewMode;
  onChange: (view: ViewMode) => void;
}

export const ViewToggle = memo(({ currentView, onChange }: ViewToggleProps) => {
  return (
    <div className="view-toggle">
      <button
        className={`view-toggle-btn ${currentView === VIEW_MODES.LIST ? 'active' : ''}`}
        onClick={() => onChange(VIEW_MODES.LIST)}
        aria-label="List view"
        title="List view"
      >
        <span className="material-icons">view_list</span>
      </button>
      <button
        className={`view-toggle-btn ${currentView === VIEW_MODES.VISUALIZATION ? 'active' : ''}`}
        onClick={() => onChange(VIEW_MODES.VISUALIZATION)}
        aria-label="3D visualization view"
        title="3D visualization view"
      >
        <span className="material-icons">bubble_chart</span>
      </button>
    </div>
  );
});

ViewToggle.displayName = 'ViewToggle';
