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
