# Implementation Plans

Track phased implementation plans here. Completed phases move to done/.

## Completed

### Phase 7: Chat System Refactoring
- 7A: Critical chat bug fixes
- 7B: Split ChatService into focused services + streaming improvements

### Phase 8: NotebookLM-Style Agentic RAG
- 8A: LiteLLM integration (replaced raw httpx with universal LLM client)
- 8B: Agent core + tools (NoteAgent with plan-and-execute loop, feature-flagged)
- 8C: Agentic UI (AgentSteps timeline component, real-time step streaming)
- 8D: Grounding improvements (per-claim NLI scoring, GroundingScore component)

### Phase 9: Categorization Pipeline
- 9A: Backend refactor (embedding assignment, LiteLLM integration, evaluation harness)
- 9B: Frontend UI update (multi-label chips support)

### Phase 10: Tag Categorization & Clustering Refactor
- 10A: Implement c-TF-IDF keyword extraction in `CategorizationService._get_hint_keywords`
- 10B: Verify Prompt Hardening (Ensure `TAG_NAMING_PROMPT` forbids verbs/generic descriptors)
- 10C: Verify `_get_cluster_sizing` uses dynamic cluster sizing (`math.log10`)
- 10D: Implement native tool calling to bypass strict JSON/prompt constraints

## In Progress

None.

## Planned

None.
