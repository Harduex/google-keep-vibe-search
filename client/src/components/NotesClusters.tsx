import { memo, useState, useCallback } from 'react';

import { useClusters } from '@/hooks/useClusters';
import { useTags } from '@/hooks/useTags';

import { NoteCard } from './NoteCard';

interface NotesClusterProps {
  onShowRelated: (content: string) => void;
  query: string;
}

const ClusterHeader = memo(
  ({
    cluster,
    expandedCluster,
    toggleClusterExpansion,
  }: {
    cluster: { id: number; size: number; keywords: string[] };
    expandedCluster: number | null;
    toggleClusterExpansion: (clusterId: number) => void;
  }) => {
    const handleClusterClick = useCallback(() => {
      toggleClusterExpansion(cluster.id);
    }, [cluster.id, toggleClusterExpansion]);

    return (
      <div className="cluster-header" onClick={handleClusterClick}>
        <h2>
          Cluster {cluster.id + 1}: {cluster.size} notes
          <span className="material-icons">
            {expandedCluster === cluster.id ? 'expand_less' : 'expand_more'}
          </span>
        </h2>
        <div className="cluster-keywords">
          {cluster.keywords.map((keyword, index) => (
            <span key={index} className="cluster-keyword">
              {keyword}
            </span>
          ))}
        </div>
      </div>
    );
  },
);

export const NotesClusters = memo(({ onShowRelated, query }: NotesClusterProps) => {
  const [expandedCluster, setExpandedCluster] = useState<number | null>(null);
  const [pendingClusters, setPendingClusters] = useState(2);
  const { clusters, isLoading, error, fetchClusters } = useClusters();
  const { removeTagFromNote } = useTags();

  const toggleClusterExpansion = useCallback(
    (clusterId: number) => {
      setExpandedCluster(expandedCluster === clusterId ? null : clusterId);
    },
    [expandedCluster],
  );

  const handleNumClustersChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setPendingClusters(parseInt(e.target.value));
  }, []);

  const handleGenerateClusters = useCallback(() => {
    fetchClusters(pendingClusters);
  }, [pendingClusters, fetchClusters]);

  return (
    <div className="clusters-container">
      <div className="clusters-header">
        <div className="cluster-slider">
          <label htmlFor="cluster-count">Number of clusters: {pendingClusters}</label>
          <input
            id="cluster-count"
            type="range"
            min="2"
            max="100"
            value={pendingClusters}
            onChange={handleNumClustersChange}
            className="slider"
          />
          <div className="clusters-help-text">
            More clusters = smaller, more specific groups of notes
          </div>
        </div>
        <button
          className="generate-clusters-button"
          onClick={handleGenerateClusters}
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <span className="material-icons spinning">refresh</span>
              Generating...
            </>
          ) : (
            <>
              <span className="material-icons">auto_awesome</span>
              Generate Clusters
            </>
          )}
        </button>
      </div>

      {isLoading && (
        <div className="clusters-loading">
          <span className="material-icons spinning">refresh</span>
          Generating {pendingClusters} clusters...
        </div>
      )}

      {error && <div className="clusters-error">Error: {error}</div>}

      {!isLoading && !error && clusters.length === 0 && (
        <div className="clusters-empty">No clusters available.</div>
      )}

      {!isLoading &&
        !error &&
        clusters.length > 0 &&
        clusters.map((cluster) => (
          <div key={cluster.id} className="cluster-group">
            <ClusterHeader
              cluster={cluster}
              expandedCluster={expandedCluster}
              toggleClusterExpansion={toggleClusterExpansion}
            />

            <div className={`cluster-notes ${expandedCluster === cluster.id ? 'expanded' : ''}`}>
              {expandedCluster === cluster.id &&
                cluster.notes.map((note) => (
                  <div key={note.id}>
                    <NoteCard
                      note={note}
                      query={query}
                      onShowRelated={onShowRelated}
                      onRemoveTag={removeTagFromNote}
                    />
                  </div>
                ))}

              {expandedCluster !== cluster.id && (
                <div className="cluster-preview">
                  {cluster.notes.slice(0, 3).map((note) => (
                    <div key={note.id} className="note-preview">
                      {note.title || note.content.substring(0, 100)}
                    </div>
                  ))}
                  {cluster.size > 3 && (
                    <div className="more-notes">+ {cluster.size - 3} more notes</div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
    </div>
  );
});
