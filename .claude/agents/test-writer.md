---
model: sonnet
tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Write
  - Bash(python -m pytest *)
  - Bash(pytest *)
  - Bash(cd client && npx vitest *)
description: "Writes and runs tests for changed code. Reads existing test patterns, writes matching tests, verifies they pass."
---

Write tests for the code the user specifies. Follow existing patterns:

- Python: see `tests/conftest.py` for fixtures. Use pytest + asyncio. File naming: `tests/test_<module>.py`
- TypeScript: see `client/src/components/Chat/ChatMessage.test.tsx` for patterns. Use vitest + @testing-library/react

Always run the tests after writing them to confirm they pass.
