"""Long jobs: hours of work split into milestones (user request 14-15 Nov 2026).

A job is a goal, a project folder, milestones with acceptance criteria and a deadline.
Its ledger lives outside the project (%LOCALAPPDATA%/Quartz/jobs/<id>/ledger.json) and is
the job's memory: every milestone prompt is built from it, never from hours of chat.

Each milestone: checkpoint -> one existing chat turn (the single writer builds) -> the
job's own host-defined check -> Git commit of the files that milestone changed.

User decisions (15 Nov, 00:02):
- A job started with auto_resume continues by itself after SpeS restarts, but never after
  Stop, never past its deadline, never with wider permissions, and pauses after three
  crashes on the same milestone.
- When the writer hits its usage limit the writer role moves on (Fatum -> Fides -> Eos);
  still one writer at a time. The preferred writer returns once its limit resets.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json

WRITER_ORDER = ("claude", "codex", "antigravity")
PERSONA = {"claude": "Fatum", "codex": "Fides", "antigravity": "Eos"}
LIMIT_PERCENT = 95
MAX_ATTEMPTS = 3
MAX_CRASHES = 3
LIMIT_FALLBACK_SECONDS = 60 * 60
ACTIVE = {"running", "waiting_limit"}
FINAL = {"done", "stopped", "expired", "failed"}


class JobError(ValueError):
    """The job cannot be created or changed."""


def jobs_root() -> Path:
    return Path(os.getenv("QUARTZ_JOBS_HOME") or
                Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Quartz" / "jobs")


def _git(root, *args, timeout=60):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, check=False,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _reset_time(value):
    """agent_limits gives epoch seconds or ISO text; None when unknown."""
    if value in (None, ""):
        return None
    try:
        number = float(value)
        return number / 1000 if number > 1e12 else number
    except (TypeError, ValueError):
        pass
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def validate_spec(spec: dict) -> dict:
    """The job as the user approved it. Nothing here comes from an agent."""
    if not isinstance(spec, dict):
        raise JobError("İş tanımı geçersiz.")
    goal = str(spec.get("goal") or "").strip()
    if not goal:
        raise JobError("İşin hedefi boş olamaz.")
    root = Path(str(spec.get("project_path") or ""))
    if not root.is_dir():
        raise JobError("Proje klasörü bulunamadı.")
    milestones = []
    for index, item in enumerate(spec.get("milestones") or [], 1):
        title = str((item or {}).get("title") or "").strip()
        acceptance = str((item or {}).get("acceptance") or "").strip()
        if not title or not acceptance:
            raise JobError(f"{index}. kilometre taşının başlığı ve kabul ölçütü olmalı.")
        milestones.append({"id": f"m{index}", "title": title[:200], "acceptance": acceptance[:2000],
                           "status": "pending", "attempts": 0, "crashes": 0, "writer": None,
                           "commit": None, "checkpoint": None, "last_failure": "", "history": []})
    if not milestones:
        raise JobError("En az bir kilometre taşı gerekli.")
    hours = float(spec.get("hours") or 0)
    if not 0.05 <= hours <= 12:
        raise JobError("İş süresi 3 dakika ile 12 saat arasında olmalı.")
    verify = spec.get("verify")
    if verify is not None:
        if not (isinstance(verify, list) and verify and all(isinstance(a, str) and a for a in verify)):
            raise JobError("Kontrol komutu argüman listesi olmalı.")
    branch = spec.get("git_branch")
    if branch is not None:
        branch = str(branch).strip()
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,80}", branch) or ".." in branch or branch.startswith(("-", "/")):
            raise JobError("Git dalı adı geçersiz.")
    return {"goal": goal[:4000], "project_path": str(root.resolve()),
            "conversation_id": str(spec.get("conversation_id") or ""),
            "milestones": milestones, "hours": hours, "auto_resume": bool(spec.get("auto_resume")),
            "verify": verify, "verify_timeout": int(spec.get("verify_timeout") or 900),
            "git_branch": branch, "models": dict(spec.get("models") or {}),
            "permission_level": "full" if spec.get("permission_level") == "full" else "project",
            "permissions": dict(spec.get("permissions") or {})}


class JobLedger:
    """One job's durable state. Only the job's runner writes it."""

    def __init__(self, path: Path, data: dict):
        self.path, self.data = Path(path), data
        self._lock = threading.RLock()

    @classmethod
    def create(cls, spec: dict, *, root: Path | None = None, clock=time.time):
        clean = validate_spec(spec)
        now = clock()
        job_id = time.strftime("%Y%m%d-%H%M%S-", time.localtime(now)) + uuid.uuid4().hex[:6]
        data = {**clean, "id": job_id, "created_at": now, "deadline": now + clean["hours"] * 3600,
                "status": "created", "stopped": False, "writer": None, "limited": {},
                "decisions": [], "events": []}
        ledger = cls(Path(root or jobs_root()) / job_id / "ledger.json", data)
        ledger.save()
        return ledger

    @classmethod
    def load(cls, path: Path):
        data = load_json(path, None)
        if not isinstance(data, dict) or not data.get("id"):
            raise JobError("İş defteri okunamadı.")
        return cls(path, data)

    @classmethod
    def all(cls, root: Path | None = None):
        found = []
        for path in sorted(Path(root or jobs_root()).glob("*/ledger.json")):
            try:
                found.append(cls.load(path))
            except JobError:
                continue
        return found

    def save(self):
        with self._lock:
            atomic_write_json(self.path, self.data)

    def event(self, text, clock=time.time):
        with self._lock:
            self.data["events"] = (self.data["events"] + [{"at": clock(), "text": str(text)[:500]}])[-200:]
            self.save()

    def current(self):
        return next((m for m in self.data["milestones"] if m["status"] in {"pending", "running"}), None)

    def summary(self) -> str:
        """What every writer reads first: the job's memory, not the chat."""
        d = self.data
        lines = [f"HEDEF: {d['goal']}", "KİLOMETRE TAŞLARI:"]
        for m in d["milestones"]:
            mark = {"done": "✔", "needs_user": "?", "running": "→"}.get(m["status"], "·")
            lines.append(f" {mark} {m['id']} {m['title']} [{m['status']}]"
                         + (f" (commit {m['commit'][:8]})" if m.get("commit") else ""))
        if d["decisions"]:
            lines.append("KARARLAR:")
            lines += [f" - {x['text']}" for x in d["decisions"][-10:]]
        return "\n".join(lines)

    def public(self) -> dict:
        d = self.data
        return {k: d.get(k) for k in ("id", "goal", "status", "deadline", "writer", "auto_resume", "git_branch", "permission_level",
                                  "project_path", "conversation_id", "created_at")} | {
            "milestones": [{k: m[k] for k in ("id", "title", "status", "attempts", "writer", "commit")}
                           for m in d["milestones"]],
            "events": d["events"][-20:]}


