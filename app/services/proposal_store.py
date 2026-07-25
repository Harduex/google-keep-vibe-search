"""Persistence for generated-but-not-yet-applied tag proposals.

Generating proposals costs one LLM call per cluster — hundreds of calls and many minutes of
wall clock. Until now the result lived only in React state, so a browser reload, a dev-server
restart, a stream error or a crash threw all of it away with nothing to recover from. The
proposals are now written the moment they are generated and cleared only once they are
applied or explicitly discarded, so the expensive part survives everything except the user
choosing to drop it.

This holds tag names and note ids — the same sensitivity as `tags.json`. It lives in the
cache directory and is written with the same atomic-write helper.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.note_service import _write_json_atomically


def _pending_path() -> str:
    return os.path.join(settings.resolved_cache_dir, "pending_proposals.json")


def save_pending_proposals(proposals: List[Dict[str, Any]], granularity: Optional[str]) -> None:
    """Persist a freshly generated proposal set, replacing any previous one."""
    if not proposals:
        return
    payload = {
        "generated_at": time.time(),
        "granularity": granularity,
        "proposals": proposals,
    }
    try:
        _write_json_atomically(_pending_path(), payload, keep_backup=True)
        print(f"[proposals] saved {len(proposals)} pending proposals")
    except OSError as e:
        # Never fail the generation stream over this — the user still has the proposals on
        # screen; they just are not crash-proof this time.
        print(f"[proposals] could not persist pending proposals: {type(e).__name__}")


def load_pending_proposals() -> Optional[Dict[str, Any]]:
    """Return the persisted proposal set, or None when there is nothing pending."""
    path = _pending_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None
    if not isinstance(payload, dict) or not payload.get("proposals"):
        return None
    return payload


def clear_pending_proposals() -> None:
    """Drop the persisted set — called once the proposals have been applied or discarded."""
    path = _pending_path()
    try:
        if os.path.exists(path):
            os.replace(path, f"{path}.bak")
    except OSError as e:
        print(f"[proposals] could not clear pending proposals: {type(e).__name__}")
