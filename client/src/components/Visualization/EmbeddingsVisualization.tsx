import { OrbitControls, Text, Billboard } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { useRef, useState, useMemo, useCallback } from 'react';
import * as THREE from 'three';

import { calculateScorePercentage } from '@/helpers';
import { EmbeddingPoint } from '@/hooks/useEmbeddings';
import { Note } from '@/types';

import { VisualizationControls } from './VisualizationControls';

interface EmbeddingsVisualizationProps {
  embeddings: EmbeddingPoint[];
  searchResults: Note[];
  isLoading: boolean;
  onSelectNote: (noteId: string) => void;
  showAllPoints: boolean;
  matchThreshold: number;
  spreadFactor: number;
  isAllNotesView?: boolean;
  toggleShowAllPoints: () => void;
  handleMatchThresholdChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleSpreadFactorChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

export const EmbeddingsVisualization = ({
  embeddings,
  searchResults,
  isLoading,
  onSelectNote,
  showAllPoints,
  matchThreshold,
  spreadFactor,
  isAllNotesView = false,
  toggleShowAllPoints,
  handleMatchThresholdChange,
  handleSpreadFactorChange,
}: EmbeddingsVisualizationProps) => {
  const [hoveredPoint, setHoveredPoint] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [isPointerOverPoint, setIsPointerOverPoint] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Create a map of search result IDs and scores for filtering
  const searchResultMap = useMemo(() => {
    const map = new Map<string, number>();
    searchResults.forEach((result) => {
      map.set(result.id, calculateScorePercentage(result.score));
    });
    return map;
  }, [searchResults]);

  // Filter points based on the showAllPoints toggle and match threshold
  const visiblePoints = useMemo(() => {
    if (showAllPoints) {
      // Show all points, but still filter search results by threshold
      return embeddings.filter((point) => {
        const score = searchResultMap.get(point.id) || 0;
        return !searchResultMap.has(point.id) || score >= matchThreshold;
      });
    } else {
      // Only show search results above threshold
      return embeddings.filter((point) => {
        const score = searchResultMap.get(point.id) || 0;
        return searchResultMap.has(point.id) && score >= matchThreshold;
      });
    }
  }, [embeddings, searchResultMap, showAllPoints, matchThreshold]);

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) {
      return;
    }

    if (!document.fullscreenElement) {
      containerRef.current
        .requestFullscreen()
        .then(() => {
          setIsFullscreen(true);
        })
        .catch((_err) => {
          // Handle fullscreen error silently in production
          setIsFullscreen(false);
        });
    } else {
      document
        .exitFullscreen()
        .then(() => {
          setIsFullscreen(false);
        })
        .catch((_err) => {
          // Handle exit fullscreen error silently
        });
    }
  }, []);

  if (isLoading) {
    return <div className="visualization-loading">Loading visualization...</div>;
  }

  if (embeddings.length === 0) {
    return <div className="visualization-empty">No embeddings available for visualization.</div>;
  }

  if (visiblePoints.length === 0) {
    return <div className="visualization-empty">No points match the current filter criteria.</div>;
  }

  return (
    <div
      className={`visualization-container ${isPointerOverPoint ? 'point-hover' : ''}`}
      ref={containerRef}
    >
      <button className="fullscreen-toggle" onClick={toggleFullscreen}>
        <span className="material-icons">{isFullscreen ? 'fullscreen_exit' : 'fullscreen'}</span>
      </button>
      <Canvas camera={{ position: [0, 0, 15], fov: 75 }}>
        <ambientLight intensity={0.5} />
        <pointLight position={[10, 10, 10]} intensity={1} />
        <PointCloud
          points={visiblePoints}
          searchResultMap={searchResultMap}
          hoveredPoint={hoveredPoint}
          setHoveredPoint={setHoveredPoint}
          onSelectNote={onSelectNote}
          spreadFactor={spreadFactor}
          setIsPointerOverPoint={setIsPointerOverPoint}
        />
        <OrbitControls enableZoom enablePan enableRotate />
      </Canvas>

      <VisualizationControls
        isAllNotesView={isAllNotesView}
        showAllPoints={showAllPoints}
        toggleShowAllPoints={toggleShowAllPoints}
        matchThreshold={matchThreshold}
        handleMatchThresholdChange={handleMatchThresholdChange}
        spreadFactor={spreadFactor}
        handleSpreadFactorChange={handleSpreadFactorChange}
      />
    </div>
  );
};

