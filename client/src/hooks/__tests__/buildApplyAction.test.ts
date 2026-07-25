import { describe, expect, it } from 'vitest';

import { ProposalState, TagProposal } from '@/types';

import { buildApplyAction } from '../useOrganize';

const state = (
  proposal: TagProposal,
  action: ProposalState['action'],
  newName?: string,
  mergeTarget?: string,
): ProposalState => ({
  proposal,
  action,
  newName,
  mergeTarget,
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

  it('tags a classic merge with the target name, never with its own name', () => {
    // Regression for B8, both halves. First the Merge button dropped mergeTarget and
    // tagged the notes with their own name (behaved as approve). Then the fix emitted
    // merge_tags for a source tag that was never applied, so the backend raised KeyError
    // and skipped it — the notes ended up with no tag at all. Merging a proposal means
    // tagging its notes with the target name.
    const payload = buildApplyAction(
      state({ tag_name: 'Gym', note_ids: ['a', 'b'] }, 'merge', undefined, 'Fitness'),
    );
    expect(payload).toEqual({
      action: 'approve',
      tag_name: 'Fitness',
      note_ids: ['a', 'b'],
    });
    expect(payload?.tag_name).not.toBe('Gym');
    expect(payload?.action).not.toBe('merge');
    // merge_tags is for gray-zone proposals, where both tags are already on disk.
    expect(payload?.action).not.toBe('merge_tags');
  });

  it('drops a classic merge with no staged mergeTarget instead of falling back to approve', () => {
    expect(
      buildApplyAction(state({ tag_name: 'Gym', note_ids: ['a'] }, 'merge', undefined, undefined)),
    ).toBeNull();
  });

  it('treats a self-merge as a plain approve of that tag', () => {
    const payload = buildApplyAction(
      state({ tag_name: 'Gym', note_ids: ['a'] }, 'merge', undefined, 'Gym'),
    );
    expect(payload).toEqual({ action: 'approve', tag_name: 'Gym', note_ids: ['a'] });
  });
});
