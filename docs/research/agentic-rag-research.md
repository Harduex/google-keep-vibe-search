# Agentic RAG Research Report

*Created: 2026-04-18*
*Scope: Architecture patterns, CRAG, citation grounding, late chunking, local LLM feasibility, agent harness design*
*Goal: Recommendations for Google Keep Vibe Search (Ollama + sentence-transformers + FastAPI)*

---

## Executive Summary

Agentic RAG represents a shift from "retrieve-then-generate" to "reason-about-what-to-retrieve." Instead of a fixed pipeline, an LLM agent controls when, what, and how much to retrieve through tool calls. Systems like NotebookLM, Perplexity, and research agents (Deep Research, storm) all follow this pattern with varying levels of autonomy. The key differentiator from traditional RAG is a **planning loop** where the LLM evaluates retrieval quality and decides next actions.

This project already implements several agentic features (prompt decomposition, CRAG-style gap analysis, NLI verification, multi-signal RRF fusion). The main gaps are: (1) the retrieval pipeline is still largely procedural rather than agent-driven, (2) gap analysis uses a simple binary check rather than structured reasoning, (3) citation grounding maps to whole notes rather than specific passages, and (4) chunking is traditional rather than contextual. This report provides specific architectural recommendations to close these gaps while remaining feasible on local hardware (RTX 3060 12GB, Ollama).

---

## 1. Agentic RAG Architecture Patterns

### 1.1 What Makes RAG "Agentic"

Traditional RAG follows a fixed pipeline: embed query → retrieve top-k → stuff into prompt → generate. Agentic RAG replaces the fixed pipeline with an **agent loop** where the LLM decides:

- **Whether** to retrieve (some queries need no retrieval)
- **What** to retrieve (query reformulation, decomposition)
- **When** to stop retrieving (sufficiency judgment)
- **How** to combine results (synthesis across multiple retrievals)

The core architectural difference:

```
Traditional RAG:        query → retrieve → generate
Agentic RAG:            query → plan → [retrieve → evaluate → replan]* → generate
```

### 1.2 NotebookLM Architecture (Reverse-Engineered)

NotebookLM (Google, 2024-2026) is the gold standard for grounded conversational search over personal documents. Key architectural observations:

1. **Source-first grounding**: Every response is grounded exclusively in uploaded sources. The system refuses to answer from general knowledge when sources exist. Claims without evidence get flagged.

2. **Multi-pass retrieval**: NotebookLM doesn't do single-shot retrieval. It:
   - Parses the query for multiple information needs
   - Retrieves independently for each need
   - Cross-references retrieved passages
   - Fills gaps with targeted follow-up retrieval

3. **Evidence linking**: Each claim links to a specific passage (not just a document). The UI shows the exact text span that supports each statement. This is the biggest UX differentiator.

4. **Progressive status**: The UI shows retrieval → analysis → writing phases. Users see "Searching your sources..." → "Analyzing 5 relevant passages..." → streaming response.

5. **Follow-up suggestions**: After each response, NotebookLM suggests 2-3 related questions derived from the source material, not from the conversation.

6. **Audio overview**: Generates podcast-style summaries of sources using multi-speaker TTS — not directly relevant to our architecture, but shows the direction of source synthesis.

**Key lesson**: NotebookLM's quality comes from passage-level (not document-level) grounding and multi-pass retrieval. These are achievable locally.

### 1.3 Perplexity Architecture

Perplexity (2024-2026) is the reference for agentic web search. Key patterns:

1. **Query analysis and routing**: Before any retrieval, the agent classifies the query:
   - Simple factual → direct search
   - Multi-faceted → decompose into sub-queries
   - Follow-up → incorporate conversation context
   - Opinion/creative → reduce retrieval, increase generation

2. **Search-then-read loop**: Each sub-query triggers a web search, then a reader model extracts relevant passages. The reader is a smaller model (not the main generator) that scores passage relevance.

3. **Citation-integrated generation**: The generation model is trained/prompted to produce inline citations as it writes, not post-hoc. Citations reference specific source passages.

4. **Streaming with sources**: Sources appear before the answer. The UI shows which documents were found, then streams the synthesis. This builds trust.

5. **Pro Search (agentic mode)**: For complex queries, Perplexity runs a multi-step agent:
   - Step 1: Plan what to search for
   - Step 2: Execute multiple searches
   - Step 3: Read and evaluate results
   - Step 4: Decide if more searches needed
   - Step 5: Synthesize final answer

**Key lesson**: The query routing step (what kind of answer does this need?) prevents over-retrieval on simple questions and under-retrieval on complex ones.

### 1.4 Research Agent Patterns (Deep Research, Storm)

