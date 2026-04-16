# Deep Research: Document Ingestion, Retrieval, Foundation Models, and Audio Generation Algorithms

*Research date: 2026-04-16*

---

## Table of Contents

1. [Document Ingestion and Parsing](#1-document-ingestion-and-parsing)
   - [OCR Engines](#11-optical-character-recognition-ocr)
   - [ASR / Whisper](#12-automatic-speech-recognition-asr)
2. [Chunking and Retrieval](#2-chunking-and-retrieval-algorithms)
   - [Hybrid RAG](#21-hybrid-rag)
   - [Late Chunking](#22-late-chunking)
   - [Cosine Similarity & ANN](#23-cosine-similarity--ann-optimization)
   - [TF-IDF vs BM25](#24-tf-idf-vs-bm25)
   - [Cross-Encoder Reranking](#25-cross-encoder-reranking)
3. [Foundation Models & Agentic Workflows](#3-foundation-model-architecture--agentic-workflows)
   - [Sparse MoE](#31-sparse-mixture-of-experts-moe)
   - [Prompt Decomposition](#32-prompt-decomposition)
   - [Gap Analysis](#33-gap-analysis--adaptive-retrieval)
4. [Audio Generation](#4-audio-generation-algorithms)
   - [Disfluency Injection](#41-disfluency-injection)
   - [Text-to-Semantic Modeling](#42-text-to-semantic-modeling-w2v-bert--soundstream)
   - [Non-Autoregressive Parallel Decoding](#43-non-autoregressive-parallel-decoding-maskgit--soundstorm)
   - [Residual Vector Quantization](#44-residual-vector-quantization-rvq)
   - [Bidirectional Attention](#45-bidirectional-attention-in-audio-generation)

---

## 1. Document Ingestion and Parsing

### 1.1 Optical Character Recognition (OCR)

#### Engine Comparison

| Engine | Printed Text | Handwriting | Multilingual | GPU VRAM | Speed (RTX 3060) | Best For |
|---|---|---|---|---|---|---|
| **Tesseract 5** | Good | Poor | 100+ langs | 0 (CPU) | 1-3 pages/s | Simple screenshots |
| **EasyOCR** | Good | Fair | 80+ langs | ~2 GB | 3-6 pages/s | Quick setup, multilingual |
| **PaddleOCR v5** | Excellent | Good | 111 langs | ~2-3 GB | 5-15 pages/s | **Primary recommendation** |
| **TrOCR-large** | Good | Excellent | English | ~2.5 GB | 30-60 lines/s | **Handwriting specialist** |
| **Surya** | Excellent | Good | 90+ langs | 4-8 GB* | 2-4 pages/s | Complex document structure |
| **docTR** | Good | Fair | 30+ langs | ~2-3 GB | 3-8 pages/s | Cleanest Python API |

*Surya with reduced batch sizes: `DETECTOR_BATCH_SIZE=4`, `RECOGNITION_BATCH_SIZE=16`

#### Detailed Analysis

**PaddleOCR v5** (Baidu, Apache 2.0): Three-stage pipeline — DBNet++ detection, direction classification, PP-OCRv4Rec recognition. PP-OCRv5 reports 13% accuracy improvement over v4, scoring 94.5% on OmniDocBench. Server models total ~180MB. Handles tables, multi-column layouts, and mixed scripts.

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=True, show_log=False)

def extract_text(image_path: str) -> str:
    result = ocr.ocr(image_path, cls=True)
    if not result or not result[0]:
        return ""
    return "\n".join(line[1][0] for page in result for line in page)
```

**TrOCR-large-handwritten** (Microsoft, HuggingFace): Vision Encoder-Decoder (BEiT + RoBERTa). Achieves CER of 2.89% on IAM handwriting dataset — best open-source English handwriting OCR. 558M params, ~2.5GB VRAM FP16. Recognition-only — needs separate detector (PaddleOCR's DBNet).

```python
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
import torch

processor = TrOCRProcessor.from_pretrained('microsoft/trocr-large-handwritten')
model = VisionEncoderDecoderModel.from_pretrained(
    'microsoft/trocr-large-handwritten'
).to('cuda').half()

def recognize_handwritten(crop):  # PIL Image
    pixels = processor(crop, return_tensors="pt").pixel_values.to('cuda').half()
    with torch.no_grad():
        ids = model.generate(pixels)
    return processor.batch_decode(ids, skip_special_tokens=True)[0]
```

**Surya** (GPL-3.0, free for personal use): Document-first toolkit — layout detection, reading order, OCR, table parsing, LaTeX formula recognition. Uses specialized transformers totaling ~2-3GB on disk. Needs reduced batch sizes for RTX 3060.

#### Recommended Approach

Two-stage routing for Google Keep note images:
1. **PaddleOCR v5** as primary engine for all images
2. Low-confidence regions (score < 0.6) routed to **TrOCR-large-handwritten**
3. Optional: **Surya** for notes containing document screenshots (tables, forms)

Combined VRAM: PaddleOCR (~2.5GB) + TrOCR (~2.5GB) = ~5GB

---

### 1.2 Automatic Speech Recognition (ASR)

#### Whisper Model Variants

| Model | Params | VRAM | Speed vs large | WER |
|---|---|---|---|---|
| tiny | 39M | ~1 GB | ~10x | ~18-20% |
| base | 74M | ~1 GB | ~7x | ~14-16% |
| small | 244M | ~2 GB | ~4x | ~11-13% |
| medium | 769M | ~5 GB | ~2x | ~8-9% |
| large-v3 | 1,550M | ~10 GB | 1x | **7.44%** |
| **large-v3-turbo** | **809M** | **~6 GB** | **~8x** | **7.83%** |

**large-v3-turbo** is the sweet spot for RTX 3060: same encoder as large-v3 but decoder pruned from 32 to 4 layers. Only +0.39 WER points at 8x the speed.

#### Runtime Comparison

| Runtime | Backend | VRAM (large-v3-turbo) | Speed vs Original |
|---|---|---|---|
| OpenAI Whisper | PyTorch | ~6 GB | 1x |
| **faster-whisper (FP16)** | **CTranslate2** | **~3.5 GB** | **~4x** |
| faster-whisper (INT8) | CTranslate2 | ~2.5 GB | ~3.5x |
| faster-whisper (batched) | CTranslate2 | ~4.5 GB | ~15-20x |
| whisper.cpp (Q5_0) | GGML/CUDA | ~2 GB | ~3-4x |

**faster-whisper** is the clear winner: 4x faster than original, half the VRAM, same accuracy.

**Benchmark** (RTX 3070 Ti, comparable to 3060): 13 min audio in 17 seconds with batched FP16 (batch_size=8).

```python
from faster_whisper import WhisperModel, BatchedInferencePipeline

model = WhisperModel("large-v3-turbo", device="cuda", compute_type="int8_float16")
batched = BatchedInferencePipeline(model=model)

def transcribe(audio_path: str) -> str:
    segments, info = batched.transcribe(audio_path, batch_size=8,
                                         language=None, vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments)
```

**For Google Keep voice memos**: Typically 5-120s `.m4a`/`.3gp` files. At ~150-200x real-time on RTX 3060, a 60s memo processes in under 1 second. Full corpus (assuming 2% of 5000 notes have audio, avg 30s) = ~3000s audio → under 30 seconds with batching.

---

## 2. Chunking and Retrieval Algorithms

### 2.1 Hybrid RAG

#### The Problem with Linear Score Blending

The current 70/30 semantic/keyword split breaks because cosine similarity scores and BM25/keyword scores live in completely different numerical ranges. A highly relevant BM25 result at 0.3 gets blended with an irrelevant cosine result at 0.85, producing misleading rankings. This is a fundamental incompatibility, not a tuning problem.

#### Reciprocal Rank Fusion (RRF) — The Industry Standard

Every major hybrid system (Qdrant, Weaviate, Azure AI Search) converges on RRF:

```
score(d) = Σ 1/(k + rank(d))  per ranked list, k=60
```

Only rank positions matter, not raw score magnitudes. Scale-agnostic, no normalization needed.

```python
def rrf_merge(dense_results, sparse_results, k=60):
    scores = {}
    for rank, (doc_id, _) in enumerate(dense_results):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
    for rank, (doc_id, _) in enumerate(sparse_results):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

#### System Implementations

- **Weaviate**: `alpha` parameter (0.0 = pure BM25, 1.0 = pure vector, default 0.75). Runs BM25 and ANN in parallel, merges with RRF.
- **Qdrant 1.10+**: `prefetch` + `fusion: rrf` query structure. Native sparse vector support for BGE-M3 sparse.
- **Milvus**: Multi-vector hybrid with `WeightedRanker` or `RRFRanker`.

**Recommendation**: Replace the 70/30 linear merge with RRF. Small code change, significant robustness improvement.

---

### 2.2 Late Chunking

#### What It Is (Jina AI, arXiv:2409.04701)

Reverses the standard chunk-then-embed pipeline:

- **Standard**: Split text → embed each chunk independently → store vectors
- **Late chunking**: Embed full document through transformer → get token-level contextual embeddings → mean-pool per chunk → store vectors

Each chunk's embedding retains global document context. A pronoun in chunk 3 referencing a noun in chunk 1 preserves cross-chunk semantics.

#### Benchmarks (nDCG@10)

| Dataset | Naive Chunking | Late Chunking | Gain |
|---|---|---|---|
| NFCorpus | 23.46% | 29.98% | **+6.5%** |
| SciFact | 64.20% | 66.10% | +1.9% |
| TREC-COVID | 63.36% | 64.70% | +1.3% |

#### BGE-M3 Compatibility

The technique is model-agnostic. BGE-M3 has 8192-token context window and outputs per-token embeddings before final pooling. Implementation:
1. Feed full note through BGE-M3
2. Access token-level hidden states from last transformer layer
3. Mean-pool over token ranges for each chunk boundary
4. Store per-chunk vectors

For ~5000 personal notes, most fit in a single BGE-M3 pass (8192 tokens ≈ ~6000 words). Benefit is highest for notes >200 tokens with internal cross-references.

---

### 2.3 Cosine Similarity & ANN Optimization

#### At 5000 Notes, Brute Force is Optimal

- Memory: `5000 × 1024 × 4 bytes = 20.48 MB`
- numpy brute-force: `query @ embeddings.T` takes **< 2ms on CPU**, sub-millisecond on GPU
- FAISS documentation recommends brute-force for datasets under ~1M vectors

| Dataset Size | Recommendation |
|---|---|
| < 100K | Brute force (numpy, FAISS Flat) |
| 100K-1M | IVFFlat or HNSW |
| > 1M | IVFFlat + PQ, or HNSW with tuned ef_construction |

FAISS GPU on RTX 3060 provides 5-10x speedup — irrelevant when CPU search is already <2ms. **No change needed.**

---

### 2.4 TF-IDF vs BM25

#### BM25 is Strictly Better for Retrieval

BM25 adds two critical improvements over TF-IDF:
1. **Term frequency saturation** (k1=1.2): `tf / (tf + k1)` — prevents term-stuffing
2. **Document length normalization** (b=0.75): penalizes long documents

BM25 outperforms TF-IDF by 3-8% nDCG@10 across BEIR datasets.

#### BGE-M3 Makes Both Redundant

BGE-M3's `return_sparse=True` outputs learned token weights (SPLADE-like) at zero additional cost during dense encoding. These sparse vectors match or beat BM25 for short-to-medium notes, with consistent tokenization (same XLM-RoBERTa tokenizer as dense).

**Recommendation**: Use BGE-M3 sparse `lexical_weights` directly. No separate BM25/TF-IDF index needed.

#### Libraries (if you need standalone BM25)

| Library | Pros | Cons |
|---|---|---|
| rank_bm25 | Simple API | Slow on large corpora |
| **bm25s** | 10-100x faster (Numba), sparse arrays | Newer |
| pyterrier | Full IR pipeline | Heavy, Java backend |

---

### 2.5 Cross-Encoder Reranking

#### Model Comparison

| Model | Params | VRAM (FP16) | Speed (V100) | Quality |
|---|---|---|---|---|
| **ms-marco-MiniLM-L6-v2** | **22.7M** | **~46MB** | **1,800 docs/sec** | NDCG@10: 74.30 |
| ms-marco-MiniLM-L12-v2 | 33.4M | ~67MB | ~900 docs/sec | 74.31 |
| **BAAI/bge-reranker-v2-m3** | **567M** | **~1.1GB** | ~100-150 docs/sec | BEIR SOTA |
| Cohere Rerank | API-only | N/A | ~200ms API | Highest quality |

#### RTX 3060 Latency

- **MiniLM-L6-v2**: Top-100 rerank ~80-100ms (RTX 3060 ≈ 60-70% of V100 throughput)
- **bge-reranker-v2-m3**: Top-100 rerank ~400-700ms

**Standard practice**: Retrieve top-100, rerank to top-10. Going beyond 200 candidates gives diminishing returns.

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2', device='cuda')

def rerank(query, candidates, top_k=10):
    pairs = [(query, doc["content"]) for doc in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in ranked[:top_k]]
```

#### VRAM Budget (All Models Simultaneous)

| Model | VRAM |
|---|---|
| BGE-M3 (existing) | ~1.1 GB |
| SigLIP (existing) | ~0.8 GB |
| MiniLM-L6-v2 reranker | ~46 MB |
| **Total** | **~2.0 GB** |

Fits trivially on 12GB with room for Ollama LLM.

---

## 3. Foundation Model Architecture & Agentic Workflows

### 3.1 Sparse Mixture-of-Experts (MoE)

#### How It Works

Each transformer layer replaces the dense FFN with N independent expert FFNs + a router network. The router selects top-k experts (typically k=2) per token. Only selected experts process the token; outputs are combined as weighted sum.

Mixtral 8x7B: 46.7B total parameters, **12.9B active per token**. 32 layers, 8 experts/layer, top-2 routing.

#### VRAM Reality on RTX 3060 12GB

| Mixtral Quantization | File Size | Peak RAM |
|---|---|---|
| Q2_K | 15.64 GB | 18.14 GB |
| Q4_K_M | 26.44 GB | 28.94 GB |

**Mixtral 8x7B does not fit on RTX 3060.** Even Q2_K (most aggressive, lossy) needs 15.64GB for weights alone. CPU+GPU split offloading is possible (~13 of 32 layers on GPU) but yields only 2-6 tokens/second — unusable for streaming chat.

#### MoE Models That Actually Fit

**Qwen1.5-MoE-A2.7B**: 14.3B total, 2.7B active. Q4_K ≈ ~7-8GB. Fits with room for context. Quality similar to Qwen1.5-7B at 1.74x faster inference. **The only practical MoE option for 12GB.**

Ollama supports all MoE models natively: `ollama pull mixtral:8x7b`, `ollama run qwen:1.5-moe`.

#### Verdict

For streaming chat on RTX 3060, **Llama 3 8B Q4_K_M (~4.5GB, 30-50 t/s) remains the best option.** MoE adds no meaningful quality gain for short-context RAG synthesis. The benefit shows in knowledge-breadth and coding tasks, not personal notes retrieval.

---

### 3.2 Prompt Decomposition

#### What It Is

Breaking a complex query into targeted sub-queries, each retrieved independently, then synthesized.

**Example**: "Compare what I wrote about exercise in January vs March"
- Sub-query 1: "What did I write about exercise in January?"
- Sub-query 2: "What did I write about exercise in March?"

#### Implementation Patterns

1. **LlamaIndex SubQuestionQueryEngine**: Question generator LLM call → parallel sub-query retrieval → synthesis LLM call
2. **LangChain MultiQueryRetriever**: Generates N alternative phrasings (not sub-questions), retrieves each, deduplicates via RRF
3. **Step-Back Prompting**: Generate abstract "step-back question" first, retrieve broad context, then answer specific question

#### Latency on RTX 3060

| Step | Time |
|---|---|
| Query classification LLM call | ~0.3-0.5s |
| Sub-question generation LLM call | ~0.5-0.8s |
| 2x BGE-M3 embedding | ~0.1s each |
| 2x vector search (5K notes) | ~0.02s each |
| Final synthesis LLM (streaming) | ~1-3s to first token |
| **Total overhead** | **~1.0-1.5s additional** |

**Recommendation**: Gate decomposition — only for queries >10 words or with temporal/comparative language. Simple queries go direct.

---

### 3.3 Gap Analysis / Adaptive Retrieval

#### What It Solves

Standard RAG does one retrieval pass and blindly trusts results. Gap analysis evaluates whether retrieved notes are sufficient, triggering more retrieval when needed.

#### Key Approaches

**FLARE** (arXiv:2305.06983): During generation, tentatively generate next sentence → check token probabilities → if low confidence, use sentence as retrieval query → retrieve → regenerate with context. Best for long synthesis outputs.

**Self-RAG** (arXiv:2310.11511): Fine-tuned model emits reflection tokens: `[Retrieve]` (should I?), `[ISREL]` (relevant?), `[ISSUP]` (supports claim?), `[ISUSE]` (useful overall?). Requires Self-RAG fine-tuned weights (7B/13B on HuggingFace), not standard Ollama models.

**CRAG** (arXiv:2401.15884): Model-agnostic wrapper. Retrieve → evaluate confidence → high=proceed, medium=extract key sentences, low=trigger supplementary search or admit "notes don't contain this info."

**Iter-RetGen** (arXiv:2305.15294): Simple iterative — generate → use output as new query → retrieve again → regenerate. Practical for 2-3 iterations.

#### Practical Implementation

```python
async def adaptive_retrieve(query, notes_index, llm, max_iterations=2):
    chunks = await retrieve(query, notes_index, top_k=5)
    
    for i in range(max_iterations):
        gap_result = await llm.generate(f"""
            Query: {query}
            Context: {format_chunks(chunks)}
            Is this sufficient to answer? JSON: {{"sufficient": bool, "missing": str|null}}
        """)
        if gap_result["sufficient"]:
            break
        more = await retrieve(gap_result["missing"], notes_index, top_k=3)
        chunks = deduplicate(chunks + more)
    
    return chunks
```

Each iteration: ~0.6-1.0s (1 LLM call + 1 retrieval). 2-iteration loop adds ~1.2-2.0s pre-streaming.

**Low-confidence threshold**: If after 2 iterations best cosine similarity < 0.35, surface "Your notes don't contain information about this" rather than hallucinating.

---

## 4. Audio Generation Algorithms

*Note: These algorithms originate from Google Research (AudioLM/SoundStorm) and Meta AI (EnCodec). They are not directly used in the vibe search app but are documented here for reference.*

### 4.1 Disfluency Injection

**What it is**: Deliberately inserting natural speech disfluencies ("um", "uh", pauses, false starts, repetitions) into TTS output to make it sound conversational rather than read-aloud.

**Why it matters**: Real human speech is 6-10% disfluent by token count. The absence of disfluency is a strong "uncanny valley" cue.

**Approaches**:
- **Rule-based** (Google Duplex): Insert at unit-stitching boundaries and processing delays. Finite-state machine places disfluencies before content words, at clause boundaries.
- **Neural/learned**: BERT-based token classifier trained on spontaneous speech corpora (Switchboard, AMI) predicts disfluency placement. Prosody model learns characteristic flat/falling F0 of "um".
- **End-to-end** (SoundStorm): If you include "um" in input text, the acoustic model produces natural-sounding disfluency because it was trained on spontaneous speech.

**Open-source**: **Bark** (Suno AI, MIT) accepts `[laughter]`, `[sighs]`, hesitation markers, converting them to natural audio. Runs on RTX 3060 at ~0.8x realtime FP16.

**Papers**: Google Duplex (2018), SPEAR-TTS (arXiv:2301.03540)

---

### 4.2 Text-to-Semantic Modeling (w2v-BERT / SoundStream)

#### The AudioLM Two-Tokenizer Architecture

Audio generation requires modeling both long-term structure (grammar, melody, accent consistency) and fine acoustic details (sibilance, room reverb). AudioLM (arXiv:2209.03143) uses two tokenizers:

**Semantic tokens** (w2v-BERT, arXiv:2108.06209):
- 0.6B Conformer trained with contrastive + masked prediction losses on unlabeled audio
- Downsamples 640x → 25 tokens/second at 250 bps
- Layer 7 hidden states → k-means (K=1024) → discrete tokens
- Encodes: phonemic content, prosody. Does NOT encode: speaker identity, room acoustics
- WER 3.4% from semantic tokens vs 2.5% from original audio — faithful content representation

**Acoustic tokens** (SoundStream, IEEE TASLP 2022):
- Fully convolutional encoder-decoder with RVQ
- 50 frames/second, Q=12 codebooks, N=1024 entries → 6 kbps
- Coarse levels (1-4): speaker identity, recording conditions (ViSQOL 3.3)
- Fine levels (5-12): perceptual detail (ViSQOL 3.3 → 3.9)

#### Three-Stage AudioLM Pipeline

1. **Semantic model** (0.3B Transformer): Autoregressive generation of semantic tokens. Captures grammar, meaning.
2. **Coarse acoustic model** (0.3B Transformer): Conditioned on semantic tokens, generates Q'=4 coarse RVQ levels. Captures speaker identity.
3. **Fine acoustic model** (0.3B Transformer): Conditioned on coarse tokens, generates remaining 8 levels. Adds detail.

Total: ~0.9B parameters. Generation is slow (autoregressive over 600 tokens/second).

**Open source**: `lucidrains/audiolm-pytorch` (MIT), `facebookresearch/encodec` (MIT), `descriptinc/descript-audio-codec` (MIT)

---

### 4.3 Non-Autoregressive Parallel Decoding (MaskGIT / SoundStorm)

#### The Speed Problem

AudioLM's autoregressive stages generate 600 tokens/second → 30s audio = 18,000 sequential steps. Minutes on TPU.

**SoundStorm** (arXiv:2305.09636) replaces stages 2+3, achieving **100x speedup**: 30s audio in 0.5 seconds on TPU-v4.

#### MaskGIT Mechanism (arXiv:2202.04200)

Instead of left-to-right prediction, uses iterative masked prediction:
1. Start with all tokens masked
2. Forward pass: predict all masked tokens simultaneously (bidirectional attention)
3. Retain top-p fraction by confidence (cosine schedule)
4. Re-mask low-confidence positions
5. Repeat until all filled

#### SoundStorm's RVQ Extension

Key insight: fine RVQ levels are conditionally independent given coarse levels.

**Architecture**: 350M Conformer (12 layers, 16 heads, dim 1024). Sums embeddings of all Q tokens per frame → sequence length = T frames (not T×Q). Separate prediction heads per RVQ level.

**Decoding**:
1. Level 1: 16 MaskGIT iterations with confidence scheduling
2. Levels 2-12: Single greedy pass each (one forward pass per level)
3. Total: 27 forward passes for 18,000 tokens

**Conformer architecture**: FFN → Multi-Head Self-Attention → Convolution Module (depthwise conv kernel=5) → FFN. "Macaron-style" with half-step residuals. The convolution captures local periodic structure (pitch, formants) while bidirectional attention handles long-range consistency.

**Open source**: `lucidrains/soundstorm-pytorch` (MIT). No official Google release.

---

### 4.4 Residual Vector Quantization (RVQ)

#### How It Works

Cascading VQ codebooks, each encoding the residual of the previous:

```
Level 1: q₁ = nearest(x, C₁);          r₁ = x - C₁[q₁]
Level 2: q₂ = nearest(r₁, C₂);         r₂ = r₁ - C₂[q₂]
...
Level Q: qQ = nearest(r_{Q-1}, CQ)

Reconstruction: x̂ = C₁[q₁] + C₂[q₂] + ... + CQ[qQ]
```

Bitrate: Q × log₂(N) bits per frame. With Q=12, N=1024: 120 bits/frame. At 50 fps: 6 kbps (vs MP3 128 kbps = 21x compression).

#### Training Details

- **Straight-Through Estimator (STE)**: Gradient flows through quantization as identity (argmin has zero gradient)
- **Codebook loss**: Moves centroids toward encoder output
- **EMA updates**: More stable than gradient descent for codebook entries
- **Quantizer dropout** (SoundStream): Randomly drop fine levels during training, forcing encoder to pack info into coarse levels. Enables variable bitrate from single model.

#### Key Codecs

| Codec | Org | Sample Rate | Levels | Bitrate | License |
|---|---|---|---|---|---|
| SoundStream | Google | 16/24 kHz | 12 | 3-18 kbps | Not released |
| EnCodec | Meta | 24/48 kHz | 8/16 | 1.5-24 kbps | MIT |
| **DAC (RVQGAN)** | **Descript** | **16/24/44.1 kHz** | **12** | **8 kbps** | **MIT** |

DAC achieves ~90x compression at 44.1 kHz with state-of-the-art fidelity. Recommended for new work.

**Libraries**: `facebookresearch/encodec`, `descriptinc/descript-audio-codec`, `lucidrains/vector-quantize-pytorch`

---

### 4.5 Bidirectional Attention in Audio Generation

#### Why Audio Benefits from Bidirectional Context

Standard autoregressive models use causal attention (token t only sees positions 1..t-1). MaskGIT/SoundStorm use **bidirectional attention** — each token attends to all positions including future ones.

This enables:
- **Parallel prediction**: All masked positions predicted simultaneously
- **Global speaker consistency**: SoundStorm generates entire 30s acoustic matrix in one pass; bidirectional attention at every layer accesses the voice prompt regardless of position
- **Better fine-level decoding**: Fine RVQ tokens at frame 10 can use context from frame 25 (and vice versa) to maintain consistency

**Empirical result**: SoundStorm's speaker embedding cosine similarity with prompt is stable across 30s. AudioLM's autoregressive approach shows measurable degradation after ~15s.

**Rotary Positional Embeddings (RoPE)**: SoundStorm uses RoPE (arXiv:2104.09864) — encodes position as rotation in complex plane, giving dot products natural relative-position dependence. Generalizes better than absolute positional embeddings for variable-length sequences.

**Contrast with VALL-E** (arXiv:2301.02111): Uses autoregressive for level 1 (too important to parallelize) + non-autoregressive bidirectional for levels 2-8. SoundStorm improves by using 16 MaskGIT iterations for level 1 instead of full autoregression, recovering most quality.

---

## Audio Algorithms: Relevance to Vibe Search

| Algorithm | Run on RTX 3060? | Practical Use Case |
|---|---|---|
| Disfluency Injection | Yes (Bark, ~0.8x realtime) | "Read note aloud" with natural voice |
| Semantic Tokenization | Yes (HuBERT inference, ~300MB) | Index voice memos by content |
| AudioLM full pipeline | Marginal (3x 0.3B, slow) | Not practical without quantization |
| SoundStorm | Yes (350M Conformer, inference) | Fast TTS acoustic stage |
| RVQ/DAC | Yes (real-time easily) | Compress audio notes |
| Bidirectional Attention | N/A (design choice) | Inherent in non-autoregressive TTS |

Most actionable for the app: (1) Whisper/HuBERT for semantic embedding of audio notes, (2) DAC for efficient storage, (3) Bark or Coqui XTTS for TTS playback.

---

## Key Papers Reference

| Topic | Paper | ID |
|---|---|---|
| Late Chunking | Jina AI | arXiv:2409.04701 |
| RRF Fusion | Cormack et al. | SIGIR 2009 |
| FLARE | Jiang et al. | arXiv:2305.06983 |
| Self-RAG | Asai et al. | arXiv:2310.11511 |
| CRAG | Yan et al. | arXiv:2401.15884 |
| AudioLM | Borsos et al. | arXiv:2209.03143 |
| SoundStorm | Borsos et al. | arXiv:2305.09636 |
| MaskGIT | Chang et al. | arXiv:2202.04200 |
| Conformer | Gulati et al. | arXiv:2005.08100 |
| w2v-BERT | Chung et al. | arXiv:2108.06209 |
| EnCodec | Défossez et al. | arXiv:2210.13438 |
| DAC/RVQGAN | Kumar et al. | arXiv:2306.06546 |
| VALL-E | Wang et al. | arXiv:2301.02111 |
| RoPE | Su et al. | arXiv:2104.09864 |
