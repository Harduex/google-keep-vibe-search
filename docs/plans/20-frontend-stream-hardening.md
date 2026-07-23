# Task 20 — Frontend: stream performance + error handling

## Goal
Smooth deltas, seq observability, graceful agent errors.

## Spec
In `useChat.ts` / chat components:
1. Buffer `delta` text in a ref; flush to state on `requestAnimationFrame` (or a ~50ms interval) instead of setState per chunk.
2. Track `seq`; on a gap, `console.warn` only — no UX change.
3. Render agent_step with `action === "error"` as a subdued inline notice: "Search assistant hit a snag — answering from notes found so far". The stream must continue rendering normally after it.

## Checkpoint
Kill Ollama mid-agent-run: notice appears, response still completes from collected notes (or a clean generation error), no frozen spinner. A long streamed answer renders without jank; React DevTools shows bounded re-renders.

## Commit
`task 20: frontend stream buffering, seq tracking, graceful agent errors`
Delete this file in the same commit.
