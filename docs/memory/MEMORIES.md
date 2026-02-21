# Agent Memory

Lessons learned and patterns discovered during development.

---

## 2026-02-21: Bug Fix Session

### httpx URL Joining (RFC 3986)
- **Problem**: `httpx.AsyncClient(base_url="http://host/v1")` with `client.post("/chat/completions")` drops the `/v1` segment because the leading slash on the path makes it absolute per RFC 3986.
- **Fix**: Ensure `base_url` ends with a trailing slash AND request paths have no leading slash: `base_url="http://host/v1/"` + `client.post("chat/completions")`.
- **Files**: `app/core/config.py` (trailing slash), `app/services/chat_service.py` (no leading slash on paths).

### Windows PowerShell Start-Process with npm
- **Problem**: `Start-Process -FilePath "npm"` fails with `"%1 is not a valid Win32 application"` because `npm` is a `.cmd` shell script, not a Win32 executable.
- **Fix**: Use `"npm.cmd"` as the FilePath on Windows.
- **File**: `scripts/dev.ps1`.

### Path Traversal in FastAPI File Serving
- **Problem**: Joining user-supplied path with `os.path.join()` without normalization allows `../../` traversal to read arbitrary files.
- **Fix**: Use `os.path.normpath()` on both base and full path, then verify `full_path.startswith(base)`.
- **File**: `app/routes/images.py`.

### Vite Template CSS Leftovers
- **Problem**: Default Vite React template adds CSS in `index.css` (`color-scheme: light dark`, dark background, centered layout, global button styles) that conflicts with the app's custom `data-theme` attribute theming system.
- **Fix**: Remove all Vite template defaults from `index.css`, keep only app-specific styles (Tailwind import, `@theme` block, fonts, `mark` styles).

### Pydantic v2 Migration
- **Pattern**: Use `.model_dump()` instead of deprecated `.dict()` throughout the codebase.
- **Pattern**: Use `model_config = {...}` class variable instead of inner `class Config`.
