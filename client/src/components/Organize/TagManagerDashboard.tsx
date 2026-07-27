import { memo, useMemo, useState } from 'react';

import { Tag } from '@/types';

import { TagManagementCard } from './TagManagementCard';
import { SORT_LABELS, TagSort, sortTags } from './tagSort';

interface TagManagerDashboardProps {
  tags: Tag[];
  isLoading: boolean;
  onRename: (oldName: string, newName: string) => void;
  onMerge: (sourceTag: string, targetTag: string) => void;
  onRemove: (tagName: string) => void;
}

export const TagManagerDashboard = memo(
  ({ tags, isLoading, onRename, onMerge, onRemove }: TagManagerDashboardProps) => {
    const [sort, setSort] = useState<TagSort>('count-desc');
    const sortedTags = useMemo(() => sortTags(tags, sort), [tags, sort]);

    if (isLoading) {
      return <div className="tag-manager-loading">Loading tags...</div>;
    }

    if (tags.length === 0) {
      return (
        <div className="tag-manager-empty">
          <span className="material-icons">sell</span>
          <p>No tags yet. Use Smart Tags above or tag notes from Search and All Notes.</p>
        </div>
      );
    }

    const totalNotes = tags.reduce((sum, tag) => sum + tag.count, 0);

    return (
      <div className="proposal-dashboard">
        <div className="dashboard-header">
          <div className="dashboard-stats">
            <span className="stat">
              <span className="material-icons">sell</span>
              {tags.length} tag{tags.length === 1 ? '' : 's'}
            </span>
            <span className="stat">
              <span className="material-icons">description</span>
              {totalNotes} assignment{totalNotes === 1 ? '' : 's'}
            </span>
          </div>
          <label className="tag-sort">
            <span className="material-icons">sort</span>
            <span className="tag-sort-label">Sort</span>
            <select
              className="tag-sort-select"
              value={sort}
              onChange={(e) => setSort(e.target.value as TagSort)}
              aria-label="Sort tags"
            >
              {(Object.keys(SORT_LABELS) as TagSort[]).map((key) => (
                <option key={key} value={key}>
                  {SORT_LABELS[key]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="proposals-list">
          {sortedTags.map((tag) => (
            <TagManagementCard
              key={tag.name}
              tag={tag}
              allTags={tags}
              onRename={onRename}
              onMerge={onMerge}
              onRemove={onRemove}
            />
          ))}
        </div>
      </div>
    );
  },
);
