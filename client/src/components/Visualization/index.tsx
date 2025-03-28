import { memo, useCallback, useState, useEffect } from 'react';

import { useEmbeddings } from '@/hooks/useEmbeddings';
import { Note } from '@/types';

import { EmbeddingsVisualization } from './EmbeddingsVisualization';
import './styles.css';

interface VisualizationProps {
  searchResults: Note[];
  onSelectNote: (noteId: string) => void;
  isAllNotesView?: boolean;
}

export const Visualization = memo(
  ({ searchResults, onSelectNote, isAllNotesView = false }: VisualizationProps) => {
    const { embeddings, isLoading, error } = useEmbeddings();
    const [showAllPoints, setShowAllPoints] = useState(isAllNotesView);
    const [matchThreshold, setMatchThreshold] = useState(0); // 0-100%
    const [spreadFactor, setSpreadFactor] = useState(5); // 1-10

    // Force showAllPoints to be true if in All Notes view
    useEffect(() => {
      if (isAllNotesView) {
        setShowAllPoints(true);
      }
    }, [isAllNotesView]);

    const toggleShowAllPoints = useCallback(() => {
      if (!isAllNotesView) {
        setShowAllPoints((prev) => !prev);
      }
    }, [isAllNotesView]);

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
      <div
        className={`visualization-wrapper ${isAllNotesView ? 'all-notes-visualization-wrapper' : ''}`}
      >
        <EmbeddingsVisualization
          embeddings={embeddings}
          searchResults={searchResults}
          isLoading={isLoading}
          onSelectNote={onSelectNote}
          showAllPoints={showAllPoints}
          matchThreshold={matchThreshold}
          spreadFactor={spreadFactor}
        />

        {!isAllNotesView && (
          <>
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
          </>
        )}
      </div>
    );
  },
);