Research agents (OpenAI Deep Research, Stanford Storm, Tavily) operate at longer timescales:

1. **Plan-driven exploration**: A research plan is generated first with specific sub-questions. Each sub-question drives independent retrieval.

2. **Source graph**: Findings are stored in a knowledge graph with provenance. Cross-references between sources are tracked explicitly.

3. **Iterative refinement**: After initial retrieval, the agent reviews its findings, identifies gaps, and launches targeted follow-up searches.

4. **Outline-then-fill**: Generate a report outline first, then fill each section with evidence. This ensures comprehensive coverage.

**Key lesson**: Separating planning from execution enables better coverage and reduces hallucination by making the information-gathering process explicit.

---

## 2. Multi-Step Retrieval Agents

### 2.1 Tool-Use Patterns

The dominant pattern (LangGraph, LlamaIndex, Haystack 2.x) gives the LLM explicit tools:

```python
tools = [
    search_notes(query: str, max_results: int) -> List[NoteResult],
    search_chunks(query: str, note_ids: List[str]) -> List[ChunkResult],
    get_note_detail(note_id: str) -> NoteDetail,
    check_sufficiency(query: str, evidence: List[str]) -> SufficiencyResult,
]
```

The agent then runs in a **ReAct loop**:
```
Thought: The user asks about travel plans. I need to search for travel-related notes.
Action: search_notes("travel plans itinerary")
Observation: Found 3 notes about trips to Japan, Italy, and camping.
Thought: The user specifically asked about Japan. Let me get more detail.
Action: get_note_detail("note_japan_trip")
Observation: [detailed note content]
Thought: I have sufficient context. Let me respond.
```

### 2.2 When to Search (Decision Patterns)

Production systems use these heuristics:

| Signal | Decision |
|--------|----------|
| Query is a greeting/meta ("hi", "thanks") | Skip retrieval |
| Query references "you said" / "earlier" | Search conversation history only |
| Query is factual about user's domain | Full retrieval pipeline |
| Query is general knowledge | Minimal retrieval, check if notes add value |
| Previous retrieval was insufficient | Targeted gap-filling search |
| Query has multiple facets | Decompose, search each independently |

### 2.3 When to Stop Retrieving

Three patterns for deciding retrieval sufficiency:

1. **LLM-as-judge** (current approach in this project): Ask the LLM "is this sufficient?" Binary SUFFICIENT/MISSING response. Simple but coarse.

2. **Coverage scoring**: For each sub-question, compute semantic similarity between the query and retrieved passages. If max similarity < threshold for any sub-question, retrieve more. More deterministic, no LLM call needed.

3. **Confidence calibration**: The generation model provides a confidence score with its answer. Low confidence triggers re-retrieval. Requires model that can express calibrated uncertainty (works better with larger models).

### 2.4 LangGraph Agentic RAG Pattern

