import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { calculateScorePercentage } from '@/helpers';
import { useEmbeddings } from '@/hooks/useEmbeddings';
import { Note } from '@/types';

import { HoverState, Scene, SPREAD_FACTOR } from './Scene';
import {
  autoPointRadius,
  buildEdgeBuffers,
  buildPointBuffers,
  collectConnectedIds,
  hasFocus,
  isPointFocused,
  LayerToggles,
} from './sceneData';
import { SidePanel } from './SidePanel';
import { buildTagColorScale } from './tagColors';
import { useConnectionsFor } from './useConnections';
import './styles.css';

/**
 * Track the theme the document is actually in.
 *
 * Read from the DOM rather than by calling useTheme() again: a second hook instance would
 * hold its own state and go stale the moment the user toggles the theme in the header.
 */
const useDocumentTheme = (): 'light' | 'dark' => {
  const read = (): 'light' | 'dark' =>
    document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  const [mode, setMode] = useState<'light' | 'dark'>(read);

  useEffect(() => {
    const observer = new MutationObserver(() => setMode(read()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    return () => observer.disconnect();
  }, []);

  return mode;
};

const BACKGROUNDS = { light: '#fcfcfb', dark: '#1a1a19' } as const;
const GHOST_COLOR = { light: '#c9c9c6', dark: '#3a3a38' } as const;
const NO_CONNECTIONS: ReadonlySet<string> = new Set();

interface VisualizationProps {
  searchResults: Note[];
  /** Search for notes related to the selected one — the card's Related gesture. */
  onShowRelated: (content: string) => void;
  isAllNotesView?: boolean;
  /** Note to open the view focused on, set by "Show connections" in the list.
   *  The parent clears it when leaving the 3D view, so re-picking the same note
   *  is a change again and re-focuses it. */
  focusNoteId?: string | null;
}

export const Visualization = memo(
  ({ searchResults, onShowRelated, focusNoteId = null }: VisualizationProps) => {
    const { embeddings, isLoading, error } = useEmbeddings();
    const themeMode = useDocumentTheme();
    const containerRef = useRef<HTMLDivElement>(null);

    const [ghost, setGhost] = useState(false);
    const [hideUnfocused, setHideUnfocused] = useState(false);
    const [isolatedTag, setIsolatedTag] = useState<string | null>(null);
    const [chain, setChain] = useState<string[]>([]);
    const [layers, setLayers] = useState<LayerToggles>({
      similar: true,
      tags: false,
      entities: false,
    });
    const [hover, setHover] = useState<HoverState | null>(null);
    const [isFullscreen, setIsFullscreen] = useState(false);

    const selectedId = chain.length > 0 ? chain[chain.length - 1] : null;

    // Entering the view from a note's "Show connections" starts a fresh path at it.
    useEffect(() => {
      if (focusNoteId !== null) {
        setChain([focusNoteId]);
      }
    }, [focusNoteId]);

    // The view IS the filter: only the notes the list view shows are rendered.
    const visibleIds = useMemo(() => new Set(searchResults.map((n) => n.id)), [searchResults]);
    const visiblePoints = useMemo(
      () => embeddings.filter((p) => visibleIds.has(p.id)),
      [embeddings, visibleIds],
    );
    // With nothing filtered out there is nothing to ghost, and the toggle would be
    // a control that visibly does nothing. Offered only when it has an effect.
    const canGhost = embeddings.length > visiblePoints.length;
    // Ghosting filtered-out notes contradicts "hide everything else", so the
    // narrower switch wins whenever something is actually focused.
    const showGhosts =
      ghost && canGhost && !(hideUnfocused && (selectedId !== null || isolatedTag !== null));
    const ghostPoints = useMemo(
      () => (showGhosts ? embeddings.filter((p) => !visibleIds.has(p.id)) : []),
      [embeddings, visibleIds, showGhosts],
    );

    const scoreById = useMemo(() => {
      const map = new Map<string, number>();
      searchResults.forEach((n) => {
        const pct = calculateScorePercentage(n.score);
        if (pct !== null) {
          map.set(n.id, pct);
        }
      });
      return map;
    }, [searchResults]);

    // Scale from ALL embeddings, not the visible subset: positions must not shift
    // when the filter changes — spatial memory is the point of a fixed layout.
    const scaleFactor = useMemo(() => {
      let maxAbs = 0;
      embeddings.forEach((p) =>
        p.coordinates.forEach((c) => (maxAbs = Math.max(maxAbs, Math.abs(c)))),
      );
      return maxAbs > 0 ? SPREAD_FACTOR / maxAbs : 1;
    }, [embeddings]);

    // Built from the visible points, so the legend reflects what is on screen.
    const tagScale = useMemo(
      () => buildTagColorScale(visiblePoints, themeMode),
      [visiblePoints, themeMode],
    );
    const allTags = useMemo(() => {
      const tags = new Set<string>();
      visiblePoints.forEach((p) => p.tags.forEach((t) => tags.add(t)));
      return [...tags].sort((a, b) => a.localeCompare(b));
    }, [visiblePoints]);

    const { byId, errors, isLoading: connectionsLoading } = useConnectionsFor(chain);
    const connectedIds = useMemo(
      () => (chain.length > 0 ? collectConnectedIds(chain, byId, layers) : NO_CONNECTIONS),
      [chain, byId, layers],
    );

    const focusRule = useMemo(
      () => ({ isolatedTag, selectedId, connectedIds }),
      [isolatedTag, selectedId, connectedIds],
    );

    // What actually reaches the GPU. Hiding drops whatever the fade would have
    // dimmed — a selection's neighbourhood, or an isolated tag when nothing is
    // selected — instead of merely dimming it.
    const renderedPoints = useMemo(
      () =>
        hideUnfocused && hasFocus(focusRule)
          ? visiblePoints.filter((p) => isPointFocused(p, focusRule))
          : visiblePoints,
      [visiblePoints, hideUnfocused, focusRule],
    );

    // Sized from the filtered set, NOT from what survives hiding.
    // Positions never rescale, so an isolated neighbourhood still sits in the same
    // world space as the full cloud — sizing off the handful that survives inflated
    // the dots to the ceiling and left a clump of giant spheres in an empty view.
    // Hiding removes points; it does not change how big a point is.
    const pointRadius = useMemo(() => autoPointRadius(visiblePoints.length), [visiblePoints]);

    const pointBuffers = useMemo(
      () =>
        buildPointBuffers(renderedPoints, {
          colorFor: tagScale.colorFor,
          scaleFactor,
          backgroundColor: BACKGROUNDS[themeMode],
          isolatedTag,
          selectedId,
          connectedIds,
        }),
      [renderedPoints, tagScale, scaleFactor, themeMode, isolatedTag, selectedId, connectedIds],
    );
    const ghostBuffers = useMemo(
      () =>
        ghostPoints.length > 0
          ? buildPointBuffers(ghostPoints, {
              colorFor: () => GHOST_COLOR[themeMode],
              scaleFactor,
              backgroundColor: BACKGROUNDS[themeMode],
              isolatedTag: null,
              selectedId: null,
              connectedIds: NO_CONNECTIONS,
            })
          : null,
      [ghostPoints, scaleFactor, themeMode],
    );
    const edgeBuffers = useMemo(
      () => buildEdgeBuffers(chain, byId, layers, pointBuffers),
      [chain, byId, layers, pointBuffers],
    );

    const handleSelect = useCallback((id: string) => {
      setChain([id]);
    }, []);
    const handleExpand = useCallback(
      (id: string) => {
        setChain((prev) => {
          if (prev.includes(id)) {
            return prev;
          }
          // Expanding only makes sense from an existing neighbourhood; a
          // double-click elsewhere starts a fresh path.
          return connectedIds.has(id) ? [...prev, id] : [id];
        });
      },
      [connectedIds],
    );
    const handleClearSelection = useCallback(() => setChain([]), []);
    /** The panel knows the note by id; the Related search wants its text. */
    const handleShowRelated = useCallback(
      (id: string) => {
        const note = searchResults.find((candidate) => candidate.id === id);
        if (note) {
          onShowRelated(`${note.title} ${note.content}`);
        }
      },
      [searchResults, onShowRelated],
    );
    const handleToggleLayer = useCallback(
      (kind: keyof LayerToggles) => setLayers((prev) => ({ ...prev, [kind]: !prev[kind] })),
      [],
    );

    const toggleFullscreen = useCallback(() => {
      if (!containerRef.current) {
        return;
      }
      if (!document.fullscreenElement) {
        containerRef.current
          .requestFullscreen()
          .then(() => setIsFullscreen(true))
          .catch(() => setIsFullscreen(false));
      } else {
        document
          .exitFullscreen()
          .then(() => setIsFullscreen(false))
          .catch(() => undefined);
      }
    }, []);

    const selectedPoint = useMemo(() => {
      if (selectedId === null) {
        return null;
      }
      return embeddings.find((p) => p.id === selectedId) ?? null;
    }, [embeddings, selectedId]);
    const chainTitles = useMemo(
      () =>
        chain.map((id) => {
          const p = embeddings.find((e) => e.id === id);
          return p?.title || 'Untitled';
        }),
      [chain, embeddings],
    );
    const hoveredPoint = useMemo(() => {
      if (!hover?.pointId) {
        return null;
      }
      return visiblePoints.find((p) => p.id === hover.pointId) ?? null;
    }, [hover, visiblePoints]);

    // Split out of the JSX: `a ? b ?? null : null` is formatted differently by the
    // repo's two prettier versions (pre-commit strips the parens the client's
    // eslint-prettier then demands), so the two gates fight over the file forever.
    const selectedConnections = selectedId === null ? undefined : byId[selectedId];
    const selectedConnectionsError = selectedId === null ? undefined : errors[selectedId];

    if (error) {
      return <div className="visualization-empty">Error loading visualization: {error}</div>;
    }
    if (isLoading) {
      return <div className="visualization-loading">Loading visualization...</div>;
    }
    if (embeddings.length === 0) {
      return <div className="visualization-empty">No embeddings available for visualization.</div>;
    }
    if (visiblePoints.length === 0) {
      return (
        <div className="visualization-empty">No points match the current filter criteria.</div>
      );
    }

    return (
      <div className="visualization-wrapper">
        <div
          className={`visualization-container ${hover?.pointId ? 'point-hover' : ''}`}
          ref={containerRef}
        >
          <button className="fullscreen-toggle" onClick={toggleFullscreen}>
            <span className="material-icons">
              {isFullscreen ? 'fullscreen_exit' : 'fullscreen'}
            </span>
          </button>

          <Scene
            points={pointBuffers}
            ghost={ghostBuffers}
            edges={edgeBuffers}
            isDark={themeMode === 'dark'}
            pointRadius={pointRadius}
            onHover={setHover}
            onSelect={handleSelect}
            onExpand={handleExpand}
            onClearSelection={handleClearSelection}
          />

          {hover && (hoveredPoint || hover.edge) && (
            <div className="viz-tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
              {hoveredPoint && (
                <>
                  <strong>{hoveredPoint.title || hoveredPoint.snippet || 'Untitled'}</strong>
                  {scoreById.has(hoveredPoint.id) && (
                    <div>{scoreById.get(hoveredPoint.id)}% match</div>
                  )}
                  {hoveredPoint.tags.length > 0 && <div>[{hoveredPoint.tags.join(', ')}]</div>}
                </>
              )}
              {hover.edge && <strong>{hover.edge.label}</strong>}
            </div>
          )}

          <SidePanel
            selected={selectedPoint}
            chainTitles={chainTitles}
            connections={selectedConnections ?? null}
            connectionsError={selectedConnectionsError ?? null}
            connectionsLoading={connectionsLoading}
            layers={layers}
            onToggleLayer={handleToggleLayer}
            legend={tagScale.legend}
            isolatedTag={isolatedTag}
            onIsolateTag={setIsolatedTag}
            allTags={allTags}
            ghost={ghost}
            canGhost={canGhost}
            onToggleGhost={() => setGhost((g) => !g)}
            hideUnfocused={hideUnfocused}
            onToggleHideUnfocused={() => setHideUnfocused((h) => !h)}
            onShowRelated={handleShowRelated}
            onClearPath={() => setChain(chain.slice(0, 1))}
          />
        </div>
      </div>
    );
  },
);
