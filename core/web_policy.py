"""One rule for which agent runs may use the web (user request 14 Nov 2026: "all agents").

Web is allowed only for a tool-less conversation run: no project read, no write or full
access, no desktop connection. Build steps and project checks never search.

- Fatum (Claude): the "web" sandbox, WebSearch only (no WebFetch), proven from the CLI's
  init event (core.claude_runtime).
- Fides (Codex): the per-run web_search setting of the guarded config. Default "cached"
  (answers from the search index, no live page fetch); "live" is fresher but lets a page
  steer the agent, so it is opt-in with SPES_CODEX_WEB=live. Never written to config.toml.
- Eos (Antigravity): not yet. Its tool name and hook payload could not be verified
  (quota exhausted 14 Nov); the observer guard keeps denying every tool until then.
"""
from __future__ import annotations

import os

WEB_AGENTS = frozenset({"claude", "codex"})
CODEX_MODES = ("cached", "live", "disabled")


def web_allowed(agent: str, *, conversation_only: bool, project_read: bool = False, write: bool = False,
                full_access: bool = False, desktop: bool = False) -> bool:
    return (agent in WEB_AGENTS and bool(conversation_only) and not project_read and not write
            and not full_access and not desktop)


def codex_web_mode(web: bool) -> str:
    if not web:
        return "disabled"
    mode = os.getenv("SPES_CODEX_WEB", "cached").strip().lower()
    return mode if mode in CODEX_MODES else "cached"