LangGraph (LangChain's graph-based orchestration) defines agentic RAG as a state machine:

```
               ┌──────────────┐
               │   Classify    │
               │   Query       │
               └──────┬───────┘
                      │
            ┌─────────┼─────────┐
            ▼         ▼         ▼
       [Simple]   [Complex]  [Follow-up]
            │         │         │
            ▼         ▼         ▼
       ┌────────┐ ┌────────┐ ┌────────┐
       │Retrieve│ │Decompose│ │Context │
       │        │ │& Retrieve│ │Retrieve│
       └────┬───┘ └────┬───┘ └────┬───┘
            │         │         │
            └─────────┼─────────┘
                      ▼
               ┌──────────────┐
               │   Grade      │
               │   Documents  │
               └──────┬───────┘
                      │
              ┌───────┼───────┐
              ▼               ▼
         [Relevant]     [Not Relevant]
              │               │
              ▼               ▼
         ┌────────┐    ┌──────────┐
         │Generate │    │Re-query  │
         │         │    │(reformulate)│
         └────┬───┘    └──────┬───┘
              │               │
              ▼               │
         ┌────────┐          │
         │Check    │◄─────────┘
         │Halluc.  │
         └────┬───┘
              │
       ┌──────┼──────┐
       ▼             ▼
  [Grounded]   [Not Grounded]
       │             │
       ▼             ▼
    Return      Re-generate
```

Key nodes:
- **Query classifier**: Routes to different retrieval strategies
- **Document grader**: Relevance filter before generation
- **Hallucination checker**: Post-generation verification

### 2.5 LlamaIndex Agent Patterns

LlamaIndex provides `QueryPlanTool` and `SubQuestionQueryEngine`:

1. **QueryPlanTool**: LLM generates a DAG of sub-queries with dependencies. Parallel sub-queries execute concurrently, dependent ones wait.

2. **RouterQueryEngine**: Routes to different indices (vector, keyword, structured) based on query type.

3. **Agentic retrieval**: Each index is wrapped as a tool. The agent decides which tools to call and in what order.

The pattern that maps best to this project: **sub-question decomposition with parallel retrieval, followed by fusion and gap analysis**.

---

## 3. CRAG (Corrective RAG)

### 3.1 Original CRAG Paper (Yan et al., 2024)

The Corrective Retrieval Augmented Generation paper introduced three key components:

1. **Retrieval evaluator**: A lightweight model (not the generator) that classifies each retrieved document as:
   - **Correct**: Document is relevant and useful
   - **Incorrect**: Document is irrelevant
   - **Ambiguous**: Partially relevant, needs refinement

2. **Knowledge refinement**: For documents classified as "correct," extract only the relevant passages (not the whole document). This is decompose-then-recompose: break the document into sentences, score each, keep only supporting ones.

3. **Corrective actions**:
   - If evaluator says **Correct**: Refine and use the document
   - If **Incorrect**: Trigger web search for additional information
   - If **Ambiguous**: Combine refined document with web search results

### 3.2 Beyond the Paper: Production CRAG Patterns (2025-2026)

Production systems have evolved CRAG into more sophisticated patterns:

**Multi-dimensional evaluation**: Instead of a single relevance score, evaluate along multiple axes:
- **Topical relevance**: Is the document about the right topic?
- **Information completeness**: Does it contain the specific facts needed?
- **Temporal relevance**: Is the information current enough?
- **Specificity match**: Does the granularity match the query?

**Iterative refinement with memory**: Track what's been tried:
```python
class CRAGState:
    original_query: str
    sub_queries: List[str]
    retrieved_docs: List[Document]
    evaluations: List[Evaluation]  # per-document scores
    gap_descriptions: List[str]    # what's still missing
    refinement_queries: List[str]  # queries generated to fill gaps
    iteration: int
    max_iterations: int = 3
```

**Structured gap analysis** (improvement over binary SUFFICIENT/MISSING):
```
Given the query and retrieved documents, evaluate:
1. Which aspects of the query are fully covered? List them.
2. Which aspects are partially covered? What's missing?
3. Which aspects are not covered at all?
4. For each gap, suggest a specific search query to fill it.

Return as JSON:
{
  "covered": ["aspect1", "aspect2"],
  "partial": [{"aspect": "...", "missing": "...", "suggested_query": "..."}],
  "uncovered": [{"aspect": "...", "suggested_query": "..."}]
}
```

### 3.3 Current Implementation vs. Best Practice

**Current (this project)**:
- Binary LLM judge: "SUFFICIENT" or "MISSING: <what>"
- Max 2 iterations
- Uses the same search function for gap-filling
- No per-document evaluation

**Recommended upgrades**:
1. **Structured gap analysis**: Replace binary with JSON-structured evaluation
2. **Per-document relevance grading**: Before gap analysis, score each retrieved note for relevance using the cross-encoder (already loaded for reranking)
3. **Query reformulation for gaps**: Instead of searching the raw gap description, have the LLM reformulate it as an optimal search query
4. **Passage-level refinement**: When a note is "partially relevant," extract only the relevant chunks rather than including the whole note

---

## 4. Source Grounding and Citation

### 4.1 How Production Systems Ground Claims

**NotebookLM approach**: Generate citations inline during streaming. Each citation references a specific passage (text span) in the source document, not just the document itself. The UI renders these as clickable chips that highlight the source passage.

**Perplexity approach**: Sources appear in a sidebar before the answer. Inline citations use numbered references. Each reference maps to a URL + extracted snippet. The generation model is prompted to cite as it writes.

**Academic RAG approach** (ALCE benchmark, 2024): Post-hoc citation verification using NLI. Generate the answer, then verify each claim against cited passages. This is what this project does with `VerificationService`.

### 4.2 Citation Architecture Spectrum

From least to most grounded:

1. **Document-level citation** (current): "[Note #1]" references the entire note. User must read the whole note to find supporting evidence.

2. **Passage-level citation**: "[Note #1, para 3]" references a specific paragraph or chunk. Requires chunk-level indexing.

3. **Span-level citation**: Citation highlights the exact sentence(s) in the source that support the claim. Requires extractive evidence linking.

4. **Entailment-verified citation**: Each citation is verified via NLI that the cited passage actually entails the claim. This project already does this.

### 4.3 Recommended Citation Pipeline

```
1. Retrieve notes (existing)
2. Chunk retrieved notes into passages (existing via ChunkingService)
3. During generation, prompt LLM to cite [Note #N, Chunk #M]
4. Post-generation: extract citation references
5. For each citation, extract the claim sentence from the response
6. NLI-verify: does the cited chunk entail the claim? (existing)
7. Return: citation + specific passage + entailment score
8. UI: clicking a citation highlights the specific passage in the note panel
```

The key missing piece: **step 3 (passage-level citation prompting)** and **step 7 (returning the specific passage with the citation)**. Both are achievable without new models — just prompt engineering and chunk indexing.

### 4.4 Grounding Scores

Google's Vertex AI and recent open-source work use a **grounding score** per response:

```
grounding_score = (num_grounded_claims / total_claims)
```

Where a claim is "grounded" if its NLI entailment score > 0.5 against any cited passage. This gives users a single quality signal for the whole response.

---

## 5. Late Chunking

### 5.1 Traditional Chunking (Current Approach)

Standard chunking splits documents into fixed-size or semantic chunks *before* embedding:

```
Document → Split into chunks → Embed each chunk independently → Index
```

Problem: Each chunk is embedded in isolation. A chunk that says "He went to the store" loses the context of who "He" refers to. The embedding captures the chunk's meaning in isolation, not in the context of the full document.

Current implementation in `ChunkingService`:
- Split by paragraphs/headers/lists
- Greedy merge up to 1500 chars
- Prepend title to first chunk
- Each chunk embedded independently with MiniLM-L12-v2

### 5.2 Late Chunking (Jina AI, 2024)

Late chunking reverses the order:

```
Document → Embed the FULL document as one sequence → Split embeddings into chunks → Index
```

How it works:
1. Pass the entire document through a long-context embedding model (e.g., jina-embeddings-v2, BGE-M3)
2. The transformer produces token-level embeddings that are *contextualized* by the full document
3. After the forward pass, segment the token embeddings into chunks based on the original text boundaries
4. Pool each chunk's token embeddings (mean pooling) to get chunk-level embeddings

**Why this matters**: The chunk "He went to the store" now has an embedding that *knows* "He" refers to "John" because the full document was processed together. The embedding for this chunk carries contextual information from the entire document.

### 5.3 Benefits

| Aspect | Traditional | Late Chunking |
|--------|-------------|---------------|
| Context awareness | Chunk is an island | Chunk knows its document context |
| Pronoun resolution | Lost | Preserved |
| Cross-reference | Lost | Preserved |
| Model requirement | Any embedding model | Long-context model (8K+ tokens) |
| Computation | N forward passes (N chunks) | 1 forward pass per document |
| Storage | Standard | Standard (same dimensionality) |

### 5.4 Feasibility for This Project

**Current model**: `paraphrase-multilingual-MiniLM-L12-v2` — 512 token max, not suitable for late chunking.

**Viable upgrade paths**:

1. **jina-embeddings-v2-base-en** (137M params, 8192 tokens): Supports late chunking natively. Jina provides a reference implementation. Requires ~550MB VRAM. Would fit alongside the current model stack on RTX 3060.

2. **BGE-M3** (568M params, 8192 tokens): Multi-lingual, supports dense + sparse + colbert retrieval. Late chunking compatible. Requires ~2.3GB VRAM. Tight but feasible on RTX 3060 with other models loaded.

3. **nomic-embed-text-v1.5** (137M params, 8192 tokens): Open-source, good multilingual support. Late chunking compatible via manual implementation.

**Recommendation**: jina-embeddings-v2-base-en is the sweet spot. It's specifically designed for late chunking, has reasonable VRAM requirements, and Jina provides implementation examples. However, this is a **medium-term upgrade** — the current chunking approach works well enough, and the gains from late chunking are most visible on documents with heavy cross-referencing.

### 5.5 Implementation Sketch

```python
class LateChunkingService:
    def __init__(self, model_name="jinaai/jina-embeddings-v2-base-en"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)

    def embed_chunks(self, document: str, chunk_boundaries: List[Tuple[int, int]]):
        # 1. Tokenize full document
        inputs = self.tokenizer(document, return_tensors="pt", max_length=8192)

        # 2. Forward pass on full document
        with torch.no_grad():
            outputs = self.model(**inputs)
        token_embeddings = outputs.last_hidden_state[0]  # (seq_len, hidden_dim)

        # 3. Map character boundaries to token boundaries
        # 4. Pool each chunk's token embeddings
        chunk_embeddings = []
        for char_start, char_end in chunk_boundaries:
            tok_start, tok_end = self._char_to_token_span(inputs, char_start, char_end)
            chunk_emb = token_embeddings[tok_start:tok_end].mean(dim=0)
            chunk_embeddings.append(chunk_emb)

        return torch.stack(chunk_embeddings)
```

---

## 6. Local/Self-Hosted Agentic RAG

### 6.1 Current Local LLM Landscape (2025-2026)

Models feasible on RTX 3060 12GB for agentic RAG:

| Model | Size | VRAM (Q4) | Tool-Use | Agentic Quality |
|-------|------|-----------|----------|-----------------|
| Llama 3.1 8B Instruct | 8B | ~5GB | Good | Solid for single-step, struggles with multi-step |
| Llama 3.2 3B Instruct | 3B | ~2GB | Basic | Good for simple tasks, fast |
| Mistral 7B Instruct v0.3 | 7B | ~4.5GB | Good | Good tool use, sometimes over-triggers |
| Qwen 2.5 7B Instruct | 7B | ~4.5GB | Excellent | Best tool-use at 7B class |
| Phi-3.5-mini (3.8B) | 3.8B | ~2.5GB | Moderate | Fast, good for structured output |
| Gemma 2 9B | 9B | ~6GB | Good | Strong reasoning, good grounding |
| Command-R 7B | 7B | ~4.5GB | Excellent | Built for RAG, native citations |

### 6.2 What's Feasible Locally

**Fully feasible on RTX 3060 12GB**:
- Single-step RAG with citation (current approach) ✅
- Query decomposition into 2-3 sub-queries ✅
- CRAG-style gap analysis with 2 iterations ✅
- Structured JSON output for gap analysis ✅
- Conversation summarization ✅

**Feasible with careful model selection**:
- Multi-step agent loops (keep it to 3-5 steps max, use Qwen 2.5 7B or Command-R 7B)
- Passage-level citation (prompt engineering, no extra model needed)
- Query routing (lightweight classifier or LLM-based)

**Challenging locally**:
- Full ReAct agent with open-ended tool use (8B models sometimes loop or hallucinate actions)
- Complex multi-hop reasoning over 10+ documents (context window fills quickly)
- Simultaneous generation + verification (need to serialize, can't parallel-run two LLMs)

**Not feasible locally** (need cloud or larger GPU):
- 70B+ models for high-quality multi-step reasoning
- Running multiple LLM instances concurrently
- Real-time re-embedding of large document collections

### 6.3 Ollama-Specific Patterns

Ollama provides an OpenAI-compatible API. Key patterns for agentic RAG:

**Tool calling** (Ollama 0.3+):
```python
response = await client.post("chat/completions", json={
    "model": "qwen2.5:7b",
    "messages": messages,
    "tools": [{
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "Search notes by semantic similarity",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
    }]
})
```

**Structured output** (Ollama 0.5+):
```python
response = await client.post("chat/completions", json={
    "model": "llama3.1:8b",
    "messages": messages,
    "response_format": {
        "type": "json_schema",
        "json_schema": {
            "name": "gap_analysis",
            "schema": {
                "type": "object",
                "properties": {
                    "covered": {"type": "array", "items": {"type": "string"}},
                    "gaps": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "aspect": {"type": "string"},
                            "search_query": {"type": "string"}
                        }
                    }}
                }
            }
        }
    }
})
```

**Model recommendations for this project**:
- **Primary generation**: `qwen2.5:7b` — best tool-use and structured output at this size
- **Fast classification/routing**: `phi3.5:3.8b` or `llama3.2:3b` — for query routing, sufficiency checks
- **Fallback/alternative**: `command-r:7b` — native RAG/citation support, Cohere's grounded generation

### 6.4 VRAM Budget

RTX 3060 12GB budget with current model stack:

| Component | VRAM | Notes |
|-----------|------|-------|
| Embedding (MiniLM-L12-v2) | ~0.5GB | Stays loaded |
| Reranker (ms-marco-MiniLM-L6) | ~0.1GB | On-demand |
| NLI (nli-deberta-v3-small) | ~0.2GB | On-demand |
| spaCy NER | ~0.05GB | CPU-based, negligible |
| LLM (7B Q4_K_M) | ~5GB | Managed by Ollama |
| **Total** | **~5.85GB** | **Headroom: ~6GB** |

With headroom, could add jina-embeddings-v2-base-en (~0.55GB) for late chunking while staying within budget.

---

## 7. Agent Harness for RAG

### 7.1 What Is an Agent Harness?

An agent harness is the runtime framework that:
1. Provides tools to the LLM
2. Executes tool calls
3. Manages the agent loop (thought → action → observation → thought)
4. Enforces safety constraints (max iterations, timeout, tool permissions)
5. Handles streaming of intermediate results to the UI

This is analogous to how Claude Code gives Claude tools (Bash, Read, Write, Search) and manages the execution loop.

### 7.2 Harness Architecture for This Project

```
┌─────────────────────────────────────────────┐
│                 Agent Harness                │
│                                             │
│  ┌─────────────┐    ┌───────────────────┐   │
│  │ Tool Registry│    │  Execution Loop   │   │
│  │             │    │                   │   │
│  │ search_notes│    │  1. Send tools +  │   │
│  │ search_chunk│    │     messages to   │   │
│  │ get_detail  │    │     LLM           │   │
│  │ check_gaps  │    │  2. Parse tool    │   │
│  │ verify_claim│    │     calls         │   │
│  │             │    │  3. Execute tools  │   │
│  └─────────────┘    │  4. Append results │   │
│                     │  5. Loop or finish │   │
│  ┌─────────────┐    │                   │   │
│  │  Guardrails │    └───────────────────┘   │
│  │             │                            │
│  │ max_steps: 5│    ┌───────────────────┐   │
│  │ timeout: 30s│    │  Stream Manager   │   │
│  │ max_tokens  │    │                   │   │
│  │ tool_budget │    │  status → UI      │   │
│  └─────────────┘    │  sources → UI     │   │
│                     │  delta → UI       │   │
│                     │  citations → UI   │   │
│                     └───────────────────┘   │
└─────────────────────────────────────────────┘
```

### 7.3 Tool Definitions

```python
# Tools the agent can call during the RAG loop

class RAGTools:
    """Tools available to the agentic RAG loop."""

    async def search_notes(self, query: str, max_results: int = 5) -> List[NoteResult]:
        """Semantic + keyword search over all notes."""

    async def search_chunks(self, query: str, note_ids: List[str] = None) -> List[ChunkResult]:
        """Search within specific notes at chunk/passage level."""

    async def get_note_detail(self, note_id: str) -> NoteDetail:
        """Get full content of a specific note."""

    async def check_sufficiency(self, query: str, evidence: List[str]) -> SufficiencyResult:
        """Evaluate if gathered evidence is sufficient to answer the query.
        Returns: {sufficient: bool, gaps: List[str], suggested_queries: List[str]}"""

    async def verify_claim(self, claim: str, passage: str) -> VerificationResult:
        """NLI check: does the passage support the claim?
        Returns: {verdict: str, score: float}"""
```

### 7.4 Execution Loop

```python
class AgentLoop:
    def __init__(self, tools: RAGTools, llm_client, model: str, max_steps: int = 5):
        self.tools = tools
        self.client = llm_client
        self.model = model
        self.max_steps = max_steps

    async def run(self, query: str, messages: List[Dict]) -> AsyncIterator[StreamFrame]:
        # Build tool descriptions for the LLM
        tool_defs = self._build_tool_definitions()

        for step in range(self.max_steps):
            # Yield status to UI
            yield StatusFrame(f"Step {step + 1}: Reasoning...")

            # Call LLM with tools
            response = await self.client.post("chat/completions", json={
                "model": self.model,
                "messages": messages,
                "tools": tool_defs,
                "stream": False,  # Tool-use step is non-streaming
            })

            choice = response.json()["choices"][0]
            message = choice["message"]

            # If no tool calls, the agent wants to generate the final answer
            if not message.get("tool_calls"):
                # Stream the final answer
                yield StatusFrame("Generating answer...")
                async for chunk in self._stream_generation(messages):
                    yield chunk
                return

            # Execute tool calls
            messages.append(message)  # Add assistant message with tool calls
            for tool_call in message["tool_calls"]:
                func_name = tool_call["function"]["name"]
                args = json.loads(tool_call["function"]["arguments"])

                yield StatusFrame(f"Calling {func_name}({args.get('query', '')[:50]}...)")

                result = await self._execute_tool(func_name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result),
                })

                # Yield intermediate results to UI
                if func_name == "search_notes":
                    yield SourcesFrame(result)

        # Max steps reached — generate best-effort answer
        yield StatusFrame("Max steps reached, generating best-effort answer...")
        async for chunk in self._stream_generation(messages):
            yield chunk
```

### 7.5 Hybrid Approach (Recommended for This Project)

A full agent loop adds latency (each step = 1 LLM call). For local models, the pragmatic approach is **hybrid**: use the existing procedural pipeline for retrieval, but add an agent-style evaluation and correction layer.

```
Phase 1 (Procedural — fast, deterministic):
  - Query decomposition
  - Multi-signal retrieval (semantic + BM25 + entity + chunks)
  - RRF fusion + reranking

Phase 2 (Agentic — LLM-driven, 1-2 steps):
  - Evaluate retrieved notes (structured gap analysis)
  - If gaps found: targeted retrieval + re-evaluation
  - If sufficient: proceed to generation

Phase 3 (Generation + Verification):
  - Stream response with passage-level citations
  - Post-hoc NLI verification
  - Return grounding score
```

This preserves the fast retrieval pipeline (no LLM calls needed for phase 1) while adding agentic intelligence where it matters most (evaluation and gap-filling).

---

## 8. Architectural Recommendations for This Project

### 8.1 Priority 1: Structured Gap Analysis (CRAG Upgrade)

**Current**: Binary "SUFFICIENT/MISSING" with free-text gap description.
**Proposed**: Structured JSON evaluation with per-aspect coverage.

Change `QueryService.retrieve_with_gap_analysis()`:

```python
GAP_ANALYSIS_PROMPT = """Analyze if these notes answer the question.

Question: {query}
Notes:
{notes_brief}

Respond in JSON:
{{
  "sufficient": true/false,
  "covered_aspects": ["aspect1", "aspect2"],
  "gaps": [
    {{"aspect": "what's missing", "search_query": "optimized query to find it"}}
  ],
  "confidence": 0.0-1.0
}}"""
```

Use Ollama's structured output (`response_format: json_schema`) to guarantee valid JSON. This replaces regex parsing and gives richer signal for gap-filling.

**Effort**: Small. Modify `query_service.py` only. Leverage existing Ollama structured output.

### 8.2 Priority 2: Passage-Level Citations

**Current**: Citations reference whole notes: `[Note #1]`
**Proposed**: Citations reference specific chunks: `[Note #1, §2]`

Implementation:
1. When building context, include chunk boundaries in the note formatting:
   ```
   --- Note #1 ---
   Title: Japan Trip
   §1: We flew into Tokyo on March 15...
   §2: Kyoto was the highlight. The temples...
   §3: Budget was about $3000 total...
   --- End Note #1 ---
   ```
2. Update system prompt: "Cite specific sections: [Note #1, §2]"
3. Update `citation_service.py` regex to parse section references
4. Return the cited passage with each citation for UI highlighting

**Effort**: Medium. Touches `context_builder.py`, `citation_service.py`, system prompts, and frontend citation rendering.

### 8.3 Priority 3: Query Router

**Current**: All queries go through the full retrieval pipeline.
**Proposed**: Classify query type first, route to appropriate strategy.

```python
class QueryRouter:
    ROUTES = {
        "greeting": {"retrieve": False},
        "follow_up": {"retrieve": True, "strategy": "context_only"},
        "factual": {"retrieve": True, "strategy": "full_pipeline"},
        "comparison": {"retrieve": True, "strategy": "decompose"},
        "general_knowledge": {"retrieve": True, "strategy": "light"},
    }

    async def route(self, query: str, conversation: List[Dict]) -> RouteDecision:
        # Use lightweight model (phi3.5 or rule-based) to classify
        ...
```

This can start rule-based (keyword heuristics, similar to existing `_is_complex`) and upgrade to LLM-based later.

**Effort**: Small-medium. New service, integrated into `retrieval_orchestrator.py`.

### 8.4 Priority 4: Cross-Encoder Document Grading (Pre-Generation Filter)

**Current**: Retrieved notes go directly to generation.
**Proposed**: Grade each retrieved note for relevance before stuffing into context.

The cross-encoder reranker is already loaded. Use it as a relevance gate:

```python
# In retrieval_orchestrator.py, after reranking:
if self.reranker:
    scores = self.reranker.score(query, notes)
    notes = [n for n, s in zip(notes, scores) if s > RELEVANCE_THRESHOLD]
```

This filters out marginally relevant notes that dilute context and trigger hallucination.

**Effort**: Small. Threshold tuning needed.

### 8.5 Priority 5: Agent Harness (Full Agentic Mode)

**Current**: Procedural pipeline.
**Proposed**: Optional agentic mode for complex queries.

Only activate for complex queries (multi-faceted, comparison, "tell me everything about..."). Use the hybrid approach from section 7.5.

Implementation:
1. Add `AgentLoop` class with tool definitions
2. Add `RAGTools` wrapper around existing services
3. Route complex queries to agent mode, simple queries to fast pipeline
4. Stream intermediate status ("Searching for travel notes...", "Found 3 relevant notes, checking for gaps...")

**Effort**: Large. New module, significant integration work. Recommended for Phase 8+.

### 8.6 Priority 6: Late Chunking (Model Upgrade)

**Current**: Independent chunk embeddings with MiniLM-L12-v2.
**Proposed**: Late chunking with jina-embeddings-v2-base-en.

This is a medium-term investment. The main benefit is better retrieval quality for notes with cross-references, pronouns, and continuation patterns. Worth implementing when the current chunking pipeline's quality becomes a bottleneck.

**Effort**: Large. New embedding model, new chunking pipeline, re-indexing.

---

## 9. Implementation Roadmap

| Phase | Feature | Effort | Impact | Dependencies |
|-------|---------|--------|--------|--------------|
| **8A** | Structured gap analysis (JSON) | 1-2 days | High | Ollama structured output |
| **8A** | Cross-encoder relevance gate | 0.5 days | Medium | Existing reranker |
| **8B** | Passage-level citations | 2-3 days | High | ChunkingService refactor |
| **8B** | Query router (rule-based) | 1 day | Medium | New service |
| **8C** | Agent harness (opt-in for complex queries) | 3-5 days | High | Tool-use capable model (qwen2.5) |
| **8C** | Streaming status indicators | 1-2 days | Medium | Frontend work |
| **8D** | Late chunking (model upgrade) | 3-5 days | Medium | New embedding model |
| **8D** | Grounding score per response | 1 day | Medium | Existing NLI |

---

## 10. Contradictions and Uncertainties

### Contradictions in the Literature

1. **Agent loops vs. latency**: Full agentic loops (ReAct-style) improve answer quality but add 2-5x latency. For local models, each step costs 2-5 seconds. The hybrid approach (procedural retrieval + agentic evaluation) is a pragmatic compromise, but it limits the system's ability to do truly open-ended exploration.

2. **Late chunking hype vs. reality**: Jina AI's benchmarks show 5-10% improvement in retrieval quality with late chunking. But these benchmarks use datasets with heavy cross-document references. For short Google Keep notes (typically self-contained), the improvement may be smaller. Worth measuring before committing.

3. **Small model tool-use reliability**: Ollama's tool-use with 7B models works well for simple cases but can be unreliable for complex multi-tool plans. Qwen 2.5 7B is the best option, but even it occasionally generates malformed tool calls or enters loops. Guardrails (max steps, timeout, fallback to procedural) are essential.

### Open Questions

1. **Optimal number of CRAG iterations**: Literature suggests 2-3. This project uses 2. Empirical testing with actual Google Keep queries would determine the right number.

2. **Cross-encoder vs. LLM for document grading**: The cross-encoder is fast (~10ms per pair) but gives a single relevance score. An LLM call gives richer evaluation but costs 2-3 seconds. For local deployment, cross-encoder grading is more practical.

3. **When to upgrade embedding model**: The current MiniLM-L12-v2 is fast and multilingual. Upgrading to jina-embeddings-v2 or BGE-M3 brings late chunking and longer context, but doubles VRAM usage. The trigger should be measured retrieval quality on a test set, not theoretical benefits.

---

## Sources and References

1. **CRAG Paper**: Yan et al., "Corrective Retrieval Augmented Generation" (arXiv:2401.15884, Jan 2024)
2. **Late Chunking**: Jina AI, "Late Chunking in Long-Context Embedding Models" (jina.ai/news, 2024)
3. **LangGraph Agentic RAG**: LangChain blog, "Agentic RAG with LangGraph" (blog.langchain.dev, 2024)
4. **LlamaIndex Agentic RAG**: LlamaIndex blog, "Agentic RAG with LlamaIndex" (llamaindex.ai/blog, 2024)
5. **ALCE Benchmark**: Gao et al., "Enabling Large Language Models to Generate Text with Citations" (ACL 2023, updated 2024)
6. **NotebookLM**: Google, "NotebookLM" — architecture inferred from product behavior and Google I/O 2024 presentations
7. **Perplexity Pro Search**: Architecture inferred from product behavior and Perplexity blog posts (2024-2025)
8. **Storm**: Shao et al., "Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models" (Stanford, 2024)
9. **Ollama Tool Calling**: Ollama documentation, structured output and tool-use support (ollama.com/blog, 2024-2025)
10. **Qwen 2.5 Technical Report**: Alibaba, "Qwen2.5 Technical Report" (2024) — tool-use benchmarks
11. **BGE-M3**: Chen et al., "BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity" (arXiv:2402.03216, 2024)
12. **Command-R**: Cohere, "Command R — A Scalable LLM Built for Business" — native RAG/citation architecture
13. **Self-RAG**: Asai et al., "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection" (arXiv:2310.11511, 2023)

---

*This report is based on published research, product analysis, and architectural patterns documented through early 2025. Specific model capabilities and Ollama features should be verified against current releases at time of implementation.*