interface PointCloudProps {
  points: EmbeddingPoint[];
  searchResultMap: Map<string, number>;
  hoveredPoint: string | null;
  setHoveredPoint: (id: string | null) => void;
  onSelectNote: (noteId: string) => void;
  spreadFactor: number;
  setIsPointerOverPoint: (isOver: boolean) => void;
}

const PointCloud = ({
  points,
  searchResultMap,
  hoveredPoint,
  setHoveredPoint,
  onSelectNote,
  spreadFactor,
  setIsPointerOverPoint,
}: PointCloudProps) => {
  const groupRef = useRef<THREE.Group>(null);

  // Scale factor to ensure points aren't too spread out or too clustered
  const scaleFactor = useMemo(() => {
    // Find the maximum absolute coordinate value
    let maxAbs = 0;
    points.forEach((point) => {
      point.coordinates.forEach((coord) => {
        const absVal = Math.abs(coord);
        if (absVal > maxAbs) {
          maxAbs = absVal;
        }
      });
    });

    // Scale to fit in approximately -5 to 5 range, adjusted by spread factor
    return maxAbs > 0 ? spreadFactor / maxAbs : 1;
  }, [points, spreadFactor]);

  const handlePointClick = useCallback(
    (pointId: string) => () => {
      onSelectNote(pointId);
    },
    [onSelectNote],
  );

  const handlePointerOver = useCallback(
    (pointId: string) => () => {
      setHoveredPoint(pointId);
      setIsPointerOverPoint(true);
    },
    [setHoveredPoint, setIsPointerOverPoint],
  );

  const handlePointerOut = useCallback(() => {
    setHoveredPoint(null);
    setIsPointerOverPoint(false);
  }, [setHoveredPoint, setIsPointerOverPoint]);

  return (
    <group ref={groupRef}>
      {points.map((point) => {
        const isSearchResult = searchResultMap.has(point.id);
        const score = searchResultMap.get(point.id) || 0;
        const isHovered = hoveredPoint === point.id;
        const [x, y, z] = point.coordinates.map((coord) => coord * scaleFactor);

        // Calculate color based on match score for search results
        let pointColor = '#9e9e9e'; // Default gray for non-search results
        if (isSearchResult) {
          // Create a color gradient from orange (low score) to green (high score)
          if (score >= 70) {
            pointColor = '#4caf50'; // Green for high scores
          } else if (score >= 40) {
            pointColor = '#ffeb3b'; // Yellow for medium scores
          } else {
            pointColor = '#ff9800'; // Orange for low scores
          }
        }

        return (
          <group key={point.id} position={[x, y, z]}>
            <mesh
              onClick={handlePointClick(point.id)}
              onPointerOver={handlePointerOver(point.id)}
              onPointerOut={handlePointerOut}
            >
              <sphereGeometry args={[isHovered ? 0.15 : 0.1, 16, 16]} />
              <meshStandardMaterial
                color={pointColor}
                emissive={isHovered ? '#ffffff' : '#000000'}
                emissiveIntensity={isHovered ? 0.5 : 0}
                opacity={isSearchResult ? 0.7 : 0.15}
                transparent={true}
              />
            </mesh>

            {isHovered && (
              <>
                <Billboard follow={true} position={[0, 0.3, 0]}>
                  <mesh renderOrder={1}>
                    <meshBasicMaterial
                      color="#000000"
                      opacity={0.6}
                      transparent
                      depthWrite={false}
                      depthTest={false}
                    />
                  </mesh>

                  <Text
                    position={[0, 0, 0.01]}
                    color="white"
                    fontSize={0.2}
                    maxWidth={2}
                    textAlign="center"
                    anchorX="center"
                    anchorY="middle"
                    outlineWidth={0.02}
                    outlineColor="#000000"
                    renderOrder={2}
                    material={
                      new THREE.MeshBasicMaterial({
                        color: 'white',
                        depthWrite: false,
                        depthTest: false,
                        transparent: true,
                      })
                    }
                  >
                    {isSearchResult ? `${score}% - ` : ''}
                    {point.title || point.content.substring(0, 100) + '...'}
                  </Text>
                </Billboard>
              </>
            )}
          </group>
        );
      })}
    </group>
  );
};
