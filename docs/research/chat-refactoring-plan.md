# Chat System Refactoring Plan

*Created: 2026-04-18*
*Based on: [chat-system-research.md](chat-system-research.md)*
*Target: NotebookLM-comparable conversational AI over personal notes*

---

## Design Principles

1. **Grounded by default** — Every claim links to evidence. Citations are first-class, not afterthoughts.
2. **Progressive disclosure** — Show retrieval → analysis → generation phases. Never leave users waiting with no feedback.
3. **Streaming-first** — Architecture assumes streaming. Non-streaming is the exception.
4. **Fail gracefully** — Partial results > error screens. Degrade service tiers, don't crash.
5. **Separation of concerns** — Each service does one thing. ChatService orchestrates, doesn't implement.

---

## Phase 7A: Critical Bug Fixes (Day 1)

### 7A.1 Fix Citation Click Handler

**Problem**: `onCitationClick` prop never passed to `ChatMessage`. Users click citations and nothing happens.

**Files**: `client/src/components/Chat/index.tsx`, `ChatNotes.tsx`

**Changes**:
1. In `Chat/index.tsx`: Pass `onCitationClick` handler to each `ChatMessage`
2. Handler scrolls to corresponding note in `ChatNotes` sidebar and highlights it
3. Add `ref` to each NoteCard in ChatNotes, keyed by note index
4. On click: `noteRefs[noteNumber].current.scrollIntoView({ behavior: 'smooth' })` + flash highlight class

**Effort**: 1-2 hours

---

### 7A.2 Fix Streaming Re-render Performance

**Problem**: `setMessages()` called per delta chunk (500+ times/response). Each triggers full React reconciliation.

**File**: `client/src/hooks/useChat.ts`

**Changes**:
1. Store streaming content in a `useRef<string>` instead of state
2. Use `requestAnimationFrame` to batch DOM updates (~60fps instead of per-chunk)
3. Only call `setMessages()` on `done` message (once per response)
4. Create a `StreamingContent` component that reads from the ref and updates via RAF

```typescript
// New pattern:
const streamingContentRef = useRef<string>('');
const rafIdRef = useRef<number>(0);

// On delta:
streamingContentRef.current += chunk;
if (!rafIdRef.current) {
  rafIdRef.current = requestAnimationFrame(() => {
    forceUpdate(); // or setState for just the streaming message
    rafIdRef.current = 0;
  });
}
```

**Effort**: 2-3 hours

---

### 7A.3 Fix Duplicate Conflict Detection

**Problem**: `detect_conflicts()` runs twice per stream request.

**File**: `app/services/chat_service.py`

**Changes**:
1. Remove conflict detection from `prepare_messages_with_context()` (line 110)
2. Keep it only in `stream_chat_with_protocol()` (line 377)
3. Pass pre-computed conflicts into `prepare_messages_with_context()` as a parameter

**Effort**: 30 minutes

---

### 7A.4 Fix NDJSON Protocol

**Problem**: Potential double newlines in NDJSON stream.

**File**: `app/services/chat_service.py`

**Changes**: Audit all `json.dumps(...).encode() + b"\n"` calls. Ensure exactly one `\n` delimiter per message.

**Effort**: 30 minutes

---

## Phase 7B: Backend Refactoring (Days 2-4)

### 7B.1 Split ChatService into Focused Services

**Current**: `chat_service.py` (455 lines) handles everything.

**New architecture**:

```
app/services/
  chat_service.py          -- Thin orchestrator (100 lines)
  retrieval_orchestrator.py -- Multi-signal retrieval + RRF + reranking (180 lines)
  context_builder.py       -- Format notes, inject conflicts/warnings (80 lines)
  conversation_manager.py  -- Windowing, summarization, history (100 lines)
  streaming_protocol.py    -- NDJSON encoding, message types, phases (80 lines)
```

