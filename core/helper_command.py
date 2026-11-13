"""Where SpeS's desktop/guard helper lives. Standard library only.

The packaged helper (QuartzDesktopMCP.exe) is also the PreToolUse guard that
Antigravity starts for every tool call. Anything the helper imports is bundled
into that one-file exe and unpacked on each call, so this module must stay free
of desktop/UI imports: importing core.desktop_agents here grew the helper from
7.8 MB to 34 MB and its start-up past Antigravity's hook time limit (12 Nov).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Antigravity kills a hook that has not answered within its timeout and the
# tool call is then refused. The guard still fails closed; this is margin for a
# busy machine (one-file start-up measured at 1-13 s depending on load).
HOOK_TIMEOUT_SECONDS = 30


def mcp_command():
    if getattr(sys, "frozen", False):
        exe = Path(sys._MEIPASS) / "operator" / "QuartzDesktopMCP.exe"
        if not exe.is_file(): raise RuntimeError("Desktop MCP helper is missing from the package")
        return [str(exe)]
    return [sys.executable, str(Path(__file__).with_name("desktop_mcp.py"))]
