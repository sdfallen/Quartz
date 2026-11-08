# Integration Request: Persist `command_results` and `unauthorized_write_detected` in `RunEvidenceStore` (`run_evidence.json`)

**Date:** 8 November 2026
**From:** Antigravity (Gemini) — Branch `antigravity/wave0-wave1-analysis-20261105`
**Target Owners:** `core/multi_agent_service.py` and `core/agent_chat.py` (Claude / Codex per `docs/PARALLEL_OWNERSHIP.md` and `docs/CLAUDE_HANDOVER_TO_GEMINI_2_20261108.md` Section 2.4)

---

## 1. Context & Problem Statement

In Wave 2 (`bd95dd7` / `9fbcaac`), `core/codex_runtime.py` and `core/antigravity_runtime.py` were updated to record structured runtime evidence on every run state (`runtime.get(run_id)`):
- `command_results`: `[{"command": str, "exit_code": int | None, "status": str, "at": float}, ...]`
- `files_changed`: `[str, ...]`
- `error_events`: `[{"source": str, "message": str, "at": float}, ...]`
- `unauthorized_write_detected`: `bool`
- `unauthorized_writes`: `[str, ...]`

However, when a run finishes through `MultiAgentService` / `AgentChatService`:
1. **`core/multi_agent_service.py:171-188` (`_watch_writer`)** builds the durable receipt persisted to `self._evidence_store.put(run_id, receipt)` (`%LOCALAPPDATA%\Quartz\.quartz\run_evidence.json`) with only `files_changed`, `evidence_warning`, and `source_validation`, omitting `command_results` and `unauthorized_write_detected` from `runtime.get(run_id)`.
2. **Read-only runs** (such as the Antigravity reviewer turn in `exam-code-03` or read-only turns in `exam-code-10`) do not go through `_watch_writer`, and `core/agent_chat.py` (`_execute_antigravity_bubble` at lines `1291-1295` and `_execute_codex_bubble` at lines `1439-1443`) does not copy `command_results` or `unauthorized_write_detected` onto message `metadata` or into `RunEvidenceStore`.

As a result, when `scripts/exam_live.py` grades a live `Quartz.exe` run (`_chat_turn_summary` at `scripts/exam_live.py:274-324`), `exam-code-09`'s `command_results_recorded` check (`scripts/exam_oracle.py:288-292`) and `exam-code-03`'s `reviewer_side_effects_none` check (`scripts/exam_oracle.py:213-228`) cannot see `command_results` or `unauthorized_write_detected` in `run_evidence.json` or message metadata unless this bridge is added.

---

## 2. Requested Changes

### 2.1 `core/multi_agent_service.py` (`_watch_writer`, lines 171–188)

Copy `command_results` and `unauthorized_write_detected` (plus `unauthorized_writes`) from the terminal `run_state = runtime.get(run_id)` into `receipt` before calling `self._evidence_store.put(run_id, receipt)`:

```python
    def _watch_writer(self, key: str, run_id: str, runtime, project_path: str, before: dict, claim=None) -> None:
        terminal_observed = False
        try:
            while runtime.get(run_id)["status"] not in runtime.TERMINAL:
                time.sleep(0.15)
            terminal_observed = True
            run_state = runtime.get(run_id)
            after = snapshot_workspace_files(project_path)
            changed, warning = changed_workspace_files(project_path, before, after)
            validation = verify_changed_python(project_path, changed, warning=warning)
            with self._lock:
                receipt = {
                    "files_changed": changed,
                    "evidence_warning": warning,
                    "source_validation": validation,
                    "command_results": list(run_state.get("command_results") or []),
                    "unauthorized_write_detected": bool(run_state.get("unauthorized_write_detected", False)),
                    "unauthorized_writes": list(run_state.get("unauthorized_writes") or []),
                }
                self._file_changes[run_id] = receipt
            try:
                self._evidence_store.put(run_id, receipt)
            except (OSError, ValueError) as exc:
                with self._lock:
                    self._file_changes[run_id]['persistence_warning'] = str(exc)
```

### 2.2 `core/agent_chat.py` (`_execute_antigravity_bubble` and `_execute_codex_bubble`)

At the end of `_stream_antigravity_run` / `_execute_antigravity_bubble` (lines `1291-1300`) and `_stream_codex_run` / `_execute_codex_bubble` (lines `1437-1448`), include `command_results` and `unauthorized_write_detected` in `meta` (both on `completed` and when publishing failed/terminal metadata) so `quartz_conversations.json` and `scripts/exam_live.py:_chat_turn_summary` can inspect them even for read-only turns that do not spawn `_watch_writer`:

```python
            meta.update({
                "status": "completed",
                "usage": run.get("usage"),
                "metrics": self._extract_metrics(run, bubble_t0),
                "command_results": list(run.get("command_results") or []),
                "unauthorized_write_detected": bool(run.get("unauthorized_write_detected", False)),
            })
```

And in `_stream_antigravity_run` (`line 1322`) / `_stream_codex_run` (`line 1469`), when `status in TERMINAL`:
```python
            if status in self.agent_service.codex.TERMINAL:
                step_meta = dict(meta)
                step_meta.update({
                    "status": status,
                    "command_results": list(run.get("command_results") or []),
                    "unauthorized_write_detected": bool(run.get("unauthorized_write_detected", False)),
                })
```

---

## 3. Verification

Once applied in `core/multi_agent_service.py` and `core/agent_chat.py`:
1. `scripts/exam_live.py grade <host_dir>` will automatically populate `marks["command_results"]` and `marks["unauthorized_write_detected"]` via `_chat_turn_summary` (`scripts/exam_live.py:297-315`).
2. `exam-code-09` (`command_results_recorded`) and `exam-code-03` (`reviewer_side_effects_none`) will verify end-to-end on live `Quartz.exe` runs without manual mark injection.
