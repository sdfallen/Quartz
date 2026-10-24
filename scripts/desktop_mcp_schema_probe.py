"""Diagnostic minimal MCP schema; used ONLY with the in-memory transport test."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.desktop_mcp import TOOLS, main

TOOLS[-1]["inputSchema"] = {"type": "object", "properties": {
    "snapshot_id": {"type": "string"}, "action": {"type": "string"},
    "x": {"type": "integer"}, "y": {"type": "integer"}},
    "required": ["snapshot_id", "action", "x", "y"], "additionalProperties": False}

if __name__ == "__main__": main()
