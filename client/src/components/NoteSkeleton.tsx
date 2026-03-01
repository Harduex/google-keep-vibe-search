import { memo } from 'react';

interface NoteSkeletonProps {
  count?: number;
  /**
   * Layout to use when rendering skeleton items. Grid matches the
   * standard search/results view; list mirrors the vertical list used
   * by the All Notes screen. Defaults to grid for backwards
   * compatibility.
   */
  layout?: 'grid' | 'list';
}

export const NoteSkeleton = memo(({ count = 6, layout = 'grid' }: NoteSkeletonProps) => (
  <div className={layout === 'grid' ? 'skeleton-grid' : 'skeleton-list'}>
    {Array.from({ length: count }, (_, i) => (
      <div key={i} className="skeleton-card">
        <div className="skeleton-line skeleton-title" />
        <div className="skeleton-line skeleton-text" />
        <div className="skeleton-line skeleton-text short" />
        <div className="skeleton-line skeleton-meta" />
      </div>
    ))}
  </div>
));
