import React from 'react';

interface VisualizationControlsProps {
  isAllNotesView?: boolean;
  showAllPoints: boolean;
  toggleShowAllPoints: () => void;
  matchThreshold: number;
  handleMatchThresholdChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  spreadFactor: number;
  handleSpreadFactorChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

export const VisualizationControls: React.FC<VisualizationControlsProps> = ({
  isAllNotesView = false,
  showAllPoints,
  toggleShowAllPoints,
  matchThreshold,
  handleMatchThresholdChange,
  spreadFactor,
  handleSpreadFactorChange,
}) => {
  return (
    <>
      <div className={`visualization-controls ${isAllNotesView ? 'all-notes-controls' : ''}`}>
        {!isAllNotesView && (
          <>
            <button
              className={`visualization-toggle ${!showAllPoints ? 'toggle-active' : ''}`}
              onClick={toggleShowAllPoints}
            >
              {showAllPoints ? 'Hide Other Notes' : 'Show All Notes'}
            </button>

            <div className="visualization-sliders">
              <div className="slider-container">
                <label htmlFor="matchSlider">Match Threshold: {matchThreshold}%</label>
                <input
                  id="matchSlider"
                  type="range"
                  min="0"
                  max="100"
                  value={matchThreshold}
                  onChange={handleMatchThresholdChange}
                  className="slider"
                />
              </div>
            </div>
          </>
        )}

        {/* Spread slider is always shown, in both regular and all-notes view */}
        <div
          className={`visualization-sliders ${isAllNotesView ? 'all-notes-slider-container' : ''}`}
        >
          <div className="slider-container">
            <label htmlFor="spreadSlider">Spread: {spreadFactor}</label>
            <input
              id="spreadSlider"
              type="range"
              min="1"
              max="10"
              value={spreadFactor}
              onChange={handleSpreadFactorChange}
              className="slider"
            />
          </div>
        </div>
      </div>

      {!isAllNotesView && (
        <div className="visualization-legend">
          <div className="legend-item">
            <div className="legend-color legend-green"></div>
            <span>Search results</span>
          </div>
          {showAllPoints && (
            <div className="legend-item">
              <div className="legend-color legend-gray"></div>
              <span>Other notes</span>
            </div>
          )}
        </div>
      )}
    </>
  );
};
