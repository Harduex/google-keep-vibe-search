import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';

import { API_ROUTES } from '@/const';

import { useOrganize } from '../useOrganize';

const originalFetch = global.fetch;

// Two clusters that independently landed on the same display name — the regression this
// suite targets. Distinct proposal_id is the only thing that tells them apart.
const topicProposal = (proposal_id: string) => ({
  tag_name: 'Topic',
  proposal_id,
  note_ids: [],
  note_count: 1,
  sample_notes: [],
  confidence: 0.5,
});

describe('useOrganize duplicate tag names (proposal identity)', () => {
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('approves the card by proposal_id, not the first same-named card', async () => {
    global.fetch = vi.fn((input: any, options?: any) => {
      if (input === API_ROUTES.ORGANIZE_PENDING && !options) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              proposals: [topicProposal('a'), topicProposal('b')],
              actions: {},
              generated_at: 1700000000,
            }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }) as any;

    const { result } = renderHook(() => useOrganize());
    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.proposals).toHaveLength(2);

    act(() => {
      result.current.approveProposal('b');
    });

    const a = result.current.proposals.find((p) => p.proposal.proposal_id === 'a');
    const b = result.current.proposals.find((p) => p.proposal.proposal_id === 'b');
    expect(b?.action).toBe('approve');
    expect(a?.action).toBe('pending');
  });

  it('assigns distinct synthetic ids to a restored set with no proposal_id, and stages only the targeted card', async () => {
    global.fetch = vi.fn((input: any, options?: any) => {
      if (input === API_ROUTES.ORGANIZE_PENDING && !options) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              proposals: [
                {
                  tag_name: 'Topic',
                  note_ids: [],
                  note_count: 1,
                  sample_notes: [],
                  confidence: 0.5,
                },
                {
                  tag_name: 'Topic',
                  note_ids: [],
                  note_count: 1,
                  sample_notes: [],
                  confidence: 0.5,
                },
              ],
              actions: {},
              generated_at: 1700000000,
            }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }) as any;

    const { result } = renderHook(() => useOrganize());
    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.proposals).toHaveLength(2);
    const ids = result.current.proposals.map((p) => p.proposal.proposal_id);
    expect(ids[0]).toBeTruthy();
    expect(ids[1]).toBeTruthy();
    expect(ids[0]).not.toBe(ids[1]);

    const secondId = ids[1] as string;
    act(() => {
      result.current.approveProposal(secondId);
    });

    expect(result.current.proposals[1].action).toBe('approve');
    expect(result.current.proposals[0].action).toBe('pending');
  });

  it('PUTs the staged action to /pending/actions keyed by tag name (server contract unchanged)', async () => {
    vi.useFakeTimers();
    const putCalls: any[] = [];
    global.fetch = vi.fn((input: any, options?: any) => {
      if (input === API_ROUTES.ORGANIZE_PENDING && !options) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              proposals: [topicProposal('a'), topicProposal('b')],
              actions: {},
              generated_at: 1700000000,
            }),
        } as Response);
      }
      if (typeof input === 'string' && input.endsWith('/actions') && options?.method === 'PUT') {
        putCalls.push(JSON.parse(options.body));
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }) as any;

    const { result } = renderHook(() => useOrganize());
    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      result.current.approveProposal('b');
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(putCalls.length).toBeGreaterThan(0);
    const last = putCalls[putCalls.length - 1];
    // Two cards share the display name "Topic", but only one is non-pending, so the
    // name-keyed body is unambiguous — the server's contract does not change.
    expect(last.actions).toEqual({ Topic: 'approve' });
  });
});
