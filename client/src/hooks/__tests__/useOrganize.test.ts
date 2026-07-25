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
    // The B8 experience: apply reported "Applied 0 tags to 0 notes" and the client cleared
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
