import { describe, expect, it } from 'vitest';

import { ProposalState, TagProposal } from '@/types';

import { buildApplyAction } from '../useOrganize';

const state = (
  proposal: TagProposal,
  action: ProposalState['action'],
  newName?: string,
): ProposalState => ({
  proposal,
  action,
  newName,
});

describe('buildApplyAction', () => {
  it('returns null for pending, rejected, and info proposals', () => {
    expect(buildApplyAction(state({ tag_name: 'X', note_ids: ['a'] }, 'pending'))).toBeNull();
    expect(buildApplyAction(state({ tag_name: 'X', note_ids: ['a'] }, 'reject'))).toBeNull();
    expect(buildApplyAction(state({ type: 'info', message: 'auto' }, 'approve'))).toBeNull();
  });

  it('maps an approved gray-zone merge to a merge_tags payload', () => {
    const payload = buildApplyAction(
      state(
        { type: 'proposal', action: 'merge_tags', source_tag: 'Gym', target_tag: 'Fitness' },
        'approve',
      ),
    );
    expect(payload).toEqual({ action: 'merge_tags', source_tag: 'Gym', target_tag: 'Fitness' });
  });

  it('maps an approved review assignment to an assign_tag payload', () => {
    const payload = buildApplyAction(
      state({ type: 'proposal', action: 'assign_tag', note_id: 'n1', tag: 'Travel' }, 'approve'),
    );
    expect(payload).toEqual({ action: 'assign_tag', note_id: 'n1', tag: 'Travel' });
  });

  it('maps a classic approve and rename to the existing payload shape', () => {
    expect(
      buildApplyAction(state({ tag_name: 'Cooking', note_ids: ['a', 'b'] }, 'approve')),
    ).toEqual({
      action: 'approve',
      tag_name: 'Cooking',
      note_ids: ['a', 'b'],
      new_name: undefined,
    });

    expect(
      buildApplyAction(state({ tag_name: 'Cook', note_ids: ['a'] }, 'rename', 'Cooking')),
    ).toEqual({
      action: 'rename',
      tag_name: 'Cook',
      note_ids: ['a'],
      new_name: 'Cooking',
    });
  });
});
