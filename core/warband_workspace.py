"""Task-scoped ASTER development and real-game tools, orchestrated by UM.

No arbitrary command tool. Source writes are trusted project development, not
an OS sandbox. Existing game/save/launcher contracts stay authoritative.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager

PROJECT = Path(r"C:\WarbandIsland")
UM = Path(r"C:\WarbandMC\universal-modder")
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\MountBlade Warband")
SAVES = Path.home() / "Documents/Mount&Blade Warband Savegames/AI_Island_Test"
CONFIG = Path.home() / "Documents/Mount&Blade Warband/rgl_config.txt"
CAPABILITIES = {"inspect", "develop", "play"}
EDITABLE = {
    "battlefield_parley.py", "command_structure.py", "parley_contract.py",
    "parley_system.py", "parley_navigation.py", "parley_rendezvous.py",
    "parley_timing.py", "parley_return.py", "parley_native_escort.py",
    "parley_player_escort.py", "parley_trail.py", "parley_follow_cohesion.py",
    "parley_guide.py", "parley_guard_observer.py", "gate_b_observation.py",
    "source/module_mission_templates.py", "source/module_scripts.py",
    "source/module_dialogs.py", "source/module_game_menus.py",
}
KEYS = {"escape": "0x1B", "enter": "0x0D", "space": "0x20", "tab": "0x09",
        "w": "0x57", "a": "0x41", "s": "0x53", "d": "0x44", "f": "0x46",
        "e": "0x45", "up": "0x26", "down": "0x28", "left": "0x25", "right": "0x27",
        **{"f"+str(n): hex(0x6F+n) for n in range(1, 12)}}

class GameLoading(RuntimeError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or len(relative) > 240:
        raise ValueError("Bounded project-relative path required")
    part = Path(relative)
    if part.is_absolute() or part.drive or any(p in {"..", ".git", ".env"} for p in part.parts):
        raise PermissionError("Path is outside the authored project scope")
    root = Path(root).resolve(strict=True)
    path = root / part
    for item in (path, *path.parents):
        if item == root: break
        if item.is_symlink() or (item.exists() and getattr(item.stat(), "st_file_attributes", 0) & 0x400):
            raise PermissionError("Linked/reparse project files are refused")
    resolved = path.resolve(strict=True)
    if root not in resolved.parents or not resolved.is_file(): raise PermissionError("Not a project file")
    return resolved


class SaveGuard:
    """Allow Native reads; deny write, truncate, rename and delete on originals."""
    def __init__(self, folder):
        self.folder, self.handles, self.before, self.metadata = Path(folder), [], {}, {}

    def acquire(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        files = sorted(self.folder.glob("sg*.sav"))
        if not files: raise RuntimeError("No original saves found; inspect the profile first")
        try:
            for path in files:
                if path.is_symlink(): raise PermissionError("Linked save refused")
                handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
                if handle in (None, ctypes.c_void_p(-1).value):
                    raise OSError(ctypes.get_last_error(), "Cannot lock original save: " + path.name)
                self.handles.append(handle)
                self.before[path.name] = digest(path)
                stat=path.stat();self.metadata[path.name]=(stat.st_size,stat.st_mtime_ns)
            return dict(self.before)
        except BaseException:
            self.close(); raise

    def verify(self):
        current = {p.name: digest(p) for p in sorted(self.folder.glob("sg*.sav"))}
        return {"unchanged": current == self.before, "before": self.before, "after": current}

    def intact(self):
        # Live write/delete-denying handles provide protection. Avoid rehashing
        # all nine multi-MB saves on every keypress on this low-memory machine.
        current={p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in self.folder.glob("sg*.sav")}
        return bool(self.handles) and current==self.metadata

    def close(self):
        for handle in self.handles: self.kernel.CloseHandle(handle)
        self.handles.clear()


class WarbandWorkspace:
    def __init__(self, evidence, *, root=PROJECT, um=UM, game=GAME, saves=SAVES, config=CONFIG):
        self.root, self.um, self.game, self.saves, self.config = map(Path, (root, um, game, saves, config))
        self.evidence = Path(evidence).resolve() / "warband"
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.capabilities = set()
        self.lock = threading.RLock()
        self.input_lock = threading.RLock()
        self.cancel = threading.Event()
        self.job = None
        self.prepared = None
        self.owned = None
        self.launcher = None
        self.launch_receipt = None
        self.guard = None
        self.input_lease = None
        self.snapshot = None
        self.focused = False
        self.focus_attempted = False
        self.audit = []
        self.rejections=[]
        self._fingerprint = None
        self.transition_deadline = 0
        self.save_watch_started=False

    def grant(self, capabilities):
        requested = set(capabilities)
        if not requested or not requested <= CAPABILITIES: raise ValueError("Unknown Warband capability")
        if "play" in requested and "play" not in self.capabilities:
            self.focus_attempted=False;self.focused=False;self.snapshot=None
        self.capabilities |= requested | {"inspect"}

    def require(self, capability):
        if self.cancel.is_set() or capability not in self.capabilities:
            raise PermissionError("Request Warband " + capability + " access in the chat first")

    def context(self):
        module = self.game / "Modules/AI_Island_Test"
        scripts = module / "scripts.txt"
        fingerprint=None
        if scripts.is_file():
            state=(scripts.stat().st_size,scripts.stat().st_mtime_ns)
            if not self._fingerprint or self._fingerprint[0]!=state: self._fingerprint=(state,digest(scripts))
            fingerprint=self._fingerprint[1]
        lease_status=None
        runtime_alive=False
        if self.owned:
            import psutil
            try:
                proc=psutil.Process(self.owned["pid"])
                runtime_alive=proc.create_time()==self.owned["started"] and proc.is_running()
            except psutil.NoSuchProcess: pass
        receipt=self.owned["lease"] if self.owned else self.launch_receipt
        if receipt:
            try:
                lease=json.loads(Path(receipt).read_text(encoding="utf-8-sig"))
                actual=[s for s in self.config.read_text(encoding="utf-8-sig").splitlines() if re.match(r"^battle_size\s*=",s)]
                lease_status={"reported_restored":lease.get("restored",False),"actual":actual,
                              "verified_restored":bool(lease.get("restored") and actual==[lease.get("originalLine")])}
            except (OSError,ValueError): lease_status={"verified_restored":False,"error":"Lease readback unavailable"}
        return {"workflow": "Universal Modder / AI_Island_Test", "root": str(self.root),
                "capabilities": sorted(self.capabilities), "prepared": bool(self.prepared),
                "job": dict(self.job) if self.job else None, "owned_game": self.owned,
                "runtime_alive":runtime_alive,"input_active": self.focused and runtime_alive and bool(self.input_lease),
                "scripts_sha256": fingerprint,"lease_status":lease_status,
                "standard_total_humans": 150, "optional_profiles": [300, 500],
                "save_writes": "DENIED; original saves locked during owned play",
                "save_guard_active":bool(self.guard and self.guard.handles),
                "evidence": str(self.evidence)}

    @contextmanager
    def _project_lock(self):
        import msvcrt
        folder=Path(os.environ.get("LOCALAPPDATA",str(Path.home())))/"Quartz"
        folder.mkdir(parents=True,exist_ok=True)
        key=hashlib.sha256(str(self.root.resolve()).casefold().encode()).hexdigest()[:12]
        stream=(folder/("warband-workspace-"+key+".lock")).open("a+b")
        try:
            stream.seek(0)
            if not stream.read(1):stream.write(b"0");stream.flush()
            stream.seek(0)
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError("Another Quartz task is preparing, building or restoring ASTER") from None
            yield
        finally:stream.close()

    def _command(self, argv, timeout=180, *, cleanup=False, kill_tree=True):
        path = self.evidence / ("command-" + uuid.uuid4().hex + ".log")
        with path.open("w", encoding="utf-8") as out:
            process = subprocess.Popen(argv, cwd=str(self.root), stdout=out, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if (not cleanup and self.cancel.wait(.1)) or time.monotonic() >= deadline:
                    if kill_tree:
                        from core.process_tree import stop_process_tree
                        stop_process_tree(process)
                    else:
                        process.terminate(); process.wait(10)
                    raise RuntimeError("Owned helper stopped/expired; inspect " + str(path))
                if cleanup:time.sleep(.1)
        text = path.read_text(encoding="utf-8", errors="replace")
        if process.returncode: raise RuntimeError("Command failed: " + text[-2200:] + "; log=" + str(path))
        return {"log": str(path), "tail": text[-6000:], "exit_code": process.returncode}

    def _um(self, *args, timeout=240, cleanup=False):
        return self._command([shutil.which("uv") or "uv", "run", "--directory", str(self.um), "um", *map(str, args)], timeout,
                             cleanup=cleanup,kill_tree=tuple(args[:2])!=("win","launch"))

    def _preflight(self):
        return self._command(["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
            str(self.root / "launch_island_profile.ps1"), "-PreflightOnly"], 40)

    def _backup(self, folder, name):
        result = self._um("backup", "create", folder, "--name", name)
        paths = re.findall(r"([^\r\n]+\.zip)\s+\(", result["tail"])
        if not paths: raise RuntimeError("UM returned no backup receipt")
        archive = Path(paths[-1].strip())
        with zipfile.ZipFile(archive) as z:
            if z.testzip() or "_um_manifest.json" not in z.namelist(): raise RuntimeError("Invalid UM checkpoint")
        diff=self._um("backup","diff",name,folder,"--snapshot",archive)
        differences=json.loads(diff["tail"])
        if any(differences.get(k) for k in ("changed","removed","added")): raise RuntimeError("UM checkpoint changed while preparing")
        return {"archive": str(archive), "sha256": digest(archive), "log": result["log"],"diff":differences}

    def prepare(self):
        self.require("inspect")
        self._preflight()
        stage = self.evidence / ("authored-source-" + uuid.uuid4().hex[:10])
        stage.mkdir()
        copied = {}
        candidates = list(self.root.glob("*.py")) + list(self.root.glob("*.md")) + list(self.root.glob("*.ps1")) + list(self.root.glob("*.cmd"))
        candidates += list((self.root / "source").glob("*.py")) + list((self.root / "source").glob("*.bat")) + list((self.root / "source").glob("variables.txt"))
        for path in candidates:
            source = safe_path(self.root, str(path.relative_to(self.root)))
            target = stage / source.relative_to(self.root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target); copied[source.relative_to(self.root).as_posix()] = digest(source)
        stamp = uuid.uuid4().hex[:10]
        snapshots = {"source": self._backup(stage, "quartz-aster-source-" + stamp),
                     "saves": self._backup(self.saves, "quartz-aster-saves-" + stamp),
                     "module": self._backup(self.game / "Modules/AI_Island_Test", "quartz-aster-module-" + stamp)}
        self.prepared = {"at": time.time(), "snapshots": snapshots, "source_hashes": copied,
                         "save_hashes": {p.name:digest(p) for p in sorted(self.saves.glob("sg*.sav"))}}
        (self.evidence / "preparation.json").write_text(json.dumps(self.prepared, indent=2), encoding="utf-8")
        return {"level": "CHECKPOINT VERIFIED", "snapshots": snapshots, "save_count": len(self.prepared["save_hashes"])}

    def source(self, mode="list", path="", start=1, count=120, query="", old="", new="", sha256=""):
        if mode=="replace":
            with self._project_lock():return self._source(mode,path,start,count,query,old,new,sha256)
        return self._source(mode,path,start,count,query,old,new,sha256)

    def _source(self, mode, path, start, count, query, old, new, sha256):
        self.require("inspect")
        if mode == "list":
            return {"editable": sorted(EDITABLE), "documents": sorted(p.name for p in self.root.glob("*.md"))}
        if mode == "changes":
            import difflib
            changes=[]
            for entry in self.audit:
                if entry.get("level")!="SOURCE CHANGED; NOT BUILT/LIVE": continue
                original=Path(entry["original"])
                if not original.is_relative_to(self.evidence) or digest(original)!=entry["before"]: raise PermissionError("Patch evidence changed")
                current=safe_path(self.root,entry["path"])
                diff="\n".join(difflib.unified_diff(original.read_text(encoding="utf-8-sig").splitlines(),
                    current.read_text(encoding="utf-8-sig").splitlines(),fromfile=entry["path"]+" (checkpoint)",tofile=entry["path"]+" (current)",lineterm=""))
                changes.append({**entry,"current_sha256":digest(current),"untrusted_diff":diff[:20000]})
            return {"changes":changes[-5:],"scope":"actual task patch receipts and current files; no inferred review acceptance"}
        source = safe_path(self.root, path)
        if source.suffix.lower() not in {".py", ".md", ".txt", ".log", ".json", ".ps1", ".cmd", ".bat"} or source.stat().st_size > 8*1024*1024:
            raise PermissionError("Only bounded source/document text is readable")
        raw = source.read_bytes()
        text = raw.decode("utf-8-sig").replace("\r\n","\n")
        identity = hashlib.sha256(raw).hexdigest()
        if mode == "replace":
            self.require("develop")
            if self.job and self.job["status"]=="running": raise RuntimeError("Wait for the active UM operation before editing source")
            if path.replace("\\", "/") not in EDITABLE: raise PermissionError("File is outside Gate B authored edit scope")
            if not self.prepared: raise PermissionError("Run the UM preparation checkpoint first")
            self._preflight()
            if identity != sha256 or not old or text.count(old) != 1 or len(old) + len(new) > 16000:
                raise ValueError("Fresh SHA256 and a single exact replacement required")
            # A new UM source checkpoint precedes every write, even a later patch.
            before = self._backup(source.parent if source.parent.name == "source" else self._source_stage(), "quartz-aster-patch-" + uuid.uuid4().hex[:10])
            patched = text.replace(old, new, 1)
            candidate = self.evidence / ("candidate-"+uuid.uuid4().hex+".py")
            candidate.write_bytes(patched.encode("utf-8-sig") if raw.startswith(b"\xef\xbb\xbf") else patched.encode("utf-8"))
            self._command([r"C:\Python27\python.exe", "-B", "-c",
                           "import sys; compile(open(sys.argv[1],'rb').read(),sys.argv[1],'exec')", str(candidate)],30)
            backup = self.evidence / ("before-" + uuid.uuid4().hex + ".txt")
            backup.write_bytes(raw)
            output=patched.replace("\n","\r\n") if b"\r\n" in raw else patched
            temporary=source.with_name(source.name+".quartz-"+uuid.uuid4().hex+".tmp")
            with temporary.open("xb") as out:
                out.write(output.encode("utf-8-sig") if raw.startswith(b"\xef\xbb\xbf") else output.encode("utf-8"))
                out.flush(); os.fsync(out.fileno())
            if digest(source)!=identity: raise PermissionError("Source changed during checkpoint; patch not applied")
            self.require("develop")
            os.replace(temporary,source)
            result = {"level":"SOURCE CHANGED; NOT BUILT/LIVE", "path":path, "before":identity,
                      "after":digest(source), "checkpoint":before, "original":str(backup)}
            self.audit.append(result)
            return result
        lines = text.splitlines()
        if mode == "search":
            if not query or len(query) > 200: raise ValueError("Literal query required")
            selected = [(i+1,line) for i,line in enumerate(lines) if query.casefold() in line.casefold()][:80]
        elif mode == "read":
            if not 1 <= int(start) or not 1 <= int(count) <= 200: raise ValueError("Bounded line range required")
            selected = list(enumerate(lines, 1))[int(start)-1:int(start)-1+int(count)]
        else: raise ValueError("Unknown source operation")
        return {"path":path, "sha256":identity, "total_lines":len(lines), "untrusted_source_lines":selected}

    def _source_stage(self):
        stage = self.evidence / ("patch-source-" + uuid.uuid4().hex[:10]); stage.mkdir()
        for name in EDITABLE:
            p = self.root / name
            if p.is_file():
                dest = stage / name; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p,dest)
        return stage

    def run(self, operation):
        capability = "play" if operation in {"launch", "close"} else "develop" if operation == "build" else "inspect"
        self.require(capability)
        if operation not in {"prepare", "preflight", "contracts", "preservation", "build", "launch", "close"}: raise ValueError("Unknown operation")
        with self.lock:
            if self.job and self.job["status"] == "running": raise RuntimeError("Wait for the current UM operation")
            self.job = {"id":uuid.uuid4().hex, "operation":operation, "status":"running", "started_at":time.time()}
            identity = self.job["id"]
        def worker():
            try:
                with self._project_lock():result = self._run(operation)
                status = "completed"
            except BaseException as exc:
                result, status = {"error":str(exc)}, "failed"
            with self.lock:
                self.job.update(status=status, result=result, finished_at=time.time())
                (self.evidence / ("job-"+identity+".json")).write_text(json.dumps(self.job,indent=2),encoding="utf-8")
        threading.Thread(target=worker,daemon=True,name="quartz-warband-"+operation).start()
        return dict(self.job)

    def _run(self, operation):
        if operation == "prepare": return self.prepare()
        if operation == "preflight": return self._preflight()
        if operation == "launch": return self.launch()
        if operation == "close": return self.close_game()
        self._preflight()
        if operation == "contracts":
            results = [self._command([interpreter, "-B", str(self.root / f)],180)
                       for interpreter,f in ((r"C:\Python27\python.exe","test_contract_sequences.py"),
                                             (r"C:\Python27\python.exe","test_parley_guide.py"),
                                             (str(self.um/".venv/Scripts/python.exe"),"test_capture_native_guard.py"))]
            return {"level":"SOURCE/STATIC", "results":results}
        if operation == "preservation":
            results = [self._command([str(self.um / ".venv/Scripts/python.exe"), "-B", str(self.root / f)],180)
                       for f in ("verify_frozen_world.py", "verify_equipment_checkpoint.py", "audit_gate_b_714_prefix.py")]
            return {"level":"SOURCE/STATIC", "results":results}
        if operation == "build":
            if not self.prepared: raise PermissionError("UM preparation checkpoint required before build")
            before = self._backup(self.game / "Modules/AI_Island_Test", "quartz-aster-prebuild-"+uuid.uuid4().hex[:10])
            try:
                result = self._command(["powershell.exe","-NoProfile","-NonInteractive","-File",str(self.root/"build.ps1"),"-CodeOnly"],600)
                checks=self._run("preservation")
            except BaseException as exc:
                # Restore the exact pre-build module through UM; keep authored
                # source and all evidence for diagnosis. No clean/delete mode.
                archive=Path(before["archive"])
                try:
                    rollback=self._um("backup","restore",archive.parent.name,"--to",self.game/"Modules/AI_Island_Test","--snapshot",archive,"--yes",cleanup=True)
                except BaseException as rollback_error:
                    raise RuntimeError("Build failed AND module rollback failed: "+str(exc)+"; "+str(rollback_error)+"; checkpoint="+str(archive)) from None
                raise RuntimeError("Build failed; pre-build module restored by UM. Source retained. "+str(exc)+"; rollback="+rollback["log"]) from None
            return {"level":"BUILT; NOT LIVE VERIFIED", "module_checkpoint":before, "preservation":checks, **result}

    def launch(self):
        self.require("play")
        if not self.prepared: raise PermissionError("Prepare UM multi-root checkpoints before launch")
        self._preflight()
        import psutil
        steam=self.game.parents[2]/"steam.exe"
        if not any((p.info["name"] or "").lower()=="steam.exe" for p in psutil.process_iter(["name"])):
            if not steam.is_file(): raise RuntimeError("Legitimate Steam prerequisite not found")
            self._um("win","launch",steam,timeout=30)
            deadline=time.monotonic()+30
            while time.monotonic()<deadline and not self.cancel.wait(.3):
                if any((p.info["name"] or "").lower()=="steam.exe" for p in psutil.process_iter(["name"])): break
            else: raise RuntimeError("Steam did not start; no game or config lease created")
        # Steam's first process can exist while its updater/bootstrap is still
        # replacing it. Wait for a stable process and a visible Steam surface;
        # this establishes readiness only, never authenticates on the user's behalf.
        from core.desktop_native import NativeDesktopBackend
        deadline=time.monotonic()+60
        while time.monotonic()<deadline and not self.cancel.wait(.5):
            processes={p.pid:p.info for p in psutil.process_iter(["name","create_time"])
                       if (p.info["name"] or "").lower() in {"steam.exe","steamwebhelper.exe"}}
            stable=any((v["name"] or "").lower()=="steam.exe" and time.time()-v["create_time"]>=8 for v in processes.values())
            visible=any(w["process_id"] in processes for w in NativeDesktopBackend().controller.windows()["windows"])
            if stable and visible: break
        else: raise RuntimeError("Steam startup not ready; inspect Steam yourself if authentication is required. No game/config lease created.")
        self.guard = SaveGuard(self.saves); hashes = self.guard.acquire()
        if hashes != self.prepared["save_hashes"]:
            self.guard.close(); self.guard=None; raise PermissionError("Saves changed since preparation")
        self.old_leases = set((self.root/"evidence").glob("profile-lease-*.json"))
        self.launch_time = time.time()
        self.launch_log = self.evidence / ("launcher-"+uuid.uuid4().hex+".log")
        with self.launch_log.open("w",encoding="utf-8") as out:
            self.launcher = subprocess.Popen(["powershell.exe","-NoProfile","-NonInteractive","-File",
                str(self.root/"launch_island_profile.ps1"),"-Profile","Standard","-UserApprovedSharedConfig"],
                cwd=str(self.root),stdout=out,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        deadline=time.monotonic()+90
        while time.monotonic()<deadline and not self.cancel.wait(.3):
            for path in set((self.root/"evidence").glob("profile-lease-*.json"))-self.old_leases:
                try:
                    lease=json.loads(path.read_text(encoding="utf-8-sig"))
                    self.launch_receipt=str(path)
                    if lease.get("restored"):
                        raise RuntimeError("UM launcher exited before a stable game window: "+str(lease.get("error") or "game exited")+"; lease="+str(path))
                    if lease.get("pid") and not lease.get("restored"):
                        from core.desktop_native import NativeDesktopBackend
                        import psutil
                        process=psutil.Process(int(lease["pid"]))
                        if process.create_time()<self.launch_time-2 or Path(process.exe()).resolve()!= (self.game/"mb_warband.exe").resolve(): continue
                        self.owned={"pid":process.pid,"started":process.create_time(),"exe":process.exe(),"lease":str(path)}
                        return {"level":"LAUNCHED; NOT GAMEPLAY VERIFIED","owned_game":self.owned,"launcher_log":str(self.launch_log)}
                except (OSError,ValueError,ProcessLookupError): continue
            if self.launcher.poll() is not None: break
        raise RuntimeError("Launch not confirmed; preserve watcher and inspect "+str(self.launch_log))

    def _target(self):
        self.require("play")
        if not self.owned: raise PermissionError("Only this task's UM-launched game can receive input")
        import psutil
        from core.desktop_native import NativeDesktopBackend
        try: p=psutil.Process(self.owned["pid"])
        except psutil.NoSuchProcess: raise RuntimeError("Owned game already exited; read warband_status lease_status") from None
        if p.create_time()!=self.owned["started"] or p.exe()!=self.owned["exe"]: raise PermissionError("Game identity changed")
        processes=[q.pid for q in psutil.process_iter(["name"]) if (q.info["name"] or "").lower()=="mb_warband.exe"]
        if processes!=[p.pid]: raise PermissionError("Another Warband process exists; exact input isolation refused")
        backend=NativeDesktopBackend()
        windows=[w for w in backend.controller.windows()["windows"] if w["process_id"]==p.pid]
        if len(windows)!=1:
            if time.monotonic()<self.transition_deadline: raise GameLoading("Expected Native launcher-to-game window transition")
            raise PermissionError("No unique owned game window")
        target=backend.identity(windows[0]["handle"])
        backend.validate_input_session()
        if not backend._input_desktop_matches(target): raise PermissionError("Game is not on the active input desktop")
        if self.focused and not backend.is_foreground(target):
            self.focused=False; self.snapshot=None; self.capabilities.discard("play")
            if self.input_lease: self.input_lease.close(); self.input_lease=None
            raise PermissionError("User takeover: game input revoked; new inline permission required")
        return backend,target

    def log(self):
        self.require("inspect")
        path=self.game/"rgl_log.txt"
        if not path.is_file(): return {"lines":[],"note":"No RGL log"}
        with path.open("rb") as f:
            head=f.read(6000).decode("utf-8",errors="replace")
            f.seek(max(0,path.stat().st_size-18000)); text=f.read(18000).decode("utf-8",errors="replace")
        lines=text.splitlines()[-120:]
        modules=re.findall(r"^\s*Module_name\s*=\s*(\S+)",head,re.M)
        return {"path":str(path),"mtime":path.stat().st_mtime,"runtime_module":modules[-1] if modules else None,
                "fresh_for_owned_game":bool(self.owned and path.stat().st_mtime>=self.owned["started"]),"untrusted_log":lines,
                "script_errors":[s for s in lines if re.search(r"SCRIPT ERROR|HERR|RGL ERROR",s,re.I)]}

    def observe(self, focus=False):
        try:backend,target=self._target()
        except GameLoading as exc:
            return {"status":"game_loading","next":"task_wait then warband_observe","remaining_seconds":max(0,int(self.transition_deadline-time.monotonic())),"note":str(exc)}
        if focus:
            if self.focus_attempted: raise PermissionError("Initial focus can only be requested once per permission")
            self.focus_attempted=True
            try:
                with self.input_lock:
                    self.require("play")
                    if self.input_lease is None:self.input_lease=backend.acquire_lease()
                    drive=self._drive(target)
                    try:
                        if drive.cmd("focus",retry=False)!="ok": raise PermissionError("UM could not focus the exact owned game")
                    finally:drive.close()
            except BaseException:
                self.capabilities.discard("play")
                if self.input_lease:self.input_lease.close();self.input_lease=None
                raise
            if not backend.is_foreground(target):
                self.capabilities.discard("play")
                if self.input_lease: self.input_lease.close(); self.input_lease=None
                raise PermissionError("Game focus failed; request new inline permission")
            self.focused=True
        if not self.focused or self.input_lease is None: raise PermissionError("Acquire the single operator lease with initial focus first")
        if not backend.is_foreground(target): raise PermissionError("Focus the owned game once before observation")
        readback=self.log()
        launcher=({"can_start":False,"runtime_module":readback["runtime_module"]}
                  if readback.get("runtime_module")=="AI_Island_Test" and readback.get("fresh_for_owned_game")
                  else self._launcher_state(backend,target))
        identifier=uuid.uuid4().hex
        image=self.evidence/("game-"+identifier+".png")
        self._um("win","shot","--hwnd",str(target["handle"]),str(image),timeout=25)
        from PIL import Image
        with Image.open(image) as png:
            client, bounds = self._geometry(target["handle"], target["rect"])
            if png.size != client[2:]:
                matching = next((b for b in bounds if (b[2]-b[0],b[3]-b[1])==png.size),None)
                if matching is None: raise PermissionError("UM capture/window geometry could not be mapped")
                x,y=client[0]-matching[0],client[1]-matching[1]
                if x<0 or y<0 or x+client[2]>png.width or y+client[3]>png.height: raise PermissionError("Client crop outside captured window")
                cropped=png.crop((x,y,x+client[2],y+client[3]))
            else: cropped=png.copy()
        cropped.save(image); width,height=cropped.size
        record={"id":identifier,"at":time.time(),"target":target,"width":width,"height":height,
                "image":str(image),"image_sha256":digest(image),"log":self.log(),"actions":len(self.audit)}
        record["launcher"]=launcher
        (self.evidence/("game-"+identifier+".json")).write_text(json.dumps(record,indent=2),encoding="utf-8")
        self.require("play")
        if not self.focused or self.input_lease is None:raise PermissionError("Input scope was paused during capture")
        self.snapshot=record
        self.transition_deadline=0
        return {"snapshot_id":identifier,"target":target,"observation":{"width":width,"height":height,
            "image_base64":base64.b64encode(image.read_bytes()).decode(),"coordinate_space":"client pixels; UM Drive coordinates",
            "ui":{"elements":[]},"launcher":launcher,"telemetry":record["log"]},"evidence":str(image),"level":"LIVE OBSERVED; NOT ACCEPTED"}

    @staticmethod
    def _launcher_state(backend,target):
        try:
            with backend.controller._desktop() as desktop:
                win=backend.controller._window(desktop,target["handle"])
                combos=win.descendants(control_type="ComboBox")
                selected=[c.selected_text().strip() for c in combos]
                play=[c for c in win.descendants() if c.window_text().strip() in
                      {"Mount&Blade Oyna","Play Mount&Blade","Play Mount & Blade"} and c.is_visible() and c.is_enabled()]
                rect=play[0].rectangle() if len(play)==1 else None
                combo=combos[0].rectangle() if len(combos)==1 else None
                return {"selected_modules":selected,"play_rect": [rect.left,rect.top,rect.right,rect.bottom] if rect else None,
                        "module_rect":[combo.left,combo.top,combo.right,combo.bottom] if combo else None,
                        "can_start":selected==["AI_Island_Test"],
                        "note":"If Play has no UIA rectangle, choose its visual center from this actual screenshot"}
        except Exception:
            return {"can_start":False,"note":"Native launcher controls unavailable; no automatic module selection"}

    def start_game(self,snapshot_id,x=None,y=None):
        self.require("play")
        row=self.snapshot; self.snapshot=None
        if not row or row["id"]!=snapshot_id or time.time()-row["at"]>15: raise PermissionError("Fresh actual launcher screenshot required")
        backend,target=self._target()
        if target!=row["target"]: raise PermissionError("Launcher identity/geometry changed")
        launcher=self._launcher_state(backend,target)
        if not launcher.get("can_start") or launcher!=row.get("launcher"):
            raise PermissionError("Only the observed Native launcher with AI_Island_Test selected can start")
        client,_=self._geometry(target["handle"],target["rect"])
        r=launcher["play_rect"]
        if x is None and y is None and r:
            x=(r[0]+r[2])//2-client[0];y=(r[1]+r[3])//2-client[1]
        if type(x) is not int or type(y) is not int: raise ValueError("Play is custom rendered; choose its center from the actual screenshot")
        if not 0<=x<row["width"] or not 0<=y<row["height"]: raise PermissionError("Play control outside the observed launcher")
        combo=launcher.get("module_rect")
        if combo and combo[0]<=x+client[0]<=combo[2] and combo[1]<=y+client[1]<=combo[3]:
            raise PermissionError("Module selection is not a start-game action")
        if not self.guard or not self.guard.intact(): raise PermissionError("Original save locks required")
        drive=self._drive(target)
        try:
            with self.input_lock:
                self.require("play")
                if not self.focused or not self.input_lease:raise PermissionError("Single operator lease required")
                if drive.cmd(f"click {x} {y}",retry=False)!="ok": raise RuntimeError("Native Play input outcome unknown; do not replay")
            self.audit.append({"at":time.time(),"snapshot_id":snapshot_id,"command":"launcher click with verified AI_Island_Test selection","x":x,"y":y,"target":target})
        finally: drive.close()
        self.transition_deadline=time.monotonic()+90
        try:return self.observe()
        except Exception as exc:return {"status":"Native Play sent once; next capture pending","next":"warband_observe","capture_error":str(exc)}

    def _drive(self,target):
        import importlib,sys
        if str(self.um) not in sys.path: sys.path.insert(0,str(self.um))
        module=importlib.import_module("um.win")
        if Path(module.__file__).resolve()!=(self.um/"um/win.py").resolve(): raise PermissionError("Unexpected Universal Modder runtime")
        drive=module.Drive("mb_warband",pid=target["pid"])
        if drive.ready!="ready window":
            drive.close(); raise PermissionError("UM exact PID has no current game window")
        self._target()  # recheck start time after the helper bound its exact PID
        return drive

    @staticmethod
    def _geometry(hwnd, window_rect):
        import ctypes
        from ctypes import wintypes
        user=ctypes.windll.user32
        rect=wintypes.RECT(); point=wintypes.POINT()
        user.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        user.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
        if not user.GetClientRect(hwnd,ctypes.byref(rect)) or not user.ClientToScreen(hwnd,ctypes.byref(point)):
            raise PermissionError("Cannot read actual game client geometry")
        bounds=[tuple(window_rect)]
        dwm=wintypes.RECT()
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd),9,ctypes.byref(dwm),ctypes.sizeof(dwm))==0:
            bounds.append((dwm.left,dwm.top,dwm.right,dwm.bottom))
        return (point.x,point.y,rect.right-rect.left,rect.bottom-rect.top),bounds

    def act(self, snapshot_id, action, x=None, y=None, key=None, seconds=.15, dx=0, dy=0):
        record=self.snapshot; self.snapshot=None
        if not record or record["id"]!=snapshot_id or time.time()-record["at"]>15:
            self.rejections.append({"at":time.time(),"reason":"missing, consumed, mismatched or stale observation", "received":snapshot_id,
                "expected":record["id"] if record else None,"age_seconds":time.time()-record["at"] if record else None})
            (self.evidence/"input-rejections.json").write_text(json.dumps(self.rejections[-30:],indent=2),encoding="utf-8")
            raise PermissionError("Fresh one-use game observation required")
        backend,target=self._target()
        if any(target[k]!=record["target"][k] for k in ("handle","pid","started","exe","rect")): raise PermissionError("Game/window geometry changed")
        raw=(self.game/"rgl_log.txt").read_text(encoding="utf-8",errors="replace")
        modules=re.findall(r"^\s*Module_name\s*=\s*(\S+)",raw,re.M)
        if not modules or modules[-1]!="AI_Island_Test" or (self.game/"rgl_log.txt").stat().st_mtime<self.owned["started"]:
            raise PermissionError("Current runtime module not confirmed; warband_start_game may start only a verified AI_Island_Test launcher")
        if not self.guard or not self.guard.intact(): raise PermissionError("Original save protection failed")
        # All actual input uses UM's existing foreground-guarded Drive, retry=False.
        drive=self._drive(target)
        try:
            if drive.cmd("scanmode on",retry=False)!="ok": raise RuntimeError("DirectInput setup failed")
            rect=tuple(map(int,drive.cmd("rect",retry=False).split()))
            if action=="click":
                if type(x) is not int or type(y) is not int or not 0<=x<record["width"] or not 0<=y<record["height"]: raise ValueError("Screenshot-relative point required")
                # Mapping is allowed only when UM captured the exact client size.
                if (record["width"],record["height"])!=rect[2:]: raise PermissionError("Capture/client geometry mismatch; no guessed click scaling")
                command=f"click {x} {y}"
            elif action in {"key","hold"}:
                key={"esc":"escape","return":"enter"}.get(str(key).strip().lower(),str(key).strip().lower())
                if key not in KEYS: raise PermissionError("Key is outside the offline test profile")
                if action=="hold":
                    if not isinstance(seconds,(float,int)) or not 0<seconds<=1: raise ValueError("Hold must be <=1 second")
                    command=f"hold {KEYS[key]} {int(seconds*1000)}"
                else: command=f"key {KEYS[key]}"
            elif action=="look":
                if type(dx) is not int or type(dy) is not int or abs(dx)>400 or abs(dy)>400: raise ValueError("Bounded relative look required")
                command=f"rel {dx} {dy}"
            else: raise ValueError("Unknown game action")
            with self.input_lock:
                self.require("play")
                if not self.focused or self.input_lease is None:raise PermissionError("Single operator lease required")
                if not backend.is_foreground(target): raise PermissionError("Foreground changed before game input")
                reply=drive.cmd(command,retry=False)
            if reply!="ok": raise RuntimeError("UM input outcome unknown: "+reply)
            self.audit.append({"at":time.time(),"snapshot_id":snapshot_id,"command":command,"target":target})
        finally: drive.close()
        return self.observe()

    def close_game(self):
        self.require("play")
        if self.owned:
            import psutil
            try: psutil.Process(self.owned["pid"])
            except psutil.NoSuchProcess:
                return {"status":"already exited; no close repeated","lease_status":self.context()["lease_status"]}
        backend,target=self._target()
        import ctypes
        from ctypes import wintypes
        backend._user32().PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        backend._user32().PostMessageW(target["handle"],0x0010,0,0)
        return {"status":"normal close requested; no forced kill", "owned_game":self.owned}

    def verify(self,snapshot_id,contains):
        self.require("inspect")
        row=self.snapshot
        if not row or row["id"]!=snapshot_id or time.time()-row["at"]>15: raise PermissionError("Fresh game screenshot/log evidence required")
        if not isinstance(contains,str) or not 3<=len(contains)<=300: raise ValueError("Exact bounded RGL condition required")
        matches=[line for line in row["log"]["untrusted_log"] if contains in line]
        return {"status":"RGL CRITERION VERIFIED" if matches else "NOT VERIFIED", "scope":"exact observed RGL text; not whole Gate B or visual acceptance",
                "matches":matches,"image_sha256":row["image_sha256"],"snapshot_id":snapshot_id,
                "scripts_sha256":digest(self.game/"Modules/AI_Island_Test/scripts.txt"),"evidence":row["image"]}

    def shutdown(self):
        self.cancel.set(); self.pause_input()
        if self.guard and not self.save_watch_started:
            guard=self.guard; self.save_watch_started=True
            def finish():
                # Stop releases input immediately, while existing save locks
                # remain until this exact owned game process has exited.
                if self.owned:
                    import psutil
                    try:
                        p=psutil.Process(self.owned["pid"])
                        if p.create_time()==self.owned["started"]: p.wait()
                    except psutil.NoSuchProcess: pass
                try:
                    result=guard.verify()
                    if self.owned:
                        lease=Path(self.owned["lease"])
                        for _ in range(30):
                            try:
                                state=json.loads(lease.read_text(encoding="utf-8-sig"))
                                if state.get("restored"): break
                            except (OSError,ValueError): state={}
                            time.sleep(.5)
                        lines=self.config.read_text(encoding="utf-8-sig").splitlines()
                        actual=[s for s in lines if re.match(r"^battle_size\s*=",s)]
                        result["lease_restoration"]={"manifest":str(lease),"reported_restored":state.get("restored",False),
                            "actual_battle_size_lines":actual,"expected_original":state.get("originalLine"),
                            "verified":bool(state.get("restored") and actual==[state.get("originalLine")])}
                    (self.evidence/"save-preservation.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
                finally:
                    guard.close();self.guard=None
            threading.Thread(target=finish,daemon=True,name="quartz-warband-save-watch").start()
        (self.evidence/"audit.json").write_text(json.dumps(self.audit,indent=2),encoding="utf-8")

    def pause_input(self):
        with self.input_lock:
            self.snapshot=None;self.focused=False;self.capabilities.discard("play")
            if self.input_lease:self.input_lease.close();self.input_lease=None
