#!/usr/bin/env python3
"""dispatch_to_cc.py

Synchronous CC-tmux dispatch for prompt-to-text work. Replaces direct
Anthropic API calls with a file-based handoff into an idle CC tmux pane.

Architecture (file-based, NOT pane-scraping):

  caller -> writes /tmp/dispatch/<job_id>-prompt.md
         -> tmux paste-buffer into target session a prompt body that
            reads "read /tmp/dispatch/<job_id>-prompt.md and write your
            response (and ONLY your response) to /tmp/dispatch/<job_id>-
            response.md when done"
         -> polls /tmp/dispatch/<job_id>-response.md every 5s
         -> on file present + readable: returns the contents
         -> on timeout (default 600s): raises DispatchTimeout

Why file-based and not pane-scraping:

  - Pane buffers wrap, scroll, and embed ANSI codes; 8KB of generated
    JSON between markers can't be reliably reconstructed.
  - Per memory `feedback_never_relay_cc_pane_claims_as_truth`: the
    pane is not the source of truth. The file the CC writes is.

Receiving CC contract:

  The dispatched CC sees a prompt block in its pane. The prompt
  explicitly says "write to <path>". A cooperating CC reads the
  prompt file, does the work, writes the response file. This is the
  same pattern as `engines/investor/dispatch.py` in the playbook-
  platform repo.

  If no idle CC is available, dispatch raises DispatchNoSession and
  the caller falls back (e.g. raises to the pipeline runner which
  surfaces a partial-step failure).

Token cost:

  Zero variable cost from the playbook-skill side. The receiving CC
  consumes tokens from its own subscription. This is the whole point
  of the migration: stop hitting the Anthropic API directly while the
  org-wide credits are exhausted.

Usage:

  from dispatch_to_cc import dispatch_to_cc, DispatchTimeout
  text = dispatch_to_cc(prompt, max_tokens=8000)  # blocks
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from typing import List, Optional


DISPATCH_DIR = os.environ.get("DISPATCH_DIR", "/tmp/dispatch")
DEFAULT_TIMEOUT_SEC = 600
DEFAULT_POLL_INTERVAL_SEC = 5.0

SESSION_RE = re.compile(r"^cc-[A-Z]+-[A-Z0-9]+-[a-z]+-\d+$")
TMUX_SOCKET = os.environ.get("TMUX_SOCKET", "/tmp/tmux-1000/default")

# Pool of CC sessions. cc-CC-D-personal-1 is excluded if this script
# is dispatched from CC-D. Override via DISPATCH_POOL env if needed.
DEFAULT_POOL: List[str] = [
    "cc-CC-VB-personal-1",
    "cc-CC-E-personal-1",
    "cc-CC-C-personal-1",
    "cc-CC-N-personal-1",
    "cc-CC-Q-personal-1",
]


class DispatchError(RuntimeError):
    """Base for dispatch problems."""


class DispatchNoSession(DispatchError):
    """No idle CC tmux session available to dispatch to."""


class DispatchTimeout(DispatchError):
    """The receiving CC did not write the response file in time."""


# ---- Session selection -----------------------------------------------


def list_active_sessions() -> List[str]:
    """Return CC tmux sessions present on the local socket, excluding
    the orchestrating session if known."""
    try:
        proc = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if proc.returncode != 0:
        return []
    self_session = os.environ.get("TMUX_PANE_SESSION") or ""
    out = []
    for line in proc.stdout.splitlines():
        name = line.strip()
        if not SESSION_RE.match(name):
            continue
        if name == self_session:
            continue
        out.append(name)
    return out


def pick_session(preferred: Optional[str] = None) -> Optional[str]:
    """Pick an active session. Prefers `preferred` if it's alive."""
    active = set(list_active_sessions())
    if preferred and preferred in active:
        return preferred
    pool = os.environ.get("DISPATCH_POOL", "").split(",") if os.environ.get("DISPATCH_POOL") else DEFAULT_POOL
    for s in pool:
        s = s.strip()
        if s and s in active:
            return s
    # Fall back to any active CC session.
    for s in sorted(active):
        return s
    return None


# ---- Tmux send (local, via paste-buffer) -----------------------------


