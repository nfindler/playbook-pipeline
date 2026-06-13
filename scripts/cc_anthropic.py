"""cc_anthropic.py -- CLI-2785: the $0 cc-dispatch transport facade for the v1 pipeline.

A drop-in replacement for the `anthropic` SDK surface the step scripts actually use
(`Anthropic().messages.create(...)` + `.messages.stream(...)`, text content blocks,
cosmetic usage counters). Instead of the metered API (the org key drained 2026-06-12 and
killed generation silently -- CLI-2777), every call shells a headless `claude -p` billed
to the Max SUBSCRIPTION (the proven playbook-platform lib/ai-reasoning-cc-dispatch.js
pattern): ANTHROPIC_API_KEY is STRIPPED from the child env and CLAUDE_CONFIG_DIR is
pinned to the subscription credentials, so spend is $0 by construction.

The build-phase law (CLI-2722, locked): the metered path stays IN the architecture but
DARK. Setting CC_TRANSPORT=metered re-enables the real SDK ONLY when the cc-state
overlay says `serving_mode: live` (Nick's go-live flip); otherwise it raises. Default
is always cc-dispatch.

Swap-in is one line per step script:  `import cc_anthropic as anthropic`
"""

import json
import os
import re
import subprocess
import time

CLAUDE_BIN = os.environ.get("CC_DISPATCH_CLAUDE_BIN") or os.path.expanduser("~/.local/bin/claude")
if not os.path.exists(CLAUDE_BIN):
    CLAUDE_BIN = "claude"
# The subscription credentials dir (the CLI-2733 prior: pinned => $0).
_SHARED_CONFIG_DIR = "/home/openclaw/.claude-climatedoor"


def _config_dir():
    """review fix (PR #3): the proxy runs as ROOT; a root-spawned claude rewrites
    .claude.json/.credentials.json inside the config dir, and root-owned files in the SHARED
    openclaw subscription dir would break every other $0 flow on the box. Root gets its own
    clone (refreshed when the shared creds are newer); openclaw uses the shared dir."""
    explicit = os.environ.get("CC_DISPATCH_CONFIG_DIR")
    if explicit:
        return explicit
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        clone = "/root/.claude-climatedoor-cc2785"
        try:
            src_cred = os.path.join(_SHARED_CONFIG_DIR, ".credentials.json")
            dst_cred = os.path.join(clone, ".credentials.json")
            if not os.path.isdir(clone) or (
                os.path.exists(src_cred)
                and (not os.path.exists(dst_cred) or os.path.getmtime(src_cred) > os.path.getmtime(dst_cred))
            ):
                import shutil

                shutil.copytree(_SHARED_CONFIG_DIR, clone, dirs_exist_ok=True)
            return clone
        except Exception:
            return _SHARED_CONFIG_DIR  # degraded but functional; the hazard window is the refresh write
    return _SHARED_CONFIG_DIR


CONFIG_DIR = _config_dir()
OVERLAY_FILE = os.environ.get(
    "CC_STATE_OVERLAY", "/home/openclaw/cc-state/cc-orchestrator.config.overlay.json"
)
CALL_TIMEOUT_S = int(os.environ.get("CC_DISPATCH_TIMEOUT_S", "840"))  # < the proxy's 15min step cap

# Reasoning calls get no tools; a web_search-tools request maps to claude's native WebSearch.
_DISALLOWED_BASE = [
    "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "Task", "Agent",
    "Glob", "Grep", "Read", "TodoWrite", "WebSearch",
]


def _serving_mode():
    try:
        with open(OVERLAY_FILE, "r") as f:
            mode = (json.load(f) or {}).get("serving_mode")
        return "live" if mode == "live" else "build"
    except Exception:
        return "build"  # fail closed: an unreadable overlay never opens the metered path


def _model_alias(model):
    """Map any pinned claude-* id (incl. retired ids like claude-opus-4-20250514) to a CLI tier."""
    m = str(model or "").lower()
    if "haiku" in m:
        return "haiku"
    if "opus" in m:
        return "opus"
    if "sonnet" in m or not m:
        return "sonnet"
    return "sonnet"


def _flatten_messages(messages):
    parts = []
    for msg in messages or []:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return "\n\n".join(p for p in parts if p)


