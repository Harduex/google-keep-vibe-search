# Project Memories

This file contains lessons learned and important notes from past implementations.

---

## GPU/CUDA Setup for PyTorch (March 2026)

### Problem
The app was running embedding, indexing, and other operations on CPU instead of GPU, resulting in slow performance.

### Root Cause
1. **PyTorch CPU-only**: `requirements.txt` had `torch==2.0.1` which installs the CPU-only version by default
2. **No device specification**: `SentenceTransformer` was initialized without specifying device

### Solution

#### 1. Updated requirements.txt
```diff
- torch==2.0.1
+ torch==2.1.2 --index-url https://download.pytorch.org/whl/cu121
+ torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cu121
```

#### 2. Updated app/search.py (line 23)
```diff
- self.model = SentenceTransformer("all-MiniLM-L6-v2")
+ self.model = SentenceTransformer("all-MiniLM-L6-v2").to("cuda")
```

### Key Lessons

1. **PyTorch CUDA installation requires special index URL**: Default `pip install torch` installs CPU-only. Must use:
   ```bash
   pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cu121
   ```

2. **torchvision must match torch version**: Incompatible versions cause runtime errors (e.g., `AttributeError: module 'torch.library' has no attribute 'register_fake'`)

3. **sentence-transformers 2.2.2 device argument doesn't work**: Use `.to("cuda")` instead of `device="cuda"` parameter

4. **pip may cache CPU version**: If pip shows "requirement already satisfied" but CUDA is still unavailable, force reinstall:
   ```bash
   pip uninstall torch torchvision -y
   pip install torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cu121
   ```

5. **numpy<2 required**: PyTorch 2.1.x has compatibility issues with NumPy 2.x. Pin to `numpy<2`

### Files Changed
- `requirements.txt` - Added CUDA-enabled torch and torchvision
- `app/search.py` - Added `.to("cuda")` to SentenceTransformer

### Verification
```python
import torch
print(torch.cuda.is_available())  # Should print True
```

---

## Agent Instructions Consolidation (March 2026)

### Problem
The repository had both `AGENTS.md` and `CLAUDE.md` at the root, splitting agent guidance across two overlapping files.

### Root Cause
The repo mixed a general `AGENTS.md` architecture note with Claude-specific workflow guidance in `CLAUDE.md`, which creates drift and conflicting instructions over time.

### Solution

#### 1. Promoted `AGENTS.md` to the single root instruction file
- Merged project architecture, setup commands, validation commands, working conventions, agent workflow, and `.agents/` layout guidance into `AGENTS.md`.

#### 2. Removed duplicate root instructions
- Deleted `CLAUDE.md` so the repository has one checked-in root instruction file.

### Key Lessons

1. Keep one canonical root instruction file for agents.
2. Keep detailed prompts and workflows under `.agents/` instead of duplicating them in the root file.
3. Root instructions should stay concise and operational: setup, validation, structure, workflow, and conventions.

### Files Changed
- `AGENTS.md` - Rewritten as the single agent-facing root guide
- `CLAUDE.md` - Removed after merging content into `AGENTS.md`
- `memories.md` - Added note explaining the consolidation
