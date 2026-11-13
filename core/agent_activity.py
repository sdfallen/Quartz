"""Short Turkish description of what an agent is doing right now, for the chat.

Reads only the provider run record SpeS already keeps (events). The text is a
display hint: it is never evidence, permission or a success claim. Commands are
shortened and paths reduced to their last part so the line cannot carry a whole
secret-bearing command line or a private folder structure.
"""
from __future__ import annotations

import re

TOOL_LABELS = {
    # SpeS MCP tools (both providers).
    "desktop_request_access": "Pencere erişimi istiyor",
    "desktop_focus": "Pencereyi öne alıyor",
    "desktop_observe": "Ekranı inceliyor",
    "desktop_act": "Pencerede işlem yapıyor",
    "desktop_verify": "Sonucu doğruluyor",
    "desktop_windows": "Açık pencerelere bakıyor",
    "task_context": "Görev durumunu okuyor",
    "task_wait": "Ekip arkadaşını bekliyor",
    "task_message": "Ekibe not yazıyor",
    "task_read_log": "Günlüğü okuyor",
    "jarvis_open_app": "Uygulama açıyor",
    "jarvis_input": "Klavyeyle yazıyor",
    "jarvis_media_web": "Web/medya işlemi yapıyor",
    "jarvis_system_info": "Sistem bilgisine bakıyor",
    # Antigravity built-in tools.
    "view_file": "Dosya okuyor",
    "read_file": "Dosya okuyor",
    "list_dir": "Klasörü inceliyor",
    "list_directory": "Klasörü inceliyor",
    "find_by_name": "Dosya arıyor",
    "grep_search": "Kodda arıyor",
    "codebase_search": "Kodda arıyor",
    "search_web": "Web'de arıyor",
    "read_url_content": "Web sayfası okuyor",
    "run_command": "Komut çalıştırıyor",
    "run_shell_command": "Komut çalıştırıyor",
    "write_to_file": "Dosya yazıyor",
    "replace_file_content": "Dosya düzenliyor",
    "multi_replace_file_content": "Dosya düzenliyor",
}
_PATH_KEYS = ("AbsolutePath", "TargetFile", "file_path", "path", "DirectoryPath", "SearchPath")
_QUERY_KEYS = ("Query", "query", "pattern", "Pattern")
_SECRET = re.compile(r"(token|secret|password|api[_-]?key|authorization)\S*", re.I)


def _short(text, limit=44):
    text = _SECRET.sub("…", " ".join(str(text or "").split()))
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _leaf(path):
    parts = re.split(r"[\\/]+", str(path or "").strip())
    return _short(parts[-1] if parts and parts[-1] else "", 40)


def _with_detail(label, params):
    params = params if isinstance(params, dict) else {}
    for key in _PATH_KEYS:
        if params.get(key):
            return f"{label}: {_leaf(params[key])}"
    for key in _QUERY_KEYS:
        if params.get(key):
            return f"{label}: {_short(params[key], 32)}"
    command = params.get("CommandLine") or params.get("command")
    if command:
        return f"{label}: {_short(command)}"
    return label


def _tool_label(name):
    name = str(name or "")
    if name in TOOL_LABELS:
        return TOOL_LABELS[name]
    # MCP tools arrive with a server prefix ("mcp_quartz-desktop_desktop_act").
    for key in sorted(TOOL_LABELS, key=len, reverse=True):
        if name.endswith(("_" + key, "." + key, "/" + key)):
            return TOOL_LABELS[key]
    leaf = name.split("__")[-1].split(".")[-1]
    return f"Araç kullanıyor: {_short(leaf, 28)}" if leaf else "Araç kullanıyor"


def _codex(event):
    kind = event.get("type")
    if kind in {"turn.started", "thread.started"}:
        return "Düşünüyor…"
    if kind not in {"item.started", "item.updated", "item.completed"}:
        return None
    item = event.get("item") or {}
    item_type = item.get("type")
    started = kind != "item.completed"
    if item_type == "reasoning":
        return "Düşünüyor…"
    if item_type == "command_execution":
        return ("Komut çalıştırıyor: " if started else "Komut bitti: ") + _short(item.get("command"))
    if item_type == "file_change":
        changes = item.get("changes") or []
        first = changes[0].get("path") if changes and isinstance(changes[0], dict) else ""
        return "Dosya düzenliyor" + (f": {_leaf(first)}" if first else "")
    if item_type == "mcp_tool_call":
        return _tool_label(item.get("tool"))
    if item_type == "web_search":
        return "Web'de arıyor" + (f": {_short(item.get('query'), 32)}" if item.get("query") else "")
    if item_type == "todo_list":
        return "Plan çıkarıyor"
    if item_type == "agent_message":
        return "Yanıt yazıyor…"
    return None


def _antigravity(event):
    if event.get("event") == "init":
        return "Düşünüyor…"
    if event.get("event") != "step_update":
        return None
    step = event.get("step_update") or {}
    tool = step.get("tool_name")
    if tool:
        params = (step.get("tool_info") or {}).get("parameters") or {}
        return _with_detail(_tool_label(tool), params)
    if step.get("text_delta"):
        return "Yanıt yazıyor…"
    if step.get("thinking") or step.get("thought"):
        return "Düşünüyor…"
    return None


def describe_activity(provider, run):
    """Latest human-readable activity for a run record, or None."""
    reader = _codex if provider == "codex" else _antigravity if provider == "antigravity" else None
    if reader is None or not isinstance(run, dict):
        return None
    for event in reversed(run.get("events") or []):
        if isinstance(event, dict):
            text = reader(event)
            if text:
                return text
    return None