class _Usage(object):
    def __init__(self, input_tokens=0, output_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _TextBlock(object):
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response(object):
    def __init__(self, text, usage=None, model=None):
        self.content = [_TextBlock(text)]
        self.usage = usage or _Usage()
        self.model = model
        self.stop_reason = "end_turn"


class _FakeStream(object):
    """messages.stream(...) facade: the v1 steps use streaming only as keepalive and then
    read get_final_message(); one blocking call satisfies that contract."""

    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(())

    def get_final_message(self):
        return self._response


class _Messages(object):
    def create(self, model=None, max_tokens=None, messages=None, system=None, tools=None, **_kw):
        wants_web = any(
            isinstance(t, dict) and (t.get("name") == "web_search" or "web_search" in str(t.get("type", "")))
            for t in (tools or [])
        )
        prompt = _flatten_messages(messages)
        if not prompt.strip():
            raise ValueError("cc_anthropic: empty prompt")
        disallowed = [t for t in _DISALLOWED_BASE if not (wants_web and t == "WebSearch")]
        args = [
            CLAUDE_BIN, "-p",
            "--output-format", "json",
            "--model", _model_alias(model),
            "--strict-mcp-config",
            "--setting-sources", "project",
            "--disallowedTools", *disallowed,
        ]
        if wants_web:
            # review fix (PR #3): headless -p DENIES WebSearch unless explicitly allowed --
            # without this the 4 web-research call sites silently degrade to training-data
            # answers with fabricated-looking source URLs (proven via permission_denials).
            args += ["--allowedTools", "WebSearch"]
        if system:
            args += ["--system-prompt", str(system)[:30000]]
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)  # $0 by construction: the child can never meter
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        env.pop("ANTHROPIC_BASE_URL", None)  # parity with the canonical JS bridge
        env["CLAUDE_CONFIG_DIR"] = CONFIG_DIR
        t0 = time.time()
        proc = subprocess.run(
            args, input=prompt.encode("utf-8"), capture_output=True, timeout=CALL_TIMEOUT_S, env=env,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or b"")[-400:].decode("utf-8", "replace")
            raise RuntimeError("cc_anthropic: claude -p exit %d: %s" % (proc.returncode, tail))
        raw = proc.stdout.decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            if payload.get("is_error") or (payload.get("subtype") and payload.get("subtype") != "success"):
                # review fix (PR #3): an error envelope returned as CONTENT would re-open the
                # CLI-2777 silent-failure class on the subscription side. Fail loudly.
                raise RuntimeError("cc_anthropic: claude -p error envelope: %s" % str(payload.get("result") or payload.get("subtype"))[:300])
            text = payload.get("result") or ""
            usage = payload.get("usage") or {}
            resp_usage = _Usage(int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0))
        except json.JSONDecodeError:
            # -p json should always be json; degrade to raw text rather than lose a real answer
            text, resp_usage = raw, _Usage()
        if not str(text).strip():
            raise RuntimeError("cc_anthropic: empty result from claude -p (%.0fs)" % (time.time() - t0))
        return _Response(str(text), resp_usage, model=_model_alias(model))

    def stream(self, **kwargs):
        return _FakeStream(self.create(**kwargs))


class Anthropic(object):
    """The drop-in client. CC_TRANSPORT=metered is honored ONLY at serving_mode live."""

    def __init__(self, *a, **kw):
        if os.environ.get("CC_TRANSPORT") == "metered":
            if _serving_mode() != "live":
                raise RuntimeError(
                    "cc_anthropic: the metered path is DARK while serving_mode is build "
                    "(CLI-2722 locked law); unset CC_TRANSPORT or flip serving_mode to live"
                )
            import anthropic as _real  # noqa: the genuine SDK, only behind the flip

            self.__class__ = _real.Anthropic  # hand the instance over wholesale
            _real.Anthropic.__init__(self, *a, **kw)
            return
        self.messages = _Messages()


# step type hints reference anthropic.Anthropic; expose the SDK-ish module surface
APIError = RuntimeError
BadRequestError = RuntimeError


if __name__ == "__main__":
    # $0 smoke: one tiny haiku call through the subscription transport.
    client = Anthropic()
    r = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=50,
        messages=[{"role": "user", "content": "Reply with exactly: TRANSPORT-OK"}],
    )
    print("self-test:", r.content[0].text.strip()[:60])
