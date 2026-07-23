# Task 17 — Wire new agent into chat_service (+seq, +error mapping)

## Goal
Swap agents behind the same NDJSON protocol; add seq numbers and graceful error path.

## Spec
In `chat_service.py`:
1. Construct `PydanticNoteAgent` where `NoteAgent` was constructed (do NOT delete NoteAgent yet — task 19).
2. Map `action="error"` steps to `Protocol.agent_step("error", reasoning, 0)` AND continue to final generation with whatever notes were collected — never dead-end the stream.
3. Every emitted protocol line gets a per-request monotonic integer `seq` field.
4. `ENABLE_AGENT_MODE=false` path must be byte-identical to before (test it).

## Checkpoint
Live against Ollama, 3 questions in agent mode: raw NDJSON captured; phases ordered; seq gapless from 0; at least one agent_step per run; done event has citations field. `ENABLE_AGENT_MODE=false` output unchanged vs pre-task capture.

## Commit
`task 17: wire PydanticAI agent into chat service with seq numbering`
Delete this file in the same commit.
