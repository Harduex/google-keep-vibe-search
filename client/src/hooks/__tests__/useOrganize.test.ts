import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { API_ROUTES } from '@/const';

import { useOrganize } from '../useOrganize';

const originalFetch = global.fetch;

describe('useOrganize NDJSON stream parser', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response),
    );
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  const encodeChunk = (str: string) => new TextEncoder().encode(str);

  const createStreamResponse = (chunks: Uint8Array[]) => {
    const stream = new ReadableStream({
      start(controller) {
        chunks.forEach((c) => controller.enqueue(c));
        controller.close();
      },
    });
    return Promise.resolve({
      ok: true,
      body: stream,
    } as Response);
  };

  it('handles chunk-boundary safety with split JSON objects', async () => {
    const { result } = renderHook(() => useOrganize());

    const jsonStr =
      JSON.stringify({
        type: 'progress',
        stage: 'clustering',
        progress: 50,
        message: 'Processing',
      }) + '\n';
    const splitIndex = 20;
    const chunk1 = encodeChunk(jsonStr.slice(0, splitIndex));
    const chunk2 = encodeChunk(jsonStr.slice(splitIndex));

    (global.fetch as any).mockImplementation((input: string) => {
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        return createStreamResponse([chunk1, chunk2]);
      }
      return Promise.resolve({ ok: true });
    });

    await act(async () => {
      await result.current.startCategorization();
    });

    expect(result.current.progress).toEqual({
      stage: 'clustering',
      message: 'Processing',
      progress: 50,
      current: undefined,
      total: undefined,
    });
  });

  it('handles chunk boundary mid-multi-byte-UTF-8 character', async () => {
    const { result } = renderHook(() => useOrganize());

    const baseJson = '{"type":"progress","message":"Тест"}\n';
    const tIndex = baseJson.indexOf('Т');
    const prefixBytes = new TextEncoder().encode(baseJson.slice(0, tIndex));
    const chunk1 = new Uint8Array([...prefixBytes, 0xd0]);
    const chunk2 = new Uint8Array([0xa2, ...new TextEncoder().encode(baseJson.slice(tIndex + 1))]);

    (global.fetch as any).mockImplementation((input: string) => {
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        return createStreamResponse([chunk1, chunk2]);
      }
      return Promise.resolve({ ok: true });
    });

    await act(async () => {
      await result.current.startCategorization();
    });

    expect(result.current.progress?.message).toBe('Тест');
  });

  it('replaces rather than appends proposals when receiving label_updates after proposals', async () => {
    const { result } = renderHook(() => useOrganize());

    const streamData =
      JSON.stringify({ type: 'proposals', proposals: [{ tag_name: 'P1' }] }) +
      '\n' +
      JSON.stringify({ type: 'label_updates', proposals: [{ tag_name: 'P2' }] }) +
      '\n';

    (global.fetch as any).mockImplementation((input: string) => {
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        return createStreamResponse([encodeChunk(streamData)]);
      }
      return Promise.resolve({ ok: true });
    });

    await act(async () => {
      await result.current.startCategorization();
    });

    expect(result.current.proposals).toHaveLength(1);
    expect(result.current.proposals[0].proposal.tag_name).toBe('P2');
  });

  it('cancel aborts the stream properly', async () => {
    const { result } = renderHook(() => useOrganize());

    let streamController: ReadableStreamDefaultController;
    const stream = new ReadableStream({
      start(controller) {
        streamController = controller;
      },
    });

    (global.fetch as any).mockImplementation((input: string, options?: any) => {
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        if (options?.signal) {
          options.signal.addEventListener('abort', () => {
            try {
              streamController?.error(new DOMException('Aborted', 'AbortError'));
            } catch {
              /* ignore */
            }
          });
        }
        return Promise.resolve({ ok: true, body: stream } as Response);
      }
      return Promise.resolve({ ok: true });
    });

    let startPromise: Promise<void>;
    act(() => {
      startPromise = result.current.startCategorization();
    });

    await act(async () => {
      streamController.enqueue(
        encodeChunk(JSON.stringify({ type: 'progress', message: 'started' }) + '\n'),
      );
    });

    expect(result.current.isProcessing).toBe(true);

    await act(async () => {
      result.current.cancelCategorization();
    });

    expect(result.current.isProcessing).toBe(false);

    await act(async () => {
      await startPromise;
    });
  });

  it('skips a malformed line without killing the stream', async () => {
    const { result } = renderHook(() => useOrganize());

    const streamData =
      JSON.stringify({ type: 'progress', stage: 'start' }) +
      '\n' +
      '{ malformed json \n' +
      JSON.stringify({ type: 'progress', stage: 'end' }) +
      '\n';

    (global.fetch as any).mockImplementation((input: string) => {
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        return createStreamResponse([encodeChunk(streamData)]);
      }
      return Promise.resolve({ ok: true });
    });

    await act(async () => {
      await result.current.startCategorization();
    });

    // eslint-disable-next-line no-console
    expect(console.error).toHaveBeenCalled();
    expect(result.current.progress?.stage).toBe('end');
  });
});