**chat_service.py** (new, thin orchestrator):
```python
class ChatService:
    def __init__(self, retrieval, context_builder, conversation, 
                 streaming, verification, query_service, llm_client):
        ...
    
    async def stream_chat(self, messages, options) -> AsyncGenerator[bytes]:
        # 1. Manage conversation window
        messages = await self.conversation.maybe_summarize(messages)
        
        # 2. Retrieve context
        yield self.streaming.phase("retrieving")
        notes = await self.retrieval.get_context(messages, options)
        
        # 3. Detect conflicts
        conflicts = await self.verification.detect_conflicts(notes)
        yield self.streaming.context(notes, conflicts)
        
        # 4. Build prompt
        prompt_messages = self.context_builder.build(messages, notes, conflicts)
        
        # 5. Stream LLM response
        yield self.streaming.phase("generating")
        async for chunk in self.llm_client.stream(prompt_messages):
            yield self.streaming.delta(chunk)
        
        # 6. Post-process
        citations = extract_citations(full_response, notes)
        yield self.streaming.done(full_response, citations)
        
        # 7. Verify (async, non-blocking)
        verification = await self.verification.verify_citations(full_response, citations, notes)
        yield self.streaming.verification(verification)
```

**retrieval_orchestrator.py**:
```python
class RetrievalOrchestrator:
    async def get_context(self, messages, options) -> list[dict]:
        # 1. Decompose query if complex
        # 2. Primary retrieval (semantic + BM25 + entity)
        # 3. Context retrieval (conversation-aware, with dedup)
        # 4. Chunk-level search
        # 5. RRF fusion across all signals
        # 6. Cross-encoder reranking
        # 7. Saturation check
        # 8. Gap analysis (CRAG)
        ...
```

**streaming_protocol.py**:
```python
class StreamingProtocol:
    """Encodes all NDJSON message types with consistent formatting."""
    
    def phase(self, name: str) -> bytes:
        """New message type: retrieval status phases."""
        return self._encode({"type": "phase", "phase": name})
    
    def context(self, notes, conflicts) -> bytes: ...
    def delta(self, content: str) -> bytes: ...
    def done(self, response, citations) -> bytes: ...
    def verification(self, results) -> bytes: ...
    def error(self, message: str) -> bytes: ...
    
    def _encode(self, data: dict) -> bytes:
        return json.dumps(data).encode() + b"\n"
```

**Effort**: 1.5-2 days

---

### 7B.2 Add Streaming Status Phases

**Problem**: User sees nothing for 1-7s while retrieval + analysis happens.

**New protocol message type**:
```json
{"type": "phase", "phase": "searching", "detail": "Searching 5000 notes..."}
{"type": "phase", "phase": "analyzing", "detail": "Analyzing 12 relevant notes..."}
{"type": "phase", "phase": "checking", "detail": "Checking for conflicts..."}
{"type": "phase", "phase": "generating"}
```

**Backend**: Emit phase messages at each pipeline stage in the refactored `stream_chat()`.

**Frontend**: Show phase indicator above the message bubble:
- "Searching your notes..." (magnifying glass icon)
- "Analyzing relevance..." (analytics icon) 
- "Generating response..." (edit icon, then fade to streaming text)

**Effort**: 3-4 hours

---

### 7B.3 Follow-Up Suggestion Generation

**New endpoint**: `POST /api/chat/suggestions`
Or inline: add `suggestions` field to the `done` streaming message.

**Backend**: After response completes, generate 3 follow-up questions via LLM:
```python
FOLLOW_UP_PROMPT = """Based on this conversation and the notes used, suggest 3 brief follow-up questions 
the user might want to ask. Return ONLY the questions, one per line. Keep each under 60 characters."""
```

**Integration**: Add to `stream_chat_with_protocol()` after `done` message:
```json
{"type": "suggestions", "questions": ["What changed since last month?", "Compare with project X", "Show related tasks"]}
```

**Frontend**: Render as clickable chips below the response. On click, send as new message.

**Effort**: 0.5-1 day

---

### 7B.4 Improve Error Recovery

**Current**: Generic `{"type": "error", "error": "message"}` kills the stream.

**Changes**:
1. **Partial results on timeout**: If LLM times out but we have context, send what we have:
   ```json
   {"type": "partial", "notes": [...], "message": "Response generation timed out. Here are the relevant notes found:"}
   ```
