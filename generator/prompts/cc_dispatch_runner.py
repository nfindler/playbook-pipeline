"""
CC dispatch transport adapter.

CC-D shipped the real transport at `scripts/dispatch_to_cc.py` via PR #1.
That module spawns a file-based handoff into an idle CC tmux pane and
blocks until the receiving CC writes its response file.

This module is a thin adapter on top of it so call sites in the
generator import a stable surface:

    from generator.prompts.cc_dispatch_runner import (
        dispatch_to_cc, is_dispatch_enabled, CCDispatchUnavailable,
    )

Differences vs CC-D's transport signature:

  * Adds the `system` kwarg by prepending the system prompt onto the
    user message under a clearly-marked SYSTEM block. CC-D's transport
    has no separate system channel (the receiving CC sees one body).
  * Translates DispatchError / DispatchTimeout / DispatchNoSession to
    a single CCDispatchUnavailable that the marker-parser sites already
    handle (alongside CCResultParseError).
  * Honours CD_USE_CC_DISPATCH=1 as the feature flag.

Returns: the receiving CC's raw response text. Caller passes that text
into parse_cc_result(text, schema_id) to enforce the marker contract.
"""

from __future__ import annotations

import os
import sys

# CC-D's transport lives at scripts/dispatch_to_cc.py. Add the scripts
# directory to sys.path lazily so this module can be imported even when
# the transport file isn't on disk (older deploys).
SKILL_ROOT = "/home/openclaw/playbook-skill"
if SKILL_ROOT + "/scripts" not in sys.path:
    sys.path.insert(0, SKILL_ROOT + "/scripts")


class CCDispatchUnavailable(RuntimeError):
    """Raised when CD_USE_CC_DISPATCH=1 but the transport can't deliver."""


def is_dispatch_enabled() -> bool:
    """Feature flag: single source of truth for opt-in call sites."""
    return os.environ.get("CD_USE_CC_DISPATCH", "").strip() == "1"


def _compose_body(prompt: str, system: str | None) -> str:
    if not system:
        return prompt
    return (
        "SYSTEM PROMPT (read first, follow throughout):\n"
        "---\n"
        f"{system.strip()}\n"
        "---\n\n"
        "USER MESSAGE (the work):\n"
        f"{prompt}"
    )


def dispatch_to_cc(
    prompt: str,
    system: str | None = None,
    model: str = "sonnet",       # accepted for caller convenience; receiving CC picks its own model
    max_tokens: int = 8192,
    timeout_s: int = 600,
    target_session: str | None = None,
) -> str:
    """Send `prompt` to a CC tmux session via CC-D's file-based transport.

    Always raises CCDispatchUnavailable on any failure so caller fallback
    code (which already handles CCResultParseError) has one exception type
    to catch.
    """
    try:
        import dispatch_to_cc as _transport
    except ImportError as e:
        raise CCDispatchUnavailable(
            f"dispatch_to_cc transport not importable: {e}"
        )

    body = _compose_body(prompt, system)
    try:
        return _transport.dispatch_to_cc(
            body,
            max_tokens=max_tokens,
            target_session=target_session,
            timeout_sec=timeout_s,
        )
    except _transport.DispatchNoSession as e:
        raise CCDispatchUnavailable(f"no_session: {e}")
    except _transport.DispatchTimeout as e:
        raise CCDispatchUnavailable(f"timeout: {e}")
    except _transport.DispatchError as e:
        raise CCDispatchUnavailable(f"transport_error: {e}")
