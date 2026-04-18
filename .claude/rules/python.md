---
paths:
  - "app/**"
  - "tests/**"
  - "*.py"
---

# Python Conventions

- Format: black (line-length=100), isort (profile=black)
- Type hints on all function signatures
- Pydantic models for request/response shapes
- FastAPI `Depends()` for injection. Services in `app/services/`, routes in `app/routes/`
- Tests: pytest + asyncio. File naming: `tests/test_<module>.py`
- Errors: `HTTPException` in routes, custom exceptions in `app/core/exceptions.py`
