import { memo, useCallback, useState } from 'react';

import { useEmbeddings } from '@/hooks/useEmbeddings';
import { Note } from '@/types';

import { EmbeddingsVisualization } from './EmbeddingsVisualization';
import './styles.css';

interface VisualizationProps {
  searchResults: Note[];
  onSelectNote: (noteId: string) => void;
}

export const Visualization = memo(({ searchResults, onSelectNote }: VisualizationProps) => {
  const { embeddings, isLoading, error } = useEmbeddings();
  const [showAllPoints, setShowAllPoints] = useState(false);
  const [matchThreshold, setMatchThreshold] = useState(0); // 0-100%
  const [spreadFactor, setSpreadFactor] = useState(5); // 1-10

  const toggleShowAllPoints = useCallback(() => {
    setShowAllPoints((prev) => !prev);
  }, []);

  const handleMatchThresholdChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setMatchThreshold(parseInt(e.target.value));
  }, []);

  const handleSpreadFactorChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setSpreadFactor(parseInt(e.target.value));
  }, []);

  if (error) {
    return <div className="visualization-empty">Error loading visualization: {error}</div>;
  }

  return (
    <div className="visualization-wrapper">
      <EmbeddingsVisualization
        embeddings={embeddings}
        searchResults={searchResults}
        isLoading={isLoading}
        onSelectNote={onSelectNote}
        showAllPoints={showAllPoints}
        matchThreshold={matchThreshold}
        spreadFactor={spreadFactor}
      />

      <div className="visualization-controls">
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

      <div className="visualization-help">
        Drag to rotate • Scroll to zoom • Click point to select note
      </div>
    </div>
  );
});
