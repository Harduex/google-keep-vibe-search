import { memo, useEffect, useState } from 'react';
import { useClusters } from '@/hooks/useClusters';
import { NoteCard } from './NoteCard';

interface NotesClustersProps {
  onShowRelated: (content: string) => void;
  query: string;
}

export const NotesClusters = memo(({ onShowRelated, query }: NotesClustersProps) => {
  const [expandedCluster, setExpandedCluster] = useState<number | null>(null);
  const { clusters, isLoading, error, fetchClusters } = useClusters();

  useEffect(() => {
    fetchClusters();
  }, [fetchClusters]);

  const toggleClusterExpansion = (clusterId: number) => {
    setExpandedCluster(expandedCluster === clusterId ? null : clusterId);
  };

  return (
    <div className="clusters-container">

      {/* show number of clusters */}
      <div className="clusters-header">
        <h2>Clusters</h2>
        <span className="clusters-count">{clusters.length}</span>
      </div>

      {isLoading && (
        <div className="clusters-loading">Generating clusters...</div>
      )}
      
      {error && (
        <div className="clusters-error">Error: {error}</div>
      )}
      
      {!isLoading && !error && clusters.length === 0 && (
        <div className="clusters-empty">No clusters available.</div>
      )}

      {!isLoading && !error && clusters.length > 0 && clusters.map((cluster) => (
        <div key={cluster.id} className="cluster-group">
          <div className="cluster-header" onClick={() => toggleClusterExpansion(cluster.id)}>
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

          <div className={`cluster-notes ${expandedCluster === cluster.id ? 'expanded' : ''}`}>
            {expandedCluster === cluster.id &&
              cluster.notes.map((note) => (
                <div key={note.id}>
                  <NoteCard note={note} query={query} onShowRelated={onShowRelated} />
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

NotesClusters.displayName = 'NotesClusters';