2. **Retrieval failure fallback**: If retrieval fails, continue with empty context (already handled by NO_NOTES prompt)
3. **Verification failure**: Already non-fatal, but add explicit `{"type": "verification_error"}` message
4. **User-friendly error messages**: Map technical errors to human-readable messages

**Effort**: 3-4 hours

---

## Phase 7C: Frontend Refactoring (Days 4-6)

### 7C.1 Source Panel with Evidence Linking

**Goal**: When user clicks a citation, show the source note with the relevant passage highlighted.

**New component**: `SourcePanel.tsx`
```
+------------------+-------------------+-----------------+
| SessionList      | Chat Messages     | Source Panel     |
| (sessions)       | (conversation)    | (evidence view)  |
+------------------+-------------------+-----------------+
```

**Behavior**:
1. Citation chip click → opens Source Panel (right side)
2. Shows the full note content
3. Highlights the sentence(s) that support the claim (from verification data)
4. Shows NLI verdict badge (supported/contradicted/neutral) with score
5. "View in notes" link to jump to full note search

**Data flow**: Verification `claim` field already contains the extracted claim text. Use it to find and highlight matching text in the source note.

**Effort**: 1-1.5 days

---

### 7C.2 Phase Status Indicator Component

**New component**: `PhaseIndicator.tsx`

Renders the current pipeline phase with animated transitions:
```
[magnifying glass] Searching your notes...     ← phase: "searching"
[analytics]        Analyzing 8 relevant notes... ← phase: "analyzing"  
[warning]          Checking for conflicts...     ← phase: "checking"
[edit]             Generating response...        ← phase: "generating"
```

Each phase fades in/out. Previous phases show as completed (checkmark). Current phase has a subtle pulse animation.

**Effort**: 3-4 hours

---

### 7C.3 Follow-Up Suggestion Chips

**New component**: `SuggestionChips.tsx`

Renders below the last assistant message:
```
Suggested follow-ups:
[What changed since October?] [Compare with project Alpha] [Show related deadlines]
```

- Chips are clickable, send the question as a new user message
- Fade in after response completes
- Disappear when user types a new message
- Max 3 chips, each max 60 chars

**Effort**: 2-3 hours

---

### 7C.4 Improved Empty State

**Current**: "Ask me anything about your notes!" with robot icon.

**New design**:
```
+------------------------------------------+
|          [smart_toy icon]                |
|   Chat with your notes                   |
|                                          |
|   Try asking:                            |
|   [What did I write about X last month?] |
|   [Summarize my notes on project Y]     |
|   [Find conflicts in my meeting notes]  |
+------------------------------------------+
```

Example questions are clickable, pre-fill the input. Generate dynamically from note topics if possible, otherwise use static examples.

**Effort**: 1-2 hours

---

### 7C.5 Smart Auto-Scroll

**Problem**: Current `scrollIntoView` on every message interrupts user reading earlier messages.

**Fix**:
1. Track if user is "at bottom" (within 100px of scroll end)
2. Only auto-scroll if at bottom
3. Show "New message" pill when new content arrives while user is scrolled up

```typescript
const isAtBottom = useRef(true);
const onScroll = (e) => {
  const { scrollTop, scrollHeight, clientHeight } = e.target;
  isAtBottom.current = scrollHeight - scrollTop - clientHeight < 100;
};
```

**Effort**: 1-2 hours

---

### 7C.6 Code Block Enhancements

**Changes**:
1. Add syntax highlighting via `react-syntax-highlighter` (or `prism-react-renderer`)
2. Add copy button to code blocks
3. Add language label

**Integration**: Custom `code` component in ReactMarkdown:
```tsx
<ReactMarkdown components={{ code: CodeBlock }} />
```

**Effort**: 2-3 hours

---

## Phase 7D: Polish & Integration (Days 7-8)

### 7D.1 Citation Confidence Indicators

**Current**: NLI verdict shown only in tooltip text.

