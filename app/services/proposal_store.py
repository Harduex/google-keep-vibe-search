"""Persistence for generated-but-not-yet-applied tag proposals.

Generating proposals costs one LLM call per cluster — hundreds of calls and many minutes of
wall clock. Until now the result lived only in React state, so a browser reload, a dev-server
restart, a stream error or a crash threw all of it away with nothing to recover from. The
proposals are now written the moment they are generated and cleared only once they are
applied or explicitly discarded, so the expensive part survives everything except the user
choosing to drop it.

This holds tag names and note ids — the same sensitivity as `tags.json`. It lives in the
cache directory and is written with the same atomic-write helper.

The same artifact also carries the client's staged decisions (`actions`, a tag-name ->
action map) so the server can read which tags the user has already acted on. Those tags are
*locked*: consolidation skips them both as merge sources and merge targets, so nothing the
user decided can be undone by the machine. One artifact serves crash-safety and the lock
exemption — there is no second transport for the actions.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.note_service import _write_json_atomically


def _pending_path() -> str:
    return os.path.join(settings.resolved_cache_dir, "pending_proposals.json")


def _read_raw() -> Dict[str, Any]:
    """Return the raw persisted payload (possibly with empty fields), or an empty dict."""
    path = _pending_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_pending_proposals(proposals: List[Dict[str, Any]], granularity: Optional[str]) -> None:
    """Persist a freshly generated proposal set, replacing any previous one.

    Staged ``actions`` and the lock list are preserved across this write — a partial stream
    that re-persists must not drop decisions the user made mid-run.
    """
    if not proposals:
        return
    existing = _read_raw()
    payload = {
        "generated_at": time.time(),
        "granularity": granularity,
        "proposals": proposals,
        # Preserve staged decisions across re-persists (throttled partial saves during a run,
        # and the authoritative end-of-run frame). Empty when nothing is staged.
        "actions": existing.get("actions") if isinstance(existing.get("actions"), dict) else {},
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
    payload = _read_raw()
    if not payload.get("proposals"):
        return None
    return payload


def save_pending_actions(actions: Dict[str, str]) -> None:
    """Merge the client's staged decisions into the persisted artifact.

    ``actions`` is a tag-name -> staged-action map. The whole map is replaced (the client
    sends its complete staged state), and the proposals/``actions`` share one artifact so a
    single read serves crash-safety and the consolidation lock exemption.
    """
    if not isinstance(actions, dict):
        return
    payload = _read_raw()
    payload["actions"] = {str(k): str(v) for k, v in actions.items() if k is not None}
    # No proposals yet means nothing to lock against — still record the actions so they
    # survive until proposals arrive, but skip the atomic write when there is no payload at
    # all (mirrors save_pending_proposals' early return on empty proposals).
    try:
        _write_json_atomically(_pending_path(), payload, keep_backup=True)
    except OSError as e:
        print(f"[proposals] could not persist staged actions: {type(e).__name__}")


def load_pending_actions() -> Dict[str, str]:
    """Return the staged actions map (tag name -> action), empty when nothing is staged."""
    payload = _read_raw()
    actions = payload.get("actions")
    if not isinstance(actions, dict):
        return {}
    return {str(k): str(v) for k, v in actions.items() if k}


def clear_pending_proposals() -> None:
    """Drop the persisted set — called once the proposals have been applied or discarded."""
    path = _pending_path()
    try:
        if os.path.exists(path):
            os.replace(path, f"{path}.bak")
    except OSError as e:
        print(f"[proposals] could not clear pending proposals: {type(e).__name__}")
