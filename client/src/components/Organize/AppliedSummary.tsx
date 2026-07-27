import { memo } from 'react';

import { ProposalState } from '@/types';

interface AppliedSummaryProps {
  applied: ProposalState[];
}

/**
 * What the last apply wrote.
 *
 * Applying used to empty the review list and show nothing in its place, so a successful
 * apply was indistinguishable from losing the run — after minutes of LLM naming and a
 * screen of decisions, the panel simply went blank. The tags were on disk and visible in
 * the Tag Manager below, but nothing connected the two.
 *
 * Read-only by design: these are no longer decisions, they are a receipt. It clears when
 * the next run starts.
 */
export const AppliedSummary = memo(({ applied }: AppliedSummaryProps) => {
  if (applied.length === 0) {
    return null;
  }

  const tagNames = applied
    .map((s) => s.newName || s.proposal.tag_name || s.proposal.target_tag)
    .filter((name): name is string => Boolean(name));
  const noteCount = applied.reduce((sum, s) => sum + (s.proposal.note_count || 0), 0);

  return (
    <div className="applied-summary">
      <div className="applied-summary-header">
        <span className="material-icons">check_circle</span>
        <span>
          Applied {tagNames.length} tag{tagNames.length === 1 ? '' : 's'}
          {noteCount > 0 && ` across ${noteCount} note assignments`}
        </span>
      </div>
      <div className="applied-summary-tags">
        {tagNames.map((name) => (
          <span className="applied-summary-tag" key={name}>
            {name}
          </span>
        ))}
      </div>
      <p className="applied-summary-hint">
        These are live now — rename, merge or remove them in the Tag Manager below. Starting another
        run replaces this summary.
      </p>
    </div>
  );
});
