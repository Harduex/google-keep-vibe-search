# LLM Output Validation

**Problem**: Perfectly good LLM outputs (e.g., tags like "3D Printing" or "Mouse & Keyboard") were being discarded by the backend sanitizer.
**Root Cause**: The Python regex validator was overly strict, only allowing alphabetic characters and hard word boundaries, which immediately rejected numbers (`3`) and symbols (`&`).
**Solution**: When sanitizing short LLM outputs, validate the character set of the whole string (`^[A-Za-z0-9\s&/-]*$`) rather than strictly bounding individual words. Assume the model will use digits and safe symbols, and that symbols like `&` might be parsed as standalone words during string splits, requiring a wider truncation slice.
