"""Quartz facade that ties real Squad tasks to real local CLI runtimes."""

from __future__ import annotations

import threading
import time
import uuid
import os
import re
import tempfile

from core.antigravity_runtime import AntigravityRuntime
from core.codex_runtime import CodexRuntime
from core.project_registry import ProjectRegistry
from core.squad_adapter import SquadAdapter
from core.workspace_checkpoint import create_checkpoint, snapshot_workspace_files, changed_workspace_files


class MultiAgentService:
    MANAGER_ID = "manager"
    CODEX_ID = "quartz-codex"
    ANTIGRAVITY_ID = "quartz-antigravity"
    ANTIGRAVITY_WRITE_ERROR = (
        "Antigravity Windows CLI çalışma alanı dışına dosya yazabildiği için Proje Yetkisiyle "
        "yazma kapalı. Yazma görevi için Codex seçin."
    )
    ANTIGRAVITY_SAFETY_WARNING = (
        "Windows Antigravity CLI inceleme modunda bile geçici klasöre dosya yazabilir; "
        "bu mod katı salt okunur değildir. Proje dosyalarını değiştirmemesi istenir, fakat "
        "işletim sistemi düzeyinde tam yalıtım sağlanmıyor."
    )

    def __init__(self, projects=None, squad_executable=None, codex_executable=None,
                 antigravity_executable=None, project_store=None):
        self.projects = ProjectRegistry(projects, storage_path=project_store)
        self.codex = CodexRuntime(codex_executable)
        self.antigravity = None
        self._antigravity_error = ""
        try:
            self.antigravity = AntigravityRuntime(antigravity_executable)
        except Exception as exc:
            self._antigravity_error = str(exc)
        self._squad_executable = squad_executable
        self._lock = threading.RLock()
        self._links = {}
        self._probe_cache = (0.0, None)
        self._antigravity_probe_cache = (0.0, None)
        self._squad_conn_cache: dict[str, tuple[float, dict]] = {}
        self._collaborations = {}
        self._writers: dict[str, dict] = {}
        self._file_changes: dict[str, dict] = {}
        self._text_workspaces = {}

    def _start_writer(self, provider: str, project: dict, start, *args, **kwargs) -> dict:
        from pathlib import Path
        key = os.path.normcase(str(Path(project["path"]).resolve()))
        exclusive = bool(kwargs.get("full_access") or kwargs.get("sandbox") == "danger-full-access")
        with self._lock:
            for other_key, writer in self._writers.items():
                other = Path(other_key)
                current = Path(key)
                if exclusive or writer.get("exclusive") or other == current or other in current.parents or current in other.parents:
                    raise RuntimeError("Çakışan proje/tam yetki yazıcısı var; önce o görev tamamlanmalı.")
            self._writers[key] = {"owner": None, "agent": provider, "pending": True, "exclusive": exclusive}
        try:
            checkpoint = create_checkpoint(project["path"])
            if (checkpoint.get("status") not in {"git", "snapshot"}
                    or not checkpoint.get("complete") or not checkpoint.get("archive")):
                raise RuntimeError(checkpoint.get("warning") or "Doğrulanmış checkpoint olmadan yazma başlatılamaz.")
            before = snapshot_workspace_files(project["path"])
            run = start(*args, **kwargs)
            run["checkpoint"] = checkpoint
            with self._lock:
                self._writers[key] = {"owner": run["id"], "agent": provider, "pending": False, "exclusive": exclusive}
            runtime = self.codex if provider == "codex" else self.antigravity
            threading.Thread(target=self._watch_writer,
                             args=(key, run["id"], runtime, project["path"], before),
                             name=f"quartz-writer-{run['id'][:8]}", daemon=True).start()
            return run
        except Exception:
            with self._lock:
                self._writers.pop(key, None)
            raise

    def _watch_writer(self, key: str, run_id: str, runtime, project_path: str, before: dict) -> None:
        try:
            while runtime.get(run_id)["status"] not in runtime.TERMINAL:
                time.sleep(0.15)
            after = snapshot_workspace_files(project_path)
            changed, warning = changed_workspace_files(project_path, before, after)
            with self._lock:
                self._file_changes[run_id] = {"files_changed": changed, "evidence_warning": warning}
        finally:
            with self._lock:
                if self._writers.get(key, {}).get("owner") == run_id:
                    self._writers.pop(key, None)

    def list_models(self, *, force: bool = False) -> dict:
        codex_models = self.codex.list_models(force=force) if hasattr(self.codex, "list_models") else {
            "provider": "codex",
            "default_model": "gpt-6.1-sol",
            "default_effort": "low",
            "efforts": ["low", "medium", "high", "xhigh", "max", "ultra"],
            "models": [],
        }
        if self.antigravity is not None and hasattr(self.antigravity, "list_models"):
            agy_models = self.antigravity.list_models(force=force)
        else:
            agy_models = {
                "provider": "antigravity",
                "default_model": "gemini-4-argon-medium",
                "default_effort": "medium",
                "efforts": ["low", "medium", "high", "xhigh", "max"],
                "models": [],
                "error": self._antigravity_error or "Antigravity CLI is unavailable",
            }
        return {
            "codex": codex_models,
            "antigravity": agy_models,
        }

    def add_project(self, path: str, name: str | None = None) -> dict:
        project = self.projects.add(path, name)
        try:
            squad = self._squad(project["id"])
            squad.initialize()
            connection = self.check_squad_connection(project["id"], force=True)
            project["squad_initialized"] = bool(connection["connected"])
            if not connection["connected"]:
                project["squad_error"] = connection.get("error", "Squad bağlantısı kurulamadı")
        except Exception as exc:
            project["squad_initialized"] = False
            project["squad_error"] = str(exc)
        return project

    def select_project(self, project_id: str) -> dict:
        return self.projects.select(project_id)

    @staticmethod
    def _task_squad_status(squad):
        """Warband has no project-root DB: tasks own isolated evidence DBs."""
        status = squad.status()
        return {**status, "mode": "task-isolated", "ready": bool(status.get("installed")),
                "initialized": False, "database": "", "workspace": "",
                "message": "Squad veritabanı görev başlayınca ayrı kanıt klasöründe oluşturulur."}

    def status(self, project_id=None) -> dict:
        project = self.projects.get(project_id) if project_id else self.projects.selected()
        squad = self._squad(project["id"])
        now = time.monotonic()
        cached_at, codex_status = self._probe_cache
        if codex_status is None or now - cached_at > 60:
            codex_status = self.codex.probe()
            self._probe_cache = (now, codex_status)
        antigravity_status = self._antigravity_status(now)
        error = ""
        if project.get("workflow") == "warband":
            squad_status = self._task_squad_status(squad)
            agents, tasks, history = [], [], []
            error = squad_status.get("error", "")
        else:
            squad_status = squad.status()
            try:
                agents = squad.agents(include_archived=False)
                tasks = squad.tasks()
                history = squad.history()[-30:]
            except Exception as exc:
                agents, tasks, history, error = [], [], [], str(exc)
        return {
            "projects": self.projects.list(), "project": project,
            "squad": squad_status, "codex": codex_status,
            "antigravity": antigravity_status,
            "models": self.list_models(),
            "agents": agents, "tasks": tasks, "history": history,
            "runs": self._enriched_runs(),
            "collaborations": self._collaboration_list(), "error": error,
            "single_writer": self._writer_status(project["path"]),
            "gemini": {
                "status": "retired",
                "message": "Bireysel Gemini CLI erişimi sona erdi; Antigravity kullanılıyor.",
            },
        }

    def dispatch(self, provider, prompt, **kwargs) -> dict:
        provider = str(provider or "codex").strip().lower()
        if provider == "codex":
            return self.dispatch_codex(prompt, **kwargs)
        if provider in {"antigravity", "agy"}:
            return self.dispatch_antigravity(prompt, **kwargs)
        if provider in {"collaboration", "both", "codex-antigravity"}:
            return self.dispatch_collaboration(prompt, **kwargs)
        raise ValueError(f"Unknown agent provider: {provider}")

    def check_squad_connection(self, project_id=None, *, force: bool = False) -> dict:
        try:
            project = self.projects.get(project_id) if project_id else self.projects.selected()
            pid = project["id"]
            now = time.monotonic()
            with self._lock:
                cached = self._squad_conn_cache.get(pid)
                if not force and cached is not None and (now - cached[0]) < 30.0:
                    return dict(cached[1])
            squad = self._squad(pid)
            if project.get("workflow") == "warband":
                return {**self._task_squad_status(squad), "connected": False}
            st = squad.status()
            if not st.get("initialized") or not st.get("installed"):
                res = {
                    "connected": False,
                    "workspace": project["path"],
                    "database": st.get("database", ""),
                    "error": st.get("error") or "Squad çalışma alanı hazır değil.",
                }
                with self._lock:
                    self._squad_conn_cache[pid] = (time.monotonic(), res)
                return dict(res)
            self._ensure_agent(squad, self.MANAGER_ID, client="codex")
            self._ensure_agent(squad, self.CODEX_ID, client="codex")
            self._ensure_agent(squad, self.ANTIGRAVITY_ID, client="gemini")
            res = {
                "connected": True,
                "workspace": project["path"],
                "database": st.get("database", ""),
                "version": st.get("version", ""),
                "error": "",
            }
            with self._lock:
                self._squad_conn_cache[pid] = (time.monotonic(), res)
            return dict(res)
        except Exception as exc:
            return {
                "connected": False,
                "workspace": "",
                "database": "",
                "error": f"Squad bağlantı sorunu: {exc}",
            }

    def squad_create_group_task(self, title: str, body: str, project_id=None) -> dict:
        project = self.projects.get(project_id) if project_id else self.projects.selected()
        squad = self._squad(project["id"])
        self.check_squad_connection(project["id"])
        task = squad.create_task(
            self.MANAGER_ID, self.CODEX_ID,
            str(title or "Grup Sohbeti")[:80],
            str(body or title or "Grup Sohbeti"),
        )
        squad.ack_task(self.CODEX_ID, task["id"])
        return task

    def squad_finish_group_task(self, task_id: str, project_id: str | None,
                                *, completed: bool, summary: str) -> dict:
        project = self.projects.get(project_id) if project_id else self.projects.selected()
        squad = self._squad(project["id"])
        if completed:
            return squad.complete_task(self.CODEX_ID, task_id, summary[:2000])
        return squad.requeue_task(task_id, self.CODEX_ID)

    def squad_send_message(self, sender_id: str, recipient_id: str, content: str,
                           task_id: str | None = None, project_id=None) -> dict:
        project = self.projects.get(project_id) if project_id else self.projects.selected()
        squad = self._squad(project["id"])
        msg_text = self._bridge_text(content)
        effective_task_id = None if str(recipient_id or "").startswith("@") else task_id
        return squad.send(sender_id, recipient_id, msg_text, task_id=effective_task_id)

    def squad_receive_messages(self, agent_id: str, project_id=None) -> list[dict]:
        project = self.projects.get(project_id) if project_id else self.projects.selected()
        squad = self._squad(project["id"])
        msgs = squad.receive(agent_id)
        if msgs:
            return msgs
        # Fallback to latest history directed to agent_id if already marked read
        hist = squad.history(agent_id)
        return hist[-5:] if hist else []

    def _text_conversation(self, provider, prompt, project, *, chat_mode, write, model, effort):
        if chat_mode is not True or write:
            raise PermissionError("Araçsız sohbet işlem/yazma yetkisi alamaz.")
        runtime = self.codex if provider == "codex" else self.antigravity
        probe = runtime.probe()
        if not probe.get("ready"):
            raise RuntimeError(probe.get("error") or "CLI hazır değil")
        workspace = tempfile.TemporaryDirectory(prefix="quartz-text-chat-")
        try:
            if provider == "antigravity":
                from core.chat_coordination import write_observer_hooks
                write_observer_hooks(workspace.name)
            options = {"model": model, "effort": effort, "tool_guard": True}
            options.update({"sandbox":"read-only", "approval":"never"} if provider == "codex"
                           else {"write":False, "timeout":"2m"})
            instruction = ("This is a TEXT-ONLY conversation, not a project task. Answer directly from the "
                "supplied dialogue. Do not call any tools, inspect files, run commands or browse. "
                "Do not claim live verification. No desktop or write permission exists for this turn.\n\n")
            run = runtime.start(instruction + str(prompt), workspace.name, **options)
            run["conversation_only"] = True
            with self._lock:
                self._text_workspaces[run["id"]] = workspace
                self._links[run["id"]] = {"provider":provider, "project_id":project["id"],
                    "task_id":None, "agent_id":None, "reported":True,
                    "coordination_status":"not-required", "coordination_error":""}
            def finish():
                try:
                    while runtime.get(run["id"])["status"] not in runtime.TERMINAL:
                        time.sleep(.15)
                finally:
                    workspace.cleanup()
                    with self._lock:
                        self._text_workspaces.pop(run["id"], None)
            threading.Thread(target=finish, daemon=True, name="quartz-text-cleanup").start()
            return {"run":run, "task":None, "agent_id":None,
                    "squad":{"connected":False, "mode":"conversation-only", "error":""}}
        except Exception:
            workspace.cleanup()
            raise

    def dispatch_codex(self, prompt, *, title=None, project_id=None,
                       write=False, confirm_write=False, full_access=False,
                       resume_thread_id=None, chat_mode=False, squad_task_id=None,
                       model: str | None = None, effort: str | None = None, conversation_only=False) -> dict:
        project = self.projects.get(project_id) if project_id else self.projects.selected()
        if conversation_only:
            return self._text_conversation("codex", prompt, project, chat_mode=chat_mode,
                write=write or full_access, model=model, effort=effort)
        if project.get("protected"):
            raise PermissionError("This project is protected")
        effective_write = bool(write or full_access)
        if effective_write and confirm_write is not True:
            raise PermissionError("Write-capable Codex tasks require explicit confirmation")
        codex_status = self.codex.probe()
        if not codex_status["ready"]:
            raise RuntimeError(codex_status["error"] or "Codex is not ready")

        if chat_mode:
            squad_info = self.check_squad_connection(project["id"])
            agent_id = self.CODEX_ID
            sandbox_mode = "danger-full-access" if full_access else ("workspace-write" if effective_write else "read-only")
            start_kwargs = {
                "sandbox": sandbox_mode,
                "approval": "never" if sandbox_mode == "danger-full-access" else ("on-request" if effective_write else "never"),
                "squad_task_id": squad_task_id,
                "squad_agent_id": agent_id,
                "resume_thread_id": resume_thread_id,
            }
            if model or effort:
                start_kwargs["model"] = model
                start_kwargs["effort"] = effort
            run = (self._start_writer("codex", project, self.codex.start, str(prompt), project["path"], **start_kwargs)
                   if effective_write else self.codex.start(str(prompt), project["path"], **start_kwargs))
            with self._lock:
                self._links[run["id"]] = {
                    "provider": "codex", "project_id": project["id"],
                    "task_id": squad_task_id, "agent_id": agent_id,
                    "reported": True,
                    "coordination_status": "connected" if squad_info["connected"] else "disconnected",
                    "coordination_error": squad_info.get("error", ""),
                    "checkpoint": run.get("checkpoint"),
                }
            return {
                "task": {"id": squad_task_id} if squad_task_id else None,
                "run": run, "agent_id": agent_id, "squad": squad_info,
            }

        squad = self._squad(project["id"])
        agent_id = self._ensure_agent(squad, self.CODEX_ID)
        task = squad.create_task(
            self.MANAGER_ID, agent_id,
            title or str(prompt).strip()[:80] or "Quartz Codex task",
            str(prompt),
        )
        squad.ack_task(agent_id, task["id"])
        instruction = (
            f"You are the real Codex runtime assigned to Squad task {task['id']}.\n"
            f"Project: {project['path']}\n"
            f"Task: {prompt}\n\n"
            "Return a concise factual result. Do not run squad CLI commands from shell; Quartz manages Squad reporting on the host. "
            "Do not claim an action succeeded unless you observed it."
        )
        try:
            start_kwargs = {
                "sandbox": "danger-full-access" if full_access else ("workspace-write" if effective_write else "read-only"),
                "approval": "on-request" if write and not full_access else "never",
                "squad_task_id": task["id"],
                "squad_agent_id": agent_id,
                "resume_thread_id": resume_thread_id,
            }
            if model or effort:
                start_kwargs["model"] = model
                start_kwargs["effort"] = effort
            starter = self._start_writer if effective_write else None
            run = (starter("codex", project, self.codex.start, instruction, project["path"], **start_kwargs)
                   if starter else self.codex.start(instruction, project["path"], **start_kwargs))
        except Exception:
            squad.requeue_task(task["id"], agent_id)
            raise
        with self._lock:
            self._links[run["id"]] = {
                "provider": "codex", "project_id": project["id"], "task_id": task["id"],
                "agent_id": agent_id, "reported": False,
                "coordination_status": "running", "coordination_error": "",
                "checkpoint": run.get("checkpoint"),
            }
        threading.Thread(
            target=self._report_completion, args=("codex", run["id"]),
            name=f"squad-report-{run['id'][:8]}", daemon=True,
        ).start()
        return {"task": task, "run": run, "agent_id": agent_id}

    def dispatch_antigravity(self, prompt, *, title=None, project_id=None,
                             write=False, confirm_write=False, full_access=False,
                             conversation_id=None, chat_mode=False, squad_task_id=None,
                             model: str | None = None, effort: str | None = None, conversation_only=False) -> dict:
        if self.antigravity is None:
            raise RuntimeError(self._antigravity_error or "Antigravity CLI is unavailable")
        project = self.projects.get(project_id) if project_id else self.projects.selected()
        if conversation_only:
            return self._text_conversation("antigravity", prompt, project, chat_mode=chat_mode,
                write=write or full_access, model=model, effort=effort)
        if project.get("protected"):
            raise PermissionError("This project is protected")
        effective_write = bool(write or full_access)
        if effective_write and confirm_write is not True:
            raise PermissionError("Write-capable Antigravity tasks require explicit confirmation")
        if effective_write and not full_access:
            raise PermissionError(self.ANTIGRAVITY_WRITE_ERROR)
        if effective_write and not chat_mode and self._writer_status(project["path"])["locked"]:
            raise RuntimeError("This project already has an active write-capable agent")
        status = self.antigravity.probe()
        if not status["ready"]:
            raise RuntimeError(status["error"] or "Antigravity is not ready")

        if chat_mode:
            squad_info = self.check_squad_connection(project["id"])
            agent_id = self.ANTIGRAVITY_ID
            start_kwargs = {
                "write": effective_write,
                "full_access": bool(full_access),
                "squad_task_id": squad_task_id,
                "squad_agent_id": agent_id,
                "conversation_id": conversation_id,
            }
            if model or effort:
                start_kwargs["model"] = model
                start_kwargs["effort"] = effort
            run = (self._start_writer("antigravity", project, self.antigravity.start, str(prompt), project["path"], **start_kwargs)
                   if effective_write else self.antigravity.start(str(prompt), project["path"], **start_kwargs))
            with self._lock:
                self._links[run["id"]] = {
                    "provider": "antigravity", "project_id": project["id"],
                    "task_id": squad_task_id, "agent_id": agent_id,
                    "reported": True,
                    "coordination_status": "connected" if squad_info["connected"] else "disconnected",
                    "coordination_error": squad_info.get("error", ""),
                    "bridge": "squad-cli",
                    "checkpoint": run.get("checkpoint"),
                }
            return {
                "task": {"id": squad_task_id} if squad_task_id else None,
                "run": run, "agent_id": agent_id,
                "bridge": "squad-cli", "squad": squad_info,
            }

        squad = self._squad(project["id"])
        agent_id = self._ensure_agent(
            squad, self.ANTIGRAVITY_ID, client="gemini",
        )
        task = squad.create_task(
            self.MANAGER_ID, agent_id,
            title or str(prompt).strip()[:80] or "Quartz Antigravity task",
            str(prompt),
        )
        squad.ack_task(agent_id, task["id"])
        instruction = (
            f"You are the real Google Antigravity runtime connected through the Quartz Squad bridge.\n"
            f"Squad task: {task['id']}\nProject: {project['path']}\nTask: {prompt}\n\n"
            "Return a concise factual result. Do not claim success without observed evidence. "
            + ("You may modify project files as requested." if effective_write else
               "Do not modify files; inspect and answer only.")
        )
        try:
            start_kwargs = {
                "write": effective_write,
                "squad_task_id": task["id"],
                "squad_agent_id": agent_id,
                "conversation_id": conversation_id,
            }
            if full_access:
                start_kwargs["full_access"] = True
            if model or effort:
                start_kwargs["model"] = model
                start_kwargs["effort"] = effort
            starter = self._start_writer if effective_write else None
            run = (starter("antigravity", project, self.antigravity.start, instruction, project["path"], **start_kwargs)
                   if starter else self.antigravity.start(instruction, project["path"], **start_kwargs))
        except Exception:
            squad.requeue_task(task["id"], agent_id)
            raise
        with self._lock:
            self._links[run["id"]] = {
                "provider": "antigravity", "project_id": project["id"],
                "task_id": task["id"], "agent_id": agent_id,
                "reported": False, "coordination_status": "running",
                "coordination_error": "", "bridge": "squad-cli",
                "checkpoint": run.get("checkpoint"),
            }
        threading.Thread(
            target=self._report_completion, args=("antigravity", run["id"]),
            name=f"squad-report-{run['id'][:8]}", daemon=True,
        ).start()
        return {"task": task, "run": run, "agent_id": agent_id,
                "bridge": "squad-cli"}

    @staticmethod
    def validate_model_selections(models, *, agents=("codex", "antigravity")) -> dict:
        """Never let a missing/invalid explicit selection become a CLI default."""
        if not isinstance(models, dict):
            raise ValueError("Model seçimleri gerekli; sohbet modelini açıkça seçin.")
        result = {}
        for agent in agents:
            cfg = models.get(agent)
            if not isinstance(cfg, dict):
                raise ValueError(f"{agent}: model ve düşünme seviyesi gerekli.")
            model, effort = cfg.get("model"), cfg.get("effort")
            if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", model):
                raise ValueError(f"{agent}: geçerli, açık bir model seçimi gerekli.")
            allowed = CodexRuntime.SUPPORTED_EFFORTS if agent == "codex" else AntigravityRuntime.SUPPORTED_EFFORTS
            if not isinstance(effort, str) or effort not in allowed:
                raise ValueError(f"{agent}: geçersiz düşünme seviyesi.")
            result[agent] = {"model": model, "effort": effort}
        return result

    def dispatch_collaboration(self, prompt, *, title=None, project_id=None,
                               write=False, confirm_write=False, models=None) -> dict:
        if write:
            raise PermissionError("Collaborative runs are read-only in this release")
        if confirm_write:
            raise PermissionError("Collaborative runs do not accept write confirmation")
        selections = self.validate_model_selections(models)
        if self.antigravity is None:
            raise RuntimeError(self._antigravity_error or "Antigravity CLI is unavailable")
        project = self.projects.get(project_id) if project_id else self.projects.selected()
        if not self.codex.probe()["ready"]:
            raise RuntimeError("Codex is not ready")
        agy_status = self.antigravity.probe()
        if not agy_status["ready"]:
            raise RuntimeError(agy_status["error"] or "Antigravity is not ready")
        collaboration_id = uuid.uuid4().hex
        record = {
            "id": collaboration_id, "status": "starting", "prompt": str(prompt),
            "title": title or str(prompt).strip()[:80], "project_id": project["id"],
            "run_ids": [], "task_ids": [], "messages": [], "result": "",
            "error": "", "started_at": time.time(), "finished_at": None,
            "models": selections,
        }
        with self._lock:
            self._collaborations[collaboration_id] = record
        threading.Thread(
            target=self._collaboration_worker, args=(collaboration_id,),
            name=f"agent-pair-{collaboration_id[:8]}", daemon=True,
        ).start()
        return {"collaboration": dict(record)}

    def get_run(self, run_id: str) -> dict:
        with self._lock:
            provider = self._links.get(run_id, {}).get("provider")
            evidence = dict(self._file_changes.get(run_id, {}))
        if provider == "antigravity" and self.antigravity:
            run = self.antigravity.get(run_id)
            return self._with_file_evidence(run, evidence)
        if self.codex:
            try:
                return self._with_file_evidence(self.codex.get(run_id), evidence)
            except KeyError:
                if self.antigravity:
                    return self._with_file_evidence(self.antigravity.get(run_id), evidence)
                raise

    @staticmethod
    def _with_file_evidence(run: dict, evidence: dict) -> dict:
        if evidence:
            run["files_changed"] = sorted(set(run.get("files_changed", [])) |
                                          set(evidence.get("files_changed", [])))
            run["evidence_warning"] = evidence.get("evidence_warning", "")
        return run
        raise KeyError(f"Run not found: {run_id}")

    def get_collaboration(self, collaboration_id: str) -> dict:
        with self._lock:
            if collaboration_id not in self._collaborations:
                raise KeyError(f"Collaboration not found: {collaboration_id}")
            return dict(self._collaborations[collaboration_id])

    def cancel_collaboration(self, collaboration_id: str) -> dict:
        with self._lock:
            if collaboration_id not in self._collaborations:
                raise KeyError(f"Collaboration not found: {collaboration_id}")
            collab = self._collaborations[collaboration_id]
            collab["status"] = "cancelling"
            collab["cancel_requested"] = True
            active_runs = list(collab.get("run_ids", []))

        # Tüm aktif alt çalıştırmaları iptal et
        for run_id in active_runs:
            try:
                self.cancel(run_id)
            except Exception:
                pass

        with self._lock:
            collab["status"] = "cancelled"
            collab["finished_at"] = time.time()
            return dict(collab)

    def cancel(self, run_id) -> dict:
        # The completion watcher is the single reporter and requeues a
        # cancelled run exactly once after the owned process has stopped.
        with self._lock:
            if run_id in self._links:
                self._links[run_id]["coordination_status"] = "cancelling"
        with self._lock:
            provider = self._links.get(run_id, {}).get("provider", "codex")
        runtime = self.antigravity if provider == "antigravity" else self.codex
        if runtime is None:
            raise RuntimeError("Runtime is unavailable")
        return runtime.cancel(run_id)

    def shutdown(self):
        self.codex.shutdown()
        if self.antigravity is not None:
            self.antigravity.shutdown()

    def _squad(self, project_id) -> SquadAdapter:
        path = self.projects.resolve(project_id)
        return SquadAdapter(path, executable=self._squad_executable)

    @staticmethod
    def _ensure_agent(squad, desired_id, client="codex"):
        active = {item["id"] for item in squad.agents()}
        if desired_id in active:
            return desired_id
        return squad.join(
            desired_id, role="worker", client=client, protocol_version=2,
        )["id"]

    def _report_completion(self, provider, run_id):
        runtime = self.antigravity if provider == "antigravity" else self.codex
        if runtime is None:
            return
        while True:
            run = runtime.get(run_id)
            if run["status"] in runtime.TERMINAL:
                break
            time.sleep(0.25)
        with self._lock:
            link = self._links.get(run_id)
            if not link or link["reported"]:
                return
            link["reported"] = True
            link["coordination_status"] = "reporting"
            link = dict(link)
        squad = self._squad(link["project_id"])
        try:
            if run["status"] == "completed":
                summary = run["result"].strip() or "Codex task completed"
                squad.complete_task(link["agent_id"], link["task_id"], summary[:50_000])
                report_status = "completed"
            else:
                squad.requeue_task(link["task_id"], link["agent_id"])
                report_status = "requeued"
            with self._lock:
                self._links[run_id]["coordination_status"] = report_status
        except Exception as exc:
            with self._lock:
                self._links[run_id]["coordination_status"] = "error"
                self._links[run_id]["coordination_error"] = str(exc)

    def _enriched_runs(self) -> list[dict]:
        runs = []
        for run in self.codex.list():
            run.setdefault("provider", "codex")
            runs.append(run)
        if self.antigravity is not None:
            runs.extend(self.antigravity.list())
        runs.sort(key=lambda item: item.get("started_at", 0), reverse=True)
        with self._lock:
            links = {key: dict(value) for key, value in self._links.items()}
            evidence = {key: dict(value) for key, value in self._file_changes.items()}
        for run in runs:
            self._with_file_evidence(run, evidence.get(run["id"], {}))
            link = links.get(run["id"], {})
            run["coordination_status"] = link.get("coordination_status", "not_linked")
            run["coordination_error"] = link.get("coordination_error", "")
            run["checkpoint"] = link.get("checkpoint")
        return runs

    def _writer_status(self, project_path):
        with self._lock:
            writer = self._writers.get(os.path.normcase(str(project_path)))
            if writer:
                return {"locked": True, **writer}
        return {"locked": False, "owner": None, "agent": None}

    def _antigravity_status(self, now):
        if self.antigravity is None:
            return {
                "installed": False, "version": "", "authenticated": False,
                "authentication": "required", "ready": False,
                "error": self._antigravity_error or "Antigravity CLI is unavailable",
                "bridge": "squad-cli",
            }
        cached_at, status = self._antigravity_probe_cache
        if status is None or now - cached_at > 60:
            status = self.antigravity.probe()
            self._antigravity_probe_cache = (now, status)
        value = dict(status)
        value["bridge"] = "squad-cli"
        value["write_safety_blocked"] = True
        value["safety_warning"] = self.ANTIGRAVITY_SAFETY_WARNING
        return value

    def _collaboration_list(self):
        with self._lock:
            values = [dict(value) for value in self._collaborations.values()]
        return list(reversed(values[-20:]))

    @staticmethod
    def _wait_for(runtime, run_id):
        while True:
            run = runtime.get(run_id)
            if run["status"] in runtime.TERMINAL:
                return run
            time.sleep(0.25)

    def _is_collaboration_cancelled(self, collaboration_id: str) -> bool:
        with self._lock:
            collab = self._collaborations.get(collaboration_id)
            if not collab:
                return True
            if collab.get("cancel_requested") or collab.get("status") in {"cancelling", "cancelled"}:
                collab["status"] = "cancelled"
                if not collab.get("finished_at"):
                    collab["finished_at"] = time.time()
                return True
            return False

    def _collaboration_worker(self, collaboration_id):
        if self._is_collaboration_cancelled(collaboration_id):
            return
        with self._lock:
            record = dict(self._collaborations[collaboration_id])
            self._collaborations[collaboration_id]["status"] = "codex-working"
        phase, provider = "analysis", "codex"
        cfg = {}
        try:
            selections = self.validate_model_selections(record.get("models"))
            cfg = selections["codex"]
            if self._is_collaboration_cancelled(collaboration_id):
                return
            first = self.dispatch_codex(
                "You are ONLY the first Codex analyst. Quartz will invoke the real Antigravity reviewer "
                "and the final synthesis separately AFTER you finish. Do not spawn or simulate reviewers, "
                "perform later phases, or claim another provider was unavailable. Return only your analysis.\n\n"
                + record["prompt"], title=f"{record['title']} · Codex analysis",
                project_id=record["project_id"], write=False, **cfg,
            )
            self._remember_collaboration_run(collaboration_id, first)
            codex_run = self._wait_for(self.codex, first["run"]["id"])
            if self._is_collaboration_cancelled(collaboration_id):
                return
            if codex_run["status"] != "completed":
                raise RuntimeError(self._runtime_failure_detail(codex_run))

            if self._is_collaboration_cancelled(collaboration_id):
                return

            squad = self._squad(record["project_id"])
            self._ensure_agent(squad, self.ANTIGRAVITY_ID, client="gemini")
            message = self._bridge_text(
                f"Codex analysis for review:\n{codex_run['result']}"
            )
            squad.send(self.CODEX_ID, self.ANTIGRAVITY_ID, message)
            self._remember_message(collaboration_id, self.CODEX_ID, self.ANTIGRAVITY_ID, message)

            if self._is_collaboration_cancelled(collaboration_id):
                return

            with self._lock:
                self._collaborations[collaboration_id]["status"] = "antigravity-reviewing"
            phase, provider, cfg = "review", "antigravity", selections["antigravity"]

            review_prompt = self._bridge_text(
                f"Original task:\n{record['prompt']}\n\n"
                f"Codex analysis:\n{codex_run['result']}\n\n"
                "Independently inspect the relevant files in the current project using read-only file tools. "
                "Compare your own findings with the Codex analysis, identify omissions or mistakes, and return a concise review. "
                "Do not modify files, run commands, access the network, or inspect paths outside this project. "
                "If read-only file access is denied, explicitly say which evidence could not be checked.", limit=95_000,
            )
            second = self.dispatch_antigravity(
                review_prompt, title=f"{record['title']} · Antigravity review",
                project_id=record["project_id"], write=False, **cfg,
            )
            self._remember_collaboration_run(collaboration_id, second)
            agy_run = self._wait_for(self.antigravity, second["run"]["id"])

            if self._is_collaboration_cancelled(collaboration_id):
                return

            if (agy_run["status"] != "completed" and self._is_permission_denial(agy_run)
                    and not self._is_quota_failure(agy_run)):
                if self._is_collaboration_cancelled(collaboration_id):
                    return
                with self._lock:
                    self._collaborations[collaboration_id]["status"] = "antigravity-retrying"
                retry_prompt = self._bridge_text(
                    "Your previous review attempt requested a tool that headless safe mode denied. "
                    "Complete the review from the embedded text only. You MUST NOT invoke any tool or command.\n\n"
                    + review_prompt,
                    limit=95_000,
                )
                retry = self.dispatch_antigravity(
                    retry_prompt,
                    title=f"{record['title']} · Antigravity safe retry",
                    project_id=record["project_id"], write=False, **cfg,
                )
                self._remember_collaboration_run(collaboration_id, retry)
                agy_run = self._wait_for(self.antigravity, retry["run"]["id"])

            if self._is_collaboration_cancelled(collaboration_id):
                return

            if agy_run["status"] != "completed":
                raise RuntimeError(self._runtime_failure_detail(agy_run))

            feedback = self._bridge_text(
                f"Antigravity review:\n{agy_run['result']}"
            )
            squad.send(self.ANTIGRAVITY_ID, self.CODEX_ID, feedback)
            self._remember_message(collaboration_id, self.ANTIGRAVITY_ID, self.CODEX_ID, feedback)

            if self._is_collaboration_cancelled(collaboration_id):
                return

            with self._lock:
                self._collaborations[collaboration_id]["status"] = "codex-synthesizing"
            phase, provider, cfg = "synthesis", "codex", selections["codex"]

            final_prompt = self._bridge_text(
                f"Original task:\n{record['prompt']}\n\n"
                f"Your first analysis:\n{codex_run['result']}\n\n"
                f"Antigravity review:\n{agy_run['result']}\n\n"
                "Produce the final reconciled answer. Do not modify files. "
                "If the real review only had embedded text or lacked file access, retain that limitation; "
                "do not label it independent source verification.", limit=95_000,
            )
            final = self.dispatch_codex(
                final_prompt, title=f"{record['title']} · Final synthesis",
                project_id=record["project_id"], write=False, **cfg,
            )
            self._remember_collaboration_run(collaboration_id, final)
            final_run = self._wait_for(self.codex, final["run"]["id"])

            if self._is_collaboration_cancelled(collaboration_id):
                return

            if final_run["status"] != "completed":
                raise RuntimeError(self._runtime_failure_detail(final_run))
            final_message = self._bridge_text(
                f"Final Codex synthesis:\n{final_run['result']}"
            )
            squad.send(self.CODEX_ID, self.ANTIGRAVITY_ID, final_message)
            self._remember_message(collaboration_id, self.CODEX_ID, self.ANTIGRAVITY_ID, final_message)
            with self._lock:
                item = self._collaborations[collaboration_id]
                item["status"] = "completed"
                item["result"] = final_run["result"]
                item["finished_at"] = time.time()
        except Exception as exc:
            with self._lock:
                item = self._collaborations[collaboration_id]
                if item.get("cancel_requested") or item.get("status") in {"cancelling", "cancelled"}:
                    item["status"] = "cancelled"
                    if not item.get("finished_at"):
                        item["finished_at"] = time.time()
                    return
                item["status"] = "failed"
                item["error"] = f"{provider} · model={cfg.get('model', 'not selected')} · effort={cfg.get('effort', 'not selected')} · {phase}: {exc}"
                item["failed_provider"] = provider
                item["failed_model"] = cfg.get("model")
                item["failed_phase"] = phase
                item["failure_kind"] = "quota" if self._is_quota_failure({"errors": [str(exc)]}) else "runtime"
                item["finished_at"] = time.time()

    def _remember_collaboration_run(self, collaboration_id, dispatch):
        with self._lock:
            item = self._collaborations[collaboration_id]
            item["run_ids"].append(dispatch["run"]["id"])
            item["task_ids"].append(dispatch["task"]["id"])

    def _remember_message(self, collaboration_id, sender, recipient, content):
        with self._lock:
            self._collaborations[collaboration_id]["messages"].append({
                "from": sender, "to": recipient, "content": content,
            })

    @staticmethod
    def _runtime_failure_detail(run):
        errors = [str(error) for error in run.get("errors", []) if error]
        return "\n".join(errors[-3:])[-1800:] or f"Runtime failed (exit={run.get('exit_code', 'unknown')})"

    @staticmethod
    def _is_quota_failure(run):
        text = "\n".join(str(error) for error in run.get("errors", [])).lower()
        return any(word in text for word in ("quota", "resource_exhausted", "rate limit", "rate_limit"))

    @staticmethod
    def _is_permission_denial(run):
        errors = "\n".join(str(item) for item in run.get("errors", []))
        lowered = errors.lower()
        return "permission policy denied" in lowered or "permission" in lowered and "auto-denied" in lowered

    @staticmethod
    def _bridge_text(value, limit=49_000):
        text = str(value or "")
        if len(text) <= limit:
            return text
        return text[:limit] + "\n[Quartz bridge truncated this message]"