describe('useOrganize proposal survival', () => {
  let applyResult = { message: 'Applied 0 tags to 0 notes', tags_created: 0, notes_tagged: 0 };

  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    global.fetch = vi.fn((input: any, options?: any) => {
      if (input === API_ROUTES.ORGANIZE_PENDING && options?.method !== 'DELETE') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              proposals: [{ tag_name: 'Recipes', note_ids: ['a'] }],
              generated_at: 1700000000,
              granularity: 'broad',
            }),
        } as Response);
      }
      if (input === API_ROUTES.ORGANIZE_APPLY) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(applyResult) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }) as any;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('restores proposals the server persisted, so a reload does not lose the generation', async () => {
    const { result } = renderHook(() => useOrganize());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.proposals).toHaveLength(1);
    expect(result.current.restoredAt).toBe(1700000000);
  });

  it('keeps the proposals when an apply tagged nothing', async () => {
    // Regression: apply reported "Applied 0 tags to 0 notes" and the client cleared
    // the list anyway, discarding a generation that cost hundreds of LLM calls.
    applyResult = { message: 'Applied 0 tags to 0 notes', tags_created: 0, notes_tagged: 0 };
    const { result } = renderHook(() => useOrganize());
    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      result.current.approveProposal(0);
    });
    await act(async () => {
      await result.current.applyProposals();
    });

    expect(result.current.proposals).toHaveLength(1);
    expect(result.current.error).toContain('kept');
  });

  it('clears the proposals when an apply really tagged notes', async () => {
    applyResult = { message: 'Applied 1 tags to 1 notes', tags_created: 1, notes_tagged: 1 };
    const { result } = renderHook(() => useOrganize());
    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      result.current.approveProposal(0);
    });
    await act(async () => {
      await result.current.applyProposals();
    });

    expect(result.current.proposals).toHaveLength(0);
    expect(result.current.error).toBeNull();
  });
});

