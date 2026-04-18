@AGENTS.md
@docs/memories/MEMORY.md

## Claude Code

### Environment
- Windows 11, bash via Git Bash
- Python 3.11 (global install, no venv). Backend: `python -m uvicorn app.main:app --reload`
- Node at `client/`. Frontend: `cd client && npm run dev`
- Both servers: `./scripts/dev.ps1` (Windows) or `bash scripts/dev.sh` (Linux/macOS)
- GPU/CUDA available (RTX 3060 12GB, CUDA 12.1) — see docs/memories/gpu-cuda-setup.md

### Formatting
- Python: `black <files>` + `isort <files>` (line-length=100)
- TypeScript: `cd client && npm run fix`
- Pre-commit hooks enforce formatting. If a commit fails, fix formatting and retry.

### Validation (smallest check first)
1. Format: `black <file>` or `cd client && npx prettier --write <file>`
2. Test: `pytest tests/test_<module>.py` or `cd client && npx vitest run <file>`
3. Full suite only when multiple modules touched

### Communication
- Be extremely concise when reporting. Sacrifice grammar for concision.
- When context hits 75%, use the compact tool.
- After final implementation, ask: "Would you like me to apply any corrections, or should we conclude the session now?"
