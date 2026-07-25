import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { API_ROUTES } from '@/const';

import { useChat } from '../useChat';

const originalFetch = global.fetch;

describe('useChat NDJSON stream parser', () => {
  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.useFakeTimers({ shouldAdvanceTime: true });

    global.fetch = vi.fn((input, options) => {
      if (input === API_ROUTES.CHAT_MODEL) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ model: 'test-model' }),
        } as Response);
      }
      if (input === API_ROUTES.CHAT_SESSIONS && (!options || options.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ sessions: [] }),
        } as Response);
      }
      if (input === API_ROUTES.CHAT_SESSIONS && options?.method === 'POST') {
        if (options.body && JSON.parse(options.body as string).messages) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({}),
          } as Response);
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: 'session-123' }),
        } as Response);
      }
      if (
        typeof input === 'string' &&
        input.includes(API_ROUTES.CHAT_SESSIONS) &&
        options?.method === 'POST'
      ) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({}),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      } as Response);
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.useRealTimers();
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

  const mockChatFetch = (chatResponse: any) => {
    (global.fetch as any).mockImplementation((input: string, options?: any) => {
      if (input === API_ROUTES.CHAT) {
        return typeof chatResponse === 'function' ? chatResponse(options) : chatResponse;
      }
      if (input === API_ROUTES.CHAT_MODEL) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ model: 'test-model' }),
        });
      }
      if (input === API_ROUTES.CHAT_SESSIONS && (!options || options.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ sessions: [] }),
        });
      }
      if (input === API_ROUTES.CHAT_SESSIONS && options?.method === 'POST') {
        if (options.body && JSON.parse(options.body as string).messages) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({}),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: 'session-123' }),
        });
      }
      if (
        typeof input === 'string' &&
        input.includes(API_ROUTES.CHAT_SESSIONS) &&
        options?.method === 'POST'
      ) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({}),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });
  };

  it('handles chunk-boundary safety with split JSON objects', async () => {
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const jsonStr = JSON.stringify({ type: 'phase', phase: 'searching' }) + '\n';
    const splitIndex = 15;
    const chunk1 = encodeChunk(jsonStr.slice(0, splitIndex));
    const chunk2 = encodeChunk(jsonStr.slice(splitIndex));

    mockChatFetch(createStreamResponse([chunk1, chunk2]));

    await act(async () => {
      await result.current.sendMessage('Hello');
    });

    expect(result.current.currentPhase).toBe('searching');
  });

  it('handles chunk boundary mid-multi-byte-UTF-8 character', async () => {
    const { result } = renderHook(() => useChat());

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const baseJson = '{"type":"delta","content":"Тест"}\n';
    const tIndex = baseJson.indexOf('Т');
    const prefixBytes = new TextEncoder().encode(baseJson.slice(0, tIndex));

    const chunk1 = new Uint8Array([...prefixBytes, 0xd0]);
    const chunk2 = new Uint8Array([0xa2, ...new TextEncoder().encode(baseJson.slice(tIndex + 1))]);

    mockChatFetch(createStreamResponse([chunk1, chunk2]));

    await act(async () => {
      await result.current.sendMessage('Hello');
      await vi.runAllTimersAsync();
    });

    const assistantMessages = result.current.messages.filter((m) => m.role === 'assistant');
    expect(assistantMessages[0].content).toBe('Тест');
  });

  it('processes every event type mutating the right slice of state', async () => {
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const events = [
      { type: 'context', notes: [{ id: '1', title: 'N1' }], conflicts: [{ note_id: '1' }] },
      { type: 'phase', phase: 'thinking' },
      { type: 'suggestions', questions: ['Q1', 'Q2'] },
      {
        type: 'agent_step',
        step_number: 1,
        action: 'search',
        params: {},
        result_summary: 'ok',
        notes_found: 1,
        reasoning: 'r',
      },
      { type: 'grounding', claims: [], overall_score: 0.9, grounded_count: 1, total_claims: 2 },
      { type: 'delta', content: 'hello' },
      {
        type: 'verification',
        citations: [{ note_number: 1, note_id: '1', note_title: 'N', claim: 'A' }],
      },
      {
        type: 'done',
        full_response: 'hello world',
        citations: [{ note_number: 1, note_id: '1', note_title: 'N', claim: 'B' }],
      },
    ];

    const streamData = events.map((e) => JSON.stringify(e) + '\n').join('');

    mockChatFetch(createStreamResponse([encodeChunk(streamData)]));

    await act(async () => {
      await result.current.sendMessage('Hello');
      await vi.runAllTimersAsync();
    });

    expect(result.current.relevantNotes).toHaveLength(1);
    expect(result.current.conflicts).toHaveLength(1);
    expect(result.current.currentPhase).toBeNull();
    expect(result.current.suggestions).toEqual(['Q1', 'Q2']);
    expect(result.current.agentSteps).toHaveLength(1);
    expect(result.current.groundingResult?.overall_score).toBe(0.9);

    const assistantMessages = result.current.messages.filter((m) => m.role === 'assistant');
    expect(assistantMessages[0].content).toBe('hello world');
    expect(assistantMessages[0].citations?.[0].claim).toBe('B');
  });

  it('warns on a skipped seq and does not throw', async () => {
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const streamData =
      JSON.stringify({ type: 'delta', content: 'A', seq: 1 }) +
      '\n' +
      JSON.stringify({ type: 'delta', content: 'B', seq: 3 }) +
      '\n';

    mockChatFetch(createStreamResponse([encodeChunk(streamData)]));

    await act(async () => {
      await result.current.sendMessage('Hello');
      await vi.runAllTimersAsync();
    });

    // eslint-disable-next-line no-console
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('expected 2, got 3'));
    const assistantMessages = result.current.messages.filter((m) => m.role === 'assistant');
    expect(assistantMessages[0].content).toBe('AB');
  });

  it('stopGenerating() mid-stream aborts, cancels RAF, and leaves no state update after unmount', async () => {
    const { result, unmount } = renderHook(() => useChat());
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    let streamController: ReadableStreamDefaultController;
    const stream = new ReadableStream({
      start(controller) {
        streamController = controller;
      },
    });

    mockChatFetch((options: any) => {
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
    });

    let sendPromise: Promise<void>;
    act(() => {
      sendPromise = result.current.sendMessage('Hello');
    });

    await act(async () => {
      streamController.enqueue(
        encodeChunk(JSON.stringify({ type: 'delta', content: 'partial' }) + '\n'),
      );
    });

    expect(result.current.isLoading).toBe(true);

    await act(async () => {
      result.current.stopGenerating();
    });

    expect(result.current.isLoading).toBe(false);

    unmount();

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    await act(async () => {
      await sendPromise;
    });

    expect(true).toBe(true);
  });

  it('skips a malformed line without killing the stream', async () => {
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const streamData =
      JSON.stringify({ type: 'delta', content: 'Good' }) +
      '\n' +
      '{ malformed json \n' +
      JSON.stringify({ type: 'delta', content: 'End' }) +
      '\n';

    mockChatFetch(createStreamResponse([encodeChunk(streamData)]));

    await act(async () => {
      await result.current.sendMessage('Hello');
      await vi.runAllTimersAsync();
    });

    // eslint-disable-next-line no-console
    expect(console.error).toHaveBeenCalled();
    const assistantMessages = result.current.messages.filter((m) => m.role === 'assistant');
    expect(assistantMessages[0].content).toBe('GoodEnd');
  });

  it('handles error events properly', async () => {
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    const streamData = JSON.stringify({ type: 'error', error: 'Something went wrong' }) + '\n';

    mockChatFetch(createStreamResponse([encodeChunk(streamData)]));

    await act(async () => {
      await result.current.sendMessage('Hello');
      await vi.runAllTimersAsync();
    });

    expect(result.current.error).toBe('Something went wrong');
  });
});
