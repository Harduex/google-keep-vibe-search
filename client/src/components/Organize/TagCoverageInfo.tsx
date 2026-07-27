import { memo } from 'react';

import { TagCoverage } from '@/types';

interface TagCoverageInfoProps {
  coverage: TagCoverage | null;
  isLoading: boolean;
}

/**
 * Corpus-level tagging state, above both dashboards: how much of the library is tagged and
 * how much is still untouched. The per-tag counts already on the cards answer "how big is
 * this tag"; this answers "how far along am I", which nothing else did.
 */
export const TagCoverageInfo = memo(({ coverage, isLoading }: TagCoverageInfoProps) => {
  if (isLoading || !coverage) {
    return <div className="tag-coverage-loading">Loading tag stats...</div>;
  }

  const items = [
    { icon: 'description', label: 'Notes', value: coverage.total_notes },
    { icon: 'label', label: 'Tagged', value: `${coverage.tagged_notes} (${coverage.tagged_pct}%)` },
    { icon: 'label_off', label: 'Untagged', value: coverage.untagged_notes },
    { icon: 'sell', label: 'Distinct tags', value: coverage.distinct_tags },
    { icon: 'link', label: 'Assignments', value: coverage.assignments },
    {
      icon: 'functions',
      label: 'Tags per tagged note',
      value: coverage.avg_tags_per_tagged_note,
    },
  ];

  return (
    <div className="tag-coverage">
      {items.map((item) => (
        <div className="coverage-item" key={item.label}>
          <span className="material-icons">{item.icon}</span>
          <span className="coverage-value">{item.value}</span>
          <span className="coverage-label">{item.label}</span>
        </div>
      ))}
      {coverage.excluded_tags > 0 && (
        <div className="coverage-item" key="excluded">
          <span className="material-icons">visibility_off</span>
          <span className="coverage-value">{coverage.excluded_tags}</span>
          <span className="coverage-label">Excluded from search</span>
        </div>
      )}
    </div>
  );
});
