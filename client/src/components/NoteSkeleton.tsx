import { memo } from 'react';

interface NoteSkeletonProps {
  count?: number;
}

export const NoteSkeleton = memo(({ count = 6 }: NoteSkeletonProps) => (
  <div className="skeleton-grid">
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