describe('useOrganize streamed proposals', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    global.fetch = vi.fn(() => {
      // Default no-op for the PUT /pending/actions fire-and-forget and the restore GET.
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }) as any;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  const encodeChunk = (str: string) => new TextEncoder().encode(str);

  const createStreamResponse = (chunks: Uint8Array[]) => {
    const stream = new ReadableStream({
      start(controller) {
        chunks.forEach((c) => controller.enqueue(c));
        controller.close();
      },
    });
    return Promise.resolve({ ok: true, body: stream } as Response);
  };

  const proposalFrame = (tag: string, current: number, total: number) =>
    JSON.stringify({
      type: 'proposal',
      proposal: { tag_name: tag, note_ids: [tag], note_count: 1, sample_notes: [], confidence: 1 },
      current,
      total,
    }) + '\n';

  it('shows the most recently named proposal first, and does not re-sort', async () => {
    const { result } = renderHook(() => useOrganize());

    const stream =
      proposalFrame('Alpha', 1, 3) + proposalFrame('Beta', 2, 3) + proposalFrame('Gamma', 3, 3);

    (global.fetch as any).mockImplementation((input: string) => {
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        return createStreamResponse([encodeChunk(stream)]);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });

    await act(async () => {
      await result.current.startCategorization();
    });

    // Newest-named on top: reverse arrival order, so a name the user just watched
    // being generated is where their eye already is. Still no sorting by size or
    // name — order is a pure function of arrival, so nothing reshuffles under the
    // cursor beyond the single insertion at the top.
    expect(result.current.proposals.map((p) => p.proposal.tag_name)).toEqual([
      'Gamma',
      'Beta',
      'Alpha',
    ]);
    // Every streamed proposal starts pending.
    expect(result.current.proposals.every((p) => p.action === 'pending')).toBe(true);
  });

  it('keeps the progress current/total from the proposal frame', async () => {
    const { result } = renderHook(() => useOrganize());

    (global.fetch as any).mockImplementation((input: string) => {
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        return createStreamResponse([encodeChunk(proposalFrame('Alpha', 2, 5))]);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });

    await act(async () => {
      await result.current.startCategorization();
    });

    expect(result.current.progress?.current).toBe(2);
    expect(result.current.progress?.total).toBe(5);
  });

  it('re-attaches staged actions by tag name when label_updates replaces the list', async () => {
    // The user approved 'Alpha' while it streamed in. The authoritative label_updates frame
    // replaces the list at the end of the run — the approve must survive, keyed by tag name,
    // even though the final list may differ in shape/order.
    const { result } = renderHook(() => useOrganize());

    (global.fetch as any).mockImplementation((input: string) => {
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        const stream =
          proposalFrame('Alpha', 1, 2) +
          proposalFrame('Beta', 2, 2) +
          JSON.stringify({
            type: 'label_updates',
            proposals: [
              { tag_name: 'Beta', note_ids: ['b'], note_count: 1, sample_notes: [], confidence: 1 },
              {
                tag_name: 'Alpha',
                note_ids: ['a'],
                note_count: 1,
                sample_notes: [],
                confidence: 1,
              },
            ],
          }) +
          '\n';
        return createStreamResponse([encodeChunk(stream)]);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });

    let startPromise: Promise<void>;
    act(() => {
      startPromise = result.current.startCategorization();
    });
    // Let the first proposal frame land so 'Alpha' exists in the list.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    act(() => {
      result.current.approveProposal('Alpha');
    });

    await act(async () => {
      await startPromise;
    });

    // Final list is the label_updates order (Beta, Alpha); the approve on Alpha survived.
    const alpha = result.current.proposals.find((p) => p.proposal.tag_name === 'Alpha');
    const beta = result.current.proposals.find((p) => p.proposal.tag_name === 'Beta');
    expect(alpha?.action).toBe('approve');
    expect(beta?.action).toBe('pending');
  });

  it('a staged merge stays on its intended target after 50 more proposals arrive', async () => {
    // Regression: with positional indices, opening a merge dropdown and staging a
    // merge onto target N, then having 50 more proposals stream in, shifted the index so the
    // staged merge silently retargeted. Keying by tag name keeps it on its target.
    const { result } = renderHook(() => useOrganize());

    const names = Array.from({ length: 52 }, (_, i) => `Tag${i}`);

    (global.fetch as any).mockImplementation((input: string) => {
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        // First two arrive, the user stages a merge of Tag0 into Tag1, then 50 more arrive.
        const frames =
          proposalFrame('Tag0', 1, 52) +
          proposalFrame('Tag1', 2, 52) +
          names
            .slice(2)
            .map((n, i) => proposalFrame(n, i + 3, 52))
            .join('');
        return createStreamResponse([encodeChunk(frames)]);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });

    let startPromise: Promise<void>;
    act(() => {
      startPromise = result.current.startCategorization();
    });
    // Let Tag0 and Tag1 land.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    // Stage the merge by tag name: Tag0 -> Tag1. This is the ProposalCard merge handler.
    act(() => {
      result.current.mergeProposals('Tag0', 'Tag1');
    });

    // Let the remaining 50 proposals stream in.
    await act(async () => {
      await startPromise;
    });

    expect(result.current.proposals).toHaveLength(52);
    const tag0 = result.current.proposals.find((p) => p.proposal.tag_name === 'Tag0');
    // The merge is still on Tag1, despite 50 proposals arriving after it was staged.
    expect(tag0?.action).toBe('merge');
    expect(tag0?.mergeTarget).toBe('Tag1');
  });

  it('debounces staged decisions to PUT /pending/actions', async () => {
    const putCalls: { url: string; body: any }[] = [];
    global.fetch = vi.fn((input: any, options?: any) => {
      if (typeof input === 'string' && input.endsWith('/actions') && options?.method === 'PUT') {
        putCalls.push({ url: input, body: JSON.parse(options.body) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }) as any;

    const { result } = renderHook(() => useOrganize());

    (global.fetch as any).mockImplementation((input: string, options?: any) => {
      if (input.endsWith('/actions') && options?.method === 'PUT') {
        putCalls.push({ url: input, body: JSON.parse(options.body) });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
      }
      if (input === API_ROUTES.ORGANIZE_CATEGORIZE) {
        return createStreamResponse([
          encodeChunk(
            proposalFrame('Alpha', 1, 1) +
              JSON.stringify({
                type: 'label_updates',
                proposals: [
                  {
                    tag_name: 'Alpha',
                    note_ids: ['a'],
                    note_count: 1,
                    sample_notes: [],
                    confidence: 1,
                  },
                ],
              }) +
              '\n',
          ),
        ]);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });

    await act(async () => {
      await result.current.startCategorization();
    });

    act(() => {
      result.current.approveProposal('Alpha');
    });

    // The debounce window.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 500));
    });

    const actionsPut = putCalls.find((c) => c.body.actions?.Alpha === 'approve');
    expect(actionsPut, 'expected a PUT /pending/actions carrying {Alpha: approve}').toBeTruthy();
  });

  it('restores staged actions with the proposals on remount', async () => {
    global.fetch = vi.fn((input: any) => {
      if (input === API_ROUTES.ORGANIZE_PENDING) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              proposals: [{ tag_name: 'Recipes', note_ids: ['a'] }],
              actions: { Recipes: 'reject' },
              generated_at: 1700000000,
              granularity: 'broad',
            }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }) as any;

    const { result } = renderHook(() => useOrganize());
    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.proposals).toHaveLength(1);
    // The restored proposal carries the staged action, not 'pending'.
    expect(result.current.proposals[0].action).toBe('reject');
    expect(result.current.restoredAt).toBe(1700000000);
  });
});