def resumable(ledger: JobLedger, now: float) -> str:
    """'resume' | 'pause' | '' for a job found at startup (user decision 15 Nov)."""
    d = ledger.data
    if d.get("stopped") or d["status"] in FINAL or d["status"] in {"paused", "needs_user", "created"}:
        return ""
    if d["status"] not in ACTIVE:
        return ""
    if now >= d["deadline"]:
        return ""
    return "resume" if d.get("auto_resume") else "pause"


@contextmanager
def keep_awake():
    """Windows must not sleep while a job runs; the display may turn off."""
    setter = None
    try:
        import ctypes
        setter = ctypes.windll.kernel32.SetThreadExecutionState
        setter(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    except Exception:
        setter = None
    try:
        yield
    finally:
        if setter is not None:
            try:
                setter(0x80000000)
            except Exception:
                pass


def run_verify(ledger: JobLedger, stop: threading.Event) -> dict:
    """The job's own check, defined by the user when the job started (never by an agent)."""
    argv = ledger.data.get("verify")
    if not argv:
        return {"ok": True, "summary": "Kontrol komutu tanımlanmadı."}
    from core.process_tree import stop_process_tree
    try:
        process = subprocess.Popen(argv, cwd=ledger.data["project_path"], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        return {"ok": False, "summary": f"Kontrol başlatılamadı: {exc}"}
    deadline = time.monotonic() + ledger.data.get("verify_timeout", 900)
    output = []
    reader = threading.Thread(target=lambda: output.append(process.stdout.read()), daemon=True)
    reader.start()
    while process.poll() is None:
        if stop.is_set() or time.monotonic() > deadline:
            stop_process_tree(process, timeout=5)
            return {"ok": False, "summary": "Kontrol durduruldu." if stop.is_set() else "Kontrol süreyi aştı."}
        time.sleep(0.5)
    reader.join(5)
    tail = "".join(output)[-1500:]
    return {"ok": process.returncode == 0, "exit_code": process.returncode, "summary": tail}


def git_commit(ledger: JobLedger, files: list[str], message: str) -> str | None:
    """Commit only the files this milestone changed, on the job's branch."""
    branch = ledger.data.get("git_branch")
    root = Path(ledger.data["project_path"])
    if not branch or not files:
        return None
    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if current.returncode != 0 or current.stdout.strip() != branch:
        raise JobError(f"Proje '{branch}' dalında değil; commit atılmadı.")
    relative = []
    for name in files:
        try:
            relative.append(Path(name).resolve().relative_to(root.resolve()).as_posix())
        except ValueError:
            continue
    if relative:
        # Ignored files (Godot's .godot cache, logs) are never committed; `git add` refuses them.
        ignored = _git(root, "check-ignore", "--", *relative)
        # Forward slashes only: git quotes backslash paths in its output.
        skip = {line.strip() for line in ignored.stdout.splitlines() if line.strip()}
        relative = [r for r in relative if r not in skip and not _build_junk(r)]
    if not relative:
        return None
    added = _git(root, "add", "-A", "--", *relative)
    if added.returncode != 0:
        raise JobError("git add başarısız: " + added.stderr.strip()[:300])
    staged = _git(root, "diff", "--cached", "--name-only")
    if not staged.stdout.strip():
        return None
    done = _git(root, "commit", "-m", message, "--only", "--", *relative)
    if done.returncode != 0:
        raise JobError("git commit başarısız: " + (done.stderr or done.stdout).strip()[:300])
    return _git(root, "rev-parse", "HEAD").stdout.strip()


BASELINE_MAX_BYTES = 4 * 1024 ** 3


def baseline_checkpoint(ledger: JobLedger) -> dict:
    """One full copy of the project (tracked + the user's untracked files) at job start."""
    from core.workspace_checkpoint import create_checkpoint
    return create_checkpoint(ledger.data["project_path"], max_bytes=BASELINE_MAX_BYTES)


def milestone_checkpoint(ledger: JobLedger) -> dict:
    """Per milestone: the job branch's last commit is the restore point (the baseline holds
    the user's files). Without a job branch, a bounded full checkpoint as before."""
    if ledger.data.get("git_branch"):
        head = _git(ledger.data["project_path"], "rev-parse", "HEAD")
        if head.returncode == 0 and head.stdout.strip():
            return {"status": "git-head", "ref": head.stdout.strip()}
    from core.workspace_checkpoint import create_checkpoint
    return create_checkpoint(ledger.data["project_path"])


JUNK_SUFFIXES = (".pyc", ".pyo", ".blend1", ".blend2", ".tmp")


def _build_junk(relative: str) -> bool:
    """Caches and tool backups never go into a milestone commit (live 15 Nov: .pyc, .blend1)."""
    return "__pycache__/" in relative or relative.lower().endswith(JUNK_SUFFIXES)


def dirty_paths(ledger: JobLedger) -> dict:
    """{posix path: [size, mtime_ns] or None if deleted} for every non-ignored uncommitted path."""
    root = Path(ledger.data["project_path"])
    status = _git(root, "status", "--porcelain", "-z", "--untracked-files=all")
    if status.returncode != 0:
        return {}
    found, entries, index = {}, status.stdout.split("\0"), 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        code, name = entry[:2], entry[3:]
        if code[0] in "RC":
            index += 1  # the rename source follows
        path = root / name
        try:
            stat = path.stat()
            found[name] = [stat.st_size, stat.st_mtime_ns]
        except OSError:
            found[name] = None
    return found


def prepare_branch(ledger: JobLedger):
    """Switch to the job's branch once, keeping the user's uncommitted files as they are."""
    branch = ledger.data.get("git_branch")
    if not branch:
        return
    root = ledger.data["project_path"]
    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if current.returncode != 0:
        raise JobError("Proje bir Git deposu değil; dal kullanılamaz.")
    if current.stdout.strip() == branch:
        return
    exists = _git(root, "rev-parse", "--verify", "--quiet", "refs/heads/" + branch).returncode == 0
    switched = _git(root, "switch", branch) if exists else _git(root, "switch", "-c", branch)
    if switched.returncode != 0:
        raise JobError("Dala geçilemedi: " + (switched.stderr or switched.stdout).strip()[:300])


class LongJob:
    """Runs one ledger's milestones. Callbacks keep it independent of the chat service."""

    def __init__(self, ledger: JobLedger, *, run_milestone, verify=None, checkpoint=None, baseline=None, dirty=None,
                 snapshot=None,
                 changed=None, commit=None, limits=None, notify=None, clock=time.time, awake=keep_awake):
        self.ledger = ledger
        self.run_milestone = run_milestone
        self.verify = verify or (lambda stop: run_verify(ledger, stop))
        self.checkpoint = checkpoint or (lambda: milestone_checkpoint(ledger))
        self.baseline = baseline or (lambda: baseline_checkpoint(ledger))
        from core.workspace_checkpoint import changed_workspace_files, snapshot_workspace_files
        self.snapshot = snapshot or (lambda: snapshot_workspace_files(ledger.data["project_path"]))
        self.changed = changed or (lambda before, after: changed_workspace_files(
            ledger.data["project_path"], before, after)[0])
        self.commit = commit or (lambda files, message: git_commit(ledger, files, message))
        self.dirty = dirty or (lambda: dirty_paths(ledger))
        self.limits = limits or (lambda: {})
        self.notify = notify or (lambda text, urgent=False: None)
        self.clock, self.awake = clock, awake
        self.stop_event, self.pause_event, self.wake = threading.Event(), threading.Event(), threading.Event()
        self.thread = None
        self._halt = False

    # -- control ---------------------------------------------------------------------
    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, name=f"spes-job-{self.ledger.data['id']}", daemon=True)
            self.thread.start()

    def pause(self):
        self.pause_event.set()
        self.wake.set()

    def resume(self):
        if self.ledger.data.get("stopped"):
            raise JobError("Durdurulmuş iş devam ettirilemez.")
        self.pause_event.clear()
        self.wake.set()

    def stop(self):
        with self.ledger._lock:
            self.ledger.data["stopped"] = True
            self.ledger.data["status"] = "stopped"
            self.ledger.save()
        self.stop_event.set()
        self.wake.set()

    def add_note(self, text):
        with self.ledger._lock:
            self.ledger.data["decisions"].append({"at": self.clock(), "text": "Denetmen notu: " + str(text)[:2000]})
            self.ledger.save()
        self.ledger.event("Denetmen notu eklendi.")

    def halt(self):
        """SpeS is closing: leave the job resumable (not Stop). Its turn is cancelled by close()."""
        self._halt = True
        self.stop_event.set()
        self.wake.set()

    def _wait(self, seconds):
        # Clear after waking, never before: a resume() that lands between the loop's check
        # and this wait must not be lost (it would sleep an hour).
        self.wake.wait(max(0.0, seconds))
        self.wake.clear()

    def _set(self, **fields):
        with self.ledger._lock:
            if self.ledger.data.get("stopped") and fields.get("status") not in (None, "stopped"):
                fields.pop("status", None)
            self.ledger.data.update(fields)
            self.ledger.save()

    # -- writer choice ---------------------------------------------------------------
    def _limited_until(self, agent, snapshot, now):
        marked = float(self.ledger.data["limited"].get(agent) or 0)
        if marked > now:
            return marked
        entry = (snapshot or {}).get(agent) or {}
        worst = max([p for p in (entry.get("five_hour"), entry.get("week")) if isinstance(p, (int, float))],
                    default=None)
        if entry.get("state") == "full" or (worst is not None and worst >= LIMIT_PERCENT):
            reset = _reset_time(entry.get("resets_at"))
            return reset if reset and reset > now else now + LIMIT_FALLBACK_SECONDS
        return 0

    def pick_writer(self):
        """(agent, None) or (None, wake_at) when all three are at their limit."""
        now = self.clock()
        try:
            snapshot = self.limits() or {}
        except Exception:
            snapshot = {}
        waits = []
        for agent in WRITER_ORDER:
            until = self._limited_until(agent, snapshot, now)
            if not until:
                return agent, None
            waits.append(until)
        return None, min(waits)

    def mark_limited(self, agent):
        now = self.clock()
        try:
            entry = (self.limits() or {}).get(agent) or {}
        except Exception:
            entry = {}
        reset = _reset_time(entry.get("resets_at"))
        until = reset if reset and reset > now else now + LIMIT_FALLBACK_SECONDS
        with self.ledger._lock:
            self.ledger.data["limited"][agent] = until
            self.ledger.save()
        return until

    # -- the loop ----------------------------------------------------------------------
    def run(self):
        with self.awake():
            try:
                self._loop()
            except Exception as exc:  # the ledger records why; SpeS keeps running
                self._set(status="failed")
                self.ledger.event(f"İş beklenmedik bir hatayla durdu: {exc}")
                self.notify(f"Uzun iş durdu: {exc}", urgent=True)

    def _loop(self):
        ledger = self.ledger
        if not ledger.data.get("baseline_checkpoint"):
            # The user's files are saved once, in full, before any agent writes (live 15 Nov:
            # Yol Hakkı is 654 MB, so a full copy per milestone would fill the disk).
            saved = self.baseline() or {}
            if saved.get("status") == "error":
                raise JobError("Başlangıç yedeği alınamadı: " + str(saved.get("warning") or ""))
            with ledger._lock:
                ledger.data["baseline_checkpoint"] = saved.get("ref") or saved.get("archive") or "?"
                ledger.save()
            ledger.event("Başlangıç yedeği alındı" + (f" ({saved.get('bytes', 0) // 1_000_000} MB)." if saved.get("bytes") else "."))
        prepare_branch(ledger)
        if "initial_dirty" not in ledger.data:
            # The user's own uncommitted files as they were before the first writer: never
            # committed by the job unless an agent changes them.
            with ledger._lock:
                ledger.data["initial_dirty"] = self.dirty()
                ledger.save()
        while True:
            if self._halt:
                return  # status stays as it was: the next start may resume it
            if self.stop_event.is_set() or ledger.data.get("stopped"):
                self._set(status="stopped")
                ledger.event("İş durduruldu.")
                return
            if self.pause_event.is_set():
                if ledger.data["status"] != "paused":
                    self._set(status="paused")
                    ledger.event("İş duraklatıldı.")
                self._wait(3600)
                continue
            if self.clock() >= ledger.data["deadline"]:
                self._set(status="expired")
                ledger.event("İş süresi doldu.")
                self.notify("Uzun işin süresi doldu; yapılanlar defterde.", urgent=False)
                return
            milestone = ledger.current()
            if milestone is None:
                waiting = [m for m in ledger.data["milestones"] if m["status"] == "needs_user"]
                self._set(status="needs_user" if waiting else "done")
                text = (f"Uzun iş bitti; {len(waiting)} kilometre taşı senin kararını bekliyor."
                        if waiting else "Uzun iş bitti: bütün kilometre taşları tamam.")
                ledger.event(text)
                self.notify(text, urgent=True)
                return
            writer, wake_at = self.pick_writer()
            if writer is None:
                self._set(status="waiting_limit")
                at = time.strftime("%H:%M", time.localtime(wake_at))
                ledger.event(f"Üç ajanın da limiti dolu; {at}'te devam edilecek.")
                self.notify(f"Uzun iş limit nedeniyle bekliyor; {at}'te devam edecek.")
                self._wait(max(30.0, wake_at - self.clock()))
                continue
            self._run_one(milestone, writer)

    def _run_one(self, milestone, writer):
        ledger = self.ledger
        previous = ledger.data.get("writer")
        if previous and previous != writer:
            text = f"Yazıcı {PERSONA.get(previous, previous)} → {PERSONA.get(writer, writer)}"
            ledger.data["decisions"].append({"at": self.clock(), "text": text + " (limit)"})
            ledger.event(text)
            self.notify(text)
        checkpoint = self.checkpoint() or {}
        if checkpoint.get("status") == "error":
            raise JobError("Yedek alınamadı: " + str(checkpoint.get("warning") or ""))
        with ledger._lock:
            milestone.update(status="running", writer=writer, attempts=milestone["attempts"] + 1,
                             checkpoint=checkpoint.get("ref"))
            ledger.data.update(status="running", writer=writer)
            ledger.save()
        ledger.event(f"{milestone['id']} başladı ({PERSONA.get(writer, writer)} yazıyor, deneme {milestone['attempts']}).")
        before = self.snapshot()
        result = self.run_milestone(ledger, milestone, writer, self.stop_event) or {}
        if self._halt:
            with ledger._lock:  # a normal close is not a crash
                milestone.update(status="pending", attempts=max(0, milestone["attempts"] - 1))
                ledger.save()
            return
        if self.stop_event.is_set():
            with ledger._lock:  # live 15 Nov: a stopped job showed its milestone as still running
                milestone["status"] = "pending"
                ledger.save()
            return
        if result.get("limit"):
            until = self.mark_limited(result["limit"])
            with ledger._lock:
                milestone.update(status="pending", attempts=max(0, milestone["attempts"] - 1))
                ledger.save()
            ledger.event(f"{PERSONA.get(result['limit'], result['limit'])} limitine takıldı; "
                         f"{time.strftime('%H:%M', time.localtime(until))}'e kadar başka yazıcı.")
            return
        built = result.get("status") in {"completed", "partial"}  # partial: a reviewer failed, not the writer
        check = self.verify(self.stop_event) if built else \
            {"ok": False, "summary": result.get("summary") or "Tur tamamlanmadı."}
        if self.stop_event.is_set():
            return
        entry = {"at": self.clock(), "writer": writer, "turn": result.get("status"),
                 "check": bool(check.get("ok")), "note": str(check.get("summary") or "")[-300:]}
        if built and check.get("ok"):
            files = list(self.changed(before, self.snapshot()))
            # Live 15 Nov: scripts written in an earlier failed attempt of the same milestone
            # were left out of its commit. Anything the agents changed since the job began counts.
            initial = ledger.data.get("initial_dirty") or {}
            root = Path(ledger.data["project_path"])
            files += [str(root / name) for name, state in self.dirty().items() if initial.get(name) != state]
            sha = self.commit(files, f"SpeS iş {ledger.data['id']}: {milestone['title']}")
            with ledger._lock:
                milestone.update(status="done", commit=sha, last_failure="")
                milestone["history"].append(entry)
                ledger.save()
            ledger.event(f"{milestone['id']} tamam" + (f" (commit {sha[:8]})." if sha else "."))
            self.notify(f"Kilometre taşı tamam: {milestone['title']}")
            return
        failure = str(check.get("summary") or result.get("summary") or "")[-1500:]
        with ledger._lock:
            milestone["history"].append(entry)
            milestone["last_failure"] = failure
            milestone["status"] = "needs_user" if milestone["attempts"] >= MAX_ATTEMPTS else "pending"
            ledger.save()
        if milestone["status"] == "needs_user":
            ledger.event(f"{milestone['id']} {MAX_ATTEMPTS} denemede geçmedi; senin kararın gerekiyor.")
            self.notify(f"'{milestone['title']}' {MAX_ATTEMPTS} denemede geçmedi; senin kararın gerekiyor. "
                        "Ekip sıradaki taşa geçti.", urgent=True)
        else:
            ledger.event(f"{milestone['id']} geçmedi; yeniden denenecek.")

    # -- startup -----------------------------------------------------------------------
    def recover_after_crash(self):
        """A job that was running when SpeS stopped: count the crash on its milestone."""
        ledger = self.ledger
        milestone = next((m for m in ledger.data["milestones"] if m["status"] == "running"), None)
        if milestone is None:
            return "resume"
        with ledger._lock:
            milestone["crashes"] += 1
            milestone["attempts"] = max(0, milestone["attempts"] - 1)
            if milestone["crashes"] >= MAX_CRASHES:
                milestone["status"] = "pending"
                ledger.data["status"] = "paused"
                ledger.save()
                ledger.event(f"{milestone['id']} üst üste {MAX_CRASHES} kez yarıda kaldı; iş duraklatıldı.")
                return "pause"
            milestone["status"] = "pending"
            ledger.save()
        ledger.event(f"SpeS yeniden başladı; {milestone['id']} kaldığı dosyalardan yeniden deneniyor.")
        return "resume"


def milestone_prompt(ledger: JobLedger, milestone: dict, writer: str) -> str:
    """The writer's instruction for one milestone: ledger first, chat history never."""
    d = ledger.data
    parts = [
        "UZUN İŞ — KİLOMETRE TAŞI GÖREVİ. Projede dosya yazarak bu taşı tamamla.",
        ledger.summary(),
        f"ŞU ANKİ TAŞ: {milestone['id']} — {milestone['title']}",
        f"KABUL ÖLÇÜTÜ: {milestone['acceptance']}",
        "Yalnız bu taşın işini yap; sonraki taşlara geçme. Bitince ne yaptığını ve ölçütü nasıl "
        "karşıladığını kısaca yaz. SpeS işi bitince projenin kendi kontrolünü çalıştıracak.",
    ]
    if milestone.get("last_failure"):
        parts.append("ÖNCEKİ DENEME GEÇMEDİ. Kontrol çıktısının sonu:\n" + milestone["last_failure"])
    if milestone.get("crashes"):
        parts.append("Önceki deneme SpeS yeniden başladığı için yarıda kaldı; projede yarım değişiklikler "
                     "olabilir. Önce mevcut durumu incele.")
    if d.get("writer") and writer != "claude":
        parts.append(f"Bu taşta yazıcı sensin ({PERSONA.get(writer, writer)}); Fatum limitte.")
    return "\n\n".join(parts)


COMMAND = re.compile(r"^\s*/uzun[-_ ]?i[şs]\b", re.I)
FIELDS = {"hedef": "goal", "süre": "hours", "sure": "hours", "devam": "auto_resume", "kontrol": "verify",
          "dal": "git_branch"}


def parse_command(text: str):
    """'/uzun-iş' typed by the user in a Workspace chat -> a job spec (None if not a command).

    /uzun-iş
    Hedef: ...
    Süre: 2 saat
    Devam: evet            (çökünce kendiliğinden devam)
    Kontrol: python -m unittest      (argümanlar boşlukla; kabuk yok)
    Dal: spes/deneme-1
    1. Başlık | kabul ölçütü
    """
    if not COMMAND.match(str(text or "")):
        return None
    import shlex
    spec = {"milestones": []}
    rest = COMMAND.sub("", text, count=1).strip()
    if rest.lower() in {"durum", "liste", "list", ""}:
        return {"list": True}
    note = re.match(r"^not\s*:\s*(.+)$", rest, re.S | re.I)
    if note:
        return {"note": note.group(1).strip()[:2000]}
    for raw in rest.splitlines():
        line = raw.strip()
        if not line:
            continue
        step = re.match(r"^\d+[.)]\s*(.+?)\s*\|\s*(.+)$", line)
        if step:
            spec["milestones"].append({"title": step.group(1), "acceptance": step.group(2)})
            continue
        key, sep, value = line.partition(":")
        field = FIELDS.get(key.strip().lower())
        if not sep or not field:
            raise JobError(f"Anlaşılmayan satır: {line[:80]}")
        value = value.strip()
        if field == "hours":
            number = re.search(r"\d+(?:[.,]\d+)?", value)
            if not number:
                raise JobError("Süre sayı olmalı (ör. 2 saat).")
            amount = float(number.group(0).replace(",", "."))
            spec["hours"] = amount / 60 if re.search(r"dak", value, re.I) else amount
        elif field == "auto_resume":
            spec["auto_resume"] = value.lower() in {"evet", "e", "açık", "acik", "yes", "true"}
        elif field == "verify":
            # Windows paths keep their backslashes; surrounding quotes are dropped.
            spec["verify"] = [part[1:-1] if len(part) > 1 and part[0] == part[-1] and part[0] in "\"'" else part
                              for part in shlex.split(value, posix=False)] if value else None
        else:
            spec[field] = value
    return spec