def tmux_paste(session: str, text: str) -> None:
    """Deliver `text` into the target tmux session by writing to a temp
    file, loading it into a named tmux buffer, and pasting + Enter."""
    if not SESSION_RE.match(session):
        raise DispatchError(f"invalid session {session!r}")
    import tempfile

    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".cc-dispatch")
    try:
        tmp.write(text)
        tmp.write("\n")
        tmp.close()
        for argv in (
            ["tmux", "load-buffer", "-b", "cc-dispatch", tmp.name],
            ["tmux", "paste-buffer", "-b", "cc-dispatch", "-t", session],
            ["tmux", "send-keys", "-t", session, "Enter"],
        ):
            r = subprocess.run(argv, capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                raise DispatchError(f"tmux step failed: {argv} -> {r.stderr.strip()[:200]}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---- File-based prompt/response ---------------------------------------


def _ensure_dir() -> None:
    os.makedirs(DISPATCH_DIR, exist_ok=True)


def _prompt_path(job_id: str) -> str:
    return os.path.join(DISPATCH_DIR, f"{job_id}-prompt.md")


def _response_path(job_id: str) -> str:
    return os.path.join(DISPATCH_DIR, f"{job_id}-response.md")


def _wrap_prompt(job_id: str, body: str, max_tokens: int) -> str:
    """Build the message the receiving CC sees in its pane.

    The actual prompt lives in a file because pane buffers can't carry
    8KB+ of structured content reliably. The pane message tells the
    receiving CC where to read and where to write."""
    return (
        f"DISPATCHED-WORK from playbook-skill job_id={job_id}\n"
        f"Read the prompt at {_prompt_path(job_id)}\n"
        f"Write your response (and ONLY your response, no preamble) to {_response_path(job_id)} when done.\n"
        f"Suggested response length: under {max_tokens} tokens.\n"
        f"The playbook-skill pipeline is polling that path; once the file exists + parses, it moves on.\n"
    )


def dispatch_to_cc(
    prompt: str,
    *,
    max_tokens: int = 8000,
    target_session: Optional[str] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC,
) -> str:
    """Dispatch a prompt to a CC tmux session and return the response.

    Blocks for up to timeout_sec (default 600s = 10 min).

    Raises DispatchNoSession when no idle CC is reachable, and
    DispatchTimeout when the receiving CC doesn't write the response
    file in time. Both are recoverable: caller can fall back to a
    smaller prompt, retry, or surface a partial-step failure.
    """
    _ensure_dir()
    job_id = uuid.uuid4().hex[:12]

    # Write the full prompt to a file. The receiving CC reads it from
    # there, not from the pane.
    with open(_prompt_path(job_id), "w", encoding="utf-8") as fh:
        fh.write(prompt)

    target = target_session or pick_session(target_session)
    if not target:
        raise DispatchNoSession("no idle CC tmux session available")

    tmux_paste(target, _wrap_prompt(job_id, prompt, max_tokens))

    response_path = _response_path(job_id)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if os.path.exists(response_path):
            # Re-read once after a short pause to dodge a partial-flush
            # race when the CC is still writing.
            time.sleep(0.5)
            try:
                with open(response_path, "r", encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                pass
        time.sleep(poll_interval_sec)
    raise DispatchTimeout(
        f"job_id={job_id} target={target} timeout after {timeout_sec}s; "
        f"response_path={response_path} (the CC may still write it; pipeline can resume by tailing the path)"
    )


# ---- CLI for one-off testing -----------------------------------------

def _main(argv: List[str]) -> int:
    if not argv:
        print("usage: dispatch_to_cc.py <prompt_file_or_dash>", file=sys.stderr)
        return 2
    src = argv[0]
    if src == "-":
        prompt = sys.stdin.read()
    else:
        with open(src, "r", encoding="utf-8") as fh:
            prompt = fh.read()
    try:
        out = dispatch_to_cc(prompt)
    except DispatchNoSession as e:
        print(f"NO_SESSION: {e}", file=sys.stderr)
        return 3
    except DispatchTimeout as e:
        print(f"TIMEOUT: {e}", file=sys.stderr)
        return 4
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
