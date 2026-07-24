"""Redaction helpers — the single sanctioned way to log anything near an LLM call.

LiteLLM/httpx exceptions quote the failed **request body**, and this app's request
bodies contain sampled note text (`Title: … / Snippet: …`). So `str(e)`, `repr(e)`
and `traceback.print_exc()` are all note-text leaks — and `*.log` is gitignored, so
nobody would ever notice. Per AGENTS.md: log exception
**types** and structural metadata only, never prompts, note titles or note bodies.
Generated tag names are fine; sampled note text never is. No dependencies by design.
"""

from typing import Any, Optional

# Truncation for string values in safe_meta: enough to debug a generated tag,
# far too short to carry a note. Trades detail for containment.
MAX_VALUE_LEN = 40


def _status_code(e: BaseException) -> Optional[int]:
    """HTTP status from a provider/transport exception, if it exposes one."""
    code = getattr(e, "status_code", None)
    if code is None:
        code = getattr(getattr(e, "response", None), "status_code", None)
    if isinstance(code, bool):
        return None
    if isinstance(code, int):
        return code
    return int(code) if isinstance(code, str) and code.isdigit() else None


def safe_exc(e: BaseException) -> str:
    """Exception type (plus status code when present) — never the message."""
    code = _status_code(e)
    return f"{type(e).__name__}(status={code})" if code is not None else type(e).__name__


def safe_meta(**kw: Any) -> str:
    """Format counts/ids/shapes/timings as `key=value`.

    Never pass note text, prompts or exception messages (use `safe_exc`); the
    `MAX_VALUE_LEN` truncation of string values is a backstop, not a licence.
    """
    parts = []
    for key, value in kw.items():
        if isinstance(value, str):
            suffix = f"+{len(value) - MAX_VALUE_LEN}" if len(value) > MAX_VALUE_LEN else ""
            parts.append(f"{key}={value[:MAX_VALUE_LEN]!r}{suffix}")
        elif isinstance(value, float):
            parts.append(f"{key}={value:.3f}")
        else:
            parts.append(f"{key}={value}")
    return " ".join(parts)
