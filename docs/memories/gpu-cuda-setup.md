# GPU/CUDA Setup for PyTorch

*March 2026*

## Problem
App ran on CPU instead of GPU. Slow embedding/indexing.

## Solution
- `requirements.txt`: Use `torch==2.1.2 --index-url https://download.pytorch.org/whl/cu121` (not default CPU-only)
- `app/search.py`: `SentenceTransformer(...).to("cuda")` (not `device="cuda"` param — doesn't work in 2.2.2)
- `torchvision` must match torch version. Mismatch → `AttributeError: module 'torch.library' has no attribute 'register_fake'`
- Pin `numpy<2` — PyTorch 2.1.x incompatible with NumPy 2.x
- If pip caches CPU version: `pip uninstall torch torchvision -y` then reinstall with index URL

## Verification
```python
import torch
print(torch.cuda.is_available())  # Should print True
```
