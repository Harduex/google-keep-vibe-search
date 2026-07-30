import { EmbeddingPoint } from '@/hooks/useEmbeddings';

import { EDGE_COLORS, LayerToggles } from './sceneData';
import { TagLegendEntry } from './tagColors';
import { NoteConnections } from './useConnections';

export interface SidePanelProps {
  selected: EmbeddingPoint | null;
  chainTitles: string[];
  connections: NoteConnections | null;
  connectionsError: string | null;
  connectionsLoading: boolean;
  layers: LayerToggles;
  onToggleLayer: (kind: keyof LayerToggles) => void;
  legend: TagLegendEntry[];
  isolatedTag: string | null;
  onIsolateTag: (tag: string | null) => void;
  allTags: string[];
  ghost: boolean;
  /** Whether the current filter excludes anything. With nothing excluded there is
   *  nothing to ghost, so the toggle is offered but inert. */
  canGhost: boolean;
  onToggleGhost: () => void;
  hideUnfocused: boolean;
  onToggleHideUnfocused: () => void;
  /** Search for notes related to this one — same gesture as the card's Related button. */
  onShowRelated: (id: string) => void;
  onClearPath: () => void;
}

const LAYER_ROWS: {
  kind: keyof LayerToggles;
  label: string;
  count: (c: NoteConnections) => number;
}[] = [
  { kind: 'similar', label: 'Similar', count: (c) => c.similar.length },
  {
    kind: 'tags',
    label: 'Shared tags',
    count: (c) => c.shared_tags.reduce((n, g) => n + g.notes.length, 0),
  },
  {
    kind: 'entities',
    label: 'Shared entities',
    count: (c) => c.shared_entities.reduce((n, g) => n + g.notes.length, 0),
  },
];

/** What "everything else" currently means — selection outranks tag isolation, the
 *  same precedence the fade and the render filter use. */
const focusHint = (selected: EmbeddingPoint | null, isolatedTag: string | null): string => {
  if (selected !== null) {
    return 'Showing only this note and its connections.';
  }
  if (isolatedTag !== null) {
    return `Showing only notes tagged ${isolatedTag}.`;
  }
  return 'Select a note or isolate a tag first.';
};

export const SidePanel = ({
  selected,
  chainTitles,
  connections,
  connectionsError,
  connectionsLoading,
  layers,
  onToggleLayer,
  legend,
  isolatedTag,
  onIsolateTag,
  allTags,
  ghost,
  canGhost,
  onToggleGhost,
  hideUnfocused,
  onToggleHideUnfocused,
  onShowRelated,
  onClearPath,
}: SidePanelProps) => (
  <aside className="viz-side-panel">
    <section className="viz-panel-section">
      <h4>Tags</h4>
      <ul className="viz-tag-legend" aria-label="Point colours by tag">
        {legend.map((entry) => {
          const isSlotTag = entry.label !== 'Other tags' && entry.label !== 'Untagged';
          return (
            <li key={entry.label}>
              {isSlotTag ? (
                <button
                  className={`viz-legend-item ${isolatedTag === entry.label ? 'isolated' : ''}`}
                  onClick={() => onIsolateTag(isolatedTag === entry.label ? null : entry.label)}
                >
                  <span className="viz-tag-swatch" style={{ backgroundColor: entry.color }} />
                  {entry.label}
                </button>
              ) : (
                <span className="viz-legend-item">
                  <span className="viz-tag-swatch" style={{ backgroundColor: entry.color }} />
                  {entry.label}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      <input
        type="search"
        className="viz-tag-picker"
        placeholder="Isolate any tag…"
        list="viz-all-tags"
        value={isolatedTag ?? ''}
        onChange={(e) => onIsolateTag(allTags.includes(e.target.value) ? e.target.value : null)}
        aria-label="Isolate any tag"
      />
      <datalist id="viz-all-tags">
        {allTags.map((tag) => (
          <option key={tag} value={tag} />
        ))}
      </datalist>
    </section>

    <section className="viz-panel-section">
      <h4>View</h4>
      <label className="viz-control-row">
        <input type="checkbox" checked={ghost} onChange={onToggleGhost} disabled={!canGhost} />
        Ghost filtered-out notes
      </label>
      <label className="viz-control-row">
        <input
          type="checkbox"
          checked={hideUnfocused}
          onChange={onToggleHideUnfocused}
          disabled={selected === null && isolatedTag === null}
        />
        Hide everything else
      </label>
      {hideUnfocused && <p className="viz-muted">{focusHint(selected, isolatedTag)}</p>}
    </section>

    {selected && (
      <section className="viz-panel-section viz-selection">
        <h4>{selected.title || 'Untitled note'}</h4>
        {selected.snippet && <p className="viz-snippet">{selected.snippet}</p>}
        {selected.tags.length > 0 && (
          <p className="viz-selected-tags">{selected.tags.join(', ')}</p>
        )}
        {/* Same class as the note card's Related button, so the two gestures look alike. */}
        <button className="show-related-button" onClick={() => onShowRelated(selected.id)}>
          <span className="material-icons">layers</span> Show related
        </button>

        {connectionsError && <p className="viz-error">Connections failed: {connectionsError}</p>}
        {connectionsLoading && <p className="viz-muted">Loading connections…</p>}

        <h5>Connections</h5>
        {LAYER_ROWS.map(({ kind, label, count }) => (
          <label key={kind} className="viz-control-row">
            <input
              type="checkbox"
              checked={layers[kind]}
              onChange={() => onToggleLayer(kind)}
              aria-label={`${label} (${connections ? count(connections) : 0})`}
            />
            <span className="viz-edge-swatch" style={{ backgroundColor: EDGE_COLORS[kind] }} />
            {label} ({connections ? count(connections) : 0})
          </label>
        ))}

        {chainTitles.length > 1 && (
          <>
            <h5>Path</h5>
            <p className="viz-breadcrumb">{chainTitles.join(' → ')}</p>
            <button onClick={onClearPath}>Clear path</button>
          </>
        )}
        <p className="viz-muted">Double-click a connected note to extend the path.</p>
      </section>
    )}
  </aside>
);