**Change**: Make verdict visually prominent:
- **Supported**: Green left border + small checkmark badge
- **Contradicted**: Red left border + warning badge + "This claim may conflict with the source"
- **Neutral**: Yellow left border + question mark badge
- Show support score as a mini progress bar inside the chip

**Effort**: 2-3 hours

---

### 7D.2 Conversation Export

**New feature**: "Export conversation" button in session actions.

**Formats**:
- **Copy to clipboard**: Markdown-formatted conversation
- **Download**: `.md` file with metadata header (date, model, note count)

**Effort**: 2-3 hours

---

### 7D.3 Example Questions Generation

**Backend**: New endpoint `GET /api/chat/examples` that generates 3 example questions based on recent/popular note topics.

**Implementation**:
```python
# Pick 3 diverse notes by category, generate questions
sample_notes = random.sample(notes, min(3, len(notes)))
examples = [f"What do my notes say about {note['title']}?" for note in sample_notes]
```

Or LLM-generated for more natural phrasing. Cache for 1 hour.

**Effort**: 2-3 hours

---

### 7D.4 Persist UI Preferences

Store in `localStorage`:
- Sidebar open/closed state
- Notes context toggle
- Topic input visibility
- Source panel width

**Effort**: 1 hour

---

## Implementation Order

```
Day 1: Phase 7A — Critical bug fixes
  - 7A.1: Fix citation click handler          (1-2h)
  - 7A.2: Fix streaming re-render perf        (2-3h)
  - 7A.3: Fix duplicate conflict detection     (30m)
  - 7A.4: Fix NDJSON protocol                  (30m)

Day 2-3: Phase 7B.1 — Backend service split
  - Split ChatService into 4 focused services  (1.5-2d)

Day 3-4: Phase 7B.2-7B.4 — Backend features
  - 7B.2: Streaming status phases              (3-4h)
  - 7B.3: Follow-up suggestions                (0.5-1d)
  - 7B.4: Error recovery                       (3-4h)

Day 4-6: Phase 7C — Frontend refactoring
  - 7C.1: Source panel with evidence linking    (1-1.5d)
  - 7C.2: Phase status indicator               (3-4h)
  - 7C.3: Follow-up suggestion chips           (2-3h)
  - 7C.4: Improved empty state                 (1-2h)
  - 7C.5: Smart auto-scroll                    (1-2h)
  - 7C.6: Code block enhancements              (2-3h)

Day 7-8: Phase 7D — Polish
  - 7D.1: Citation confidence indicators       (2-3h)
  - 7D.2: Conversation export                  (2-3h)
  - 7D.3: Example questions generation         (2-3h)
  - 7D.4: Persist UI preferences               (1h)
```

---

## VRAM Impact

No additional VRAM. All changes are architectural (service splitting, protocol, frontend). Same models used.

---

## New Dependencies

```
# Frontend
react-syntax-highlighter    # Code block syntax highlighting (7C.6)

# No new backend dependencies
```

---

## Testing Strategy

| Phase | Test Type | What to Verify |
|-------|-----------|----------------|
| 7A.1 | Manual | Citation click scrolls to note, highlight flashes |
| 7A.2 | Performance | Measure re-renders during streaming (React DevTools profiler) |
| 7A.3 | Unit | Conflicts computed once per request |
| 7A.4 | Integration | NDJSON parser handles all message types cleanly |
| 7B.1 | Unit | Each new service has isolated unit tests |
| 7B.2 | E2E | Phase messages appear in correct order |
| 7B.3 | Manual | Suggestions are relevant, clickable, send message |
| 7C.1 | Manual | Source panel shows correct note, highlights evidence |
| 7C.5 | Manual | Scroll doesn't jump while reading history |

---

## Success Criteria

After refactoring:
1. Citation clicks navigate to source with evidence highlighted
2. Streaming shows progressive status (searching → analyzing → generating)
3. Follow-up suggestions appear after each response
4. No perceptible jank during streaming (< 60fps frame drops)
5. Error states degrade gracefully (partial results, not error screens)
6. ChatService is < 120 lines (orchestration only)
7. Source panel shows evidence context for any citation
