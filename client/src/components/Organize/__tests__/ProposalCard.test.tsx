import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ProposalState, TagProposal } from '@/types';

import { ProposalCard } from '../ProposalCard';

const wrap = (proposal: TagProposal): ProposalState => ({ proposal, action: 'pending' });

const noop = () => {};

const renderCard = (proposal: TagProposal, handlers: Partial<Record<string, unknown>> = {}) =>
  render(
    <ProposalCard
      state={wrap(proposal)}
      index={0}
      allProposals={[wrap(proposal)]}
      onApprove={(handlers.onApprove as never) ?? noop}
      onReject={(handlers.onReject as never) ?? noop}
      onRename={noop}
      onMerge={noop}
    />,
  );

describe('ProposalCard proposal types', () => {
  it('renders an info card with no action buttons', () => {
    renderCard({ type: 'info', message: "Auto-merged 'Gym' into 'Fitness'" });
    expect(screen.getByText("Auto-merged 'Gym' into 'Fitness'")).toBeInTheDocument();
    expect(screen.queryByTitle('Approve')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Reject')).not.toBeInTheDocument();
  });

  it('names the two merge outcomes instead of showing a bare check and cross', () => {
    const onApprove = vi.fn();
    renderCard(
      {
        type: 'proposal',
        action: 'merge_tags',
        source_tag: 'Gym',
        target_tag: 'Fitness',
        note_count: 12,
        confidence: 0.7,
      },
      { onApprove },
    );

    expect(screen.getByText('Merge ‘Gym’ into ‘Fitness’?')).toBeInTheDocument();
    // No rename button for merge proposals.
    expect(screen.queryByTitle('Rename')).not.toBeInTheDocument();

    // The outcomes are spelled out. With a bare check and cross, "reject" reads as
    // *discard these tags* when it means *keep them as two separate tags* — the reason
    // rejecting a merge felt destructive.
    expect(screen.getByTitle('Merge')).toBeInTheDocument();
    expect(screen.getByTitle('Keep separate')).toBeInTheDocument();
    expect(screen.queryByTitle('Approve')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Reject')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Merge'));
    expect(onApprove).toHaveBeenCalledWith(0);
  });

  it('renders a review assignment proposal with approve/reject', () => {
    const onReject = vi.fn();
    renderCard(
      {
        type: 'proposal',
        action: 'assign_tag',
        note_id: 'n1',
        tag: 'Travel',
        note_title: 'Kyoto trip',
        confidence: 0.42,
      },
      { onReject },
    );

    expect(screen.getByText(/suggest #Travel/)).toBeInTheDocument();
    expect(screen.getByText(/Kyoto trip/)).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Reject'));
    expect(onReject).toHaveBeenCalledWith(0);
  });

  it('still renders a classic cluster tag with rename + preview controls', () => {
    renderCard({
      tag_name: 'Cooking',
      note_ids: ['a', 'b'],
      note_count: 2,
      sample_notes: [{ id: 'a', title: 'Pasta', content: 'boil water' }],
      confidence: 0.9,
    });

    expect(screen.getByText('Cooking')).toBeInTheDocument();
    expect(screen.getByTitle('Rename')).toBeInTheDocument();
    expect(screen.getByText(/Preview/)).toBeInTheDocument();
  });
});
