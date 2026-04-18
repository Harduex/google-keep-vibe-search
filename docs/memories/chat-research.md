# Chat System Research

*April 2026*

## Reference
Full research: [docs/research/chat-system-research.md](../research/chat-system-research.md)
Refactoring plan: [docs/research/chat-refactoring-plan.md](../research/chat-refactoring-plan.md)

## Key Findings
- ChatService is a god object (455 lines) — needs splitting into RetrievalOrchestrator, ContextBuilder, ConversationManager, StreamingProtocol
- Frontend per-chunk re-render problem (500+ setState calls per response)
- Citation click handler broken (never wired to parent component)
- Missing NotebookLM features: follow-up suggestions, source panel, streaming status phases
- Latency budget: 0.5-7.5s pre-LLM overhead (gap analysis is biggest contributor)

## Status
Phase 7 refactoring plan created, implementation pending.
