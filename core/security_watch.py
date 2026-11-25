"""Eos, the security watcher: runs while SpeS is open, task or not (14 Nov; rewritten 25 Nov).

Decisions come from one table, core.security_manifest (docs/EOS_GUVENLIK_MANIFESTI.md is
generated from it). This module only gathers signals and carries out the user's one-tap
actions:

- new processes (psutil, every 10 s), autostart entries (Run/RunOnce and the Startup folder,
  every 60 s), executables arriving in Downloads (every 30 s) and Windows Defender's own
  detections (event 1116/1117/1015, every 2 min);
- for each, the signals the manifest reads: where the file is, who signed it
  (core.security_signals), whether the command line matches an abuse pattern, whether it is
  SpeS's own helper, whether the file is empty.

Location alone never raises an alarm any more (live 25 Nov: all 36 recorded alerts were
Microsoft-signed helpers, SpeS's own helper or a test). A trusted signature never mutes an
abuse pattern. Limits apply to what is said, never to what is recorded. Autostart entries and
Downloads are remembered on disk, so what was added while SpeS was closed is still reported.

What it does (agreed with the user, 14 Nov, unchanged): safe, reversible one-tap actions bound
to their own alert, re-checked before they run; nothing automatic; nothing needing
administrator rights. Screen, file and command-line text is data, never a decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json
from core.security_manifest import SIGNATURE_LABEL, Signals, classify
from core.security_signals import SignatureChecker, command_target, parent_name

RISKY_EXT = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".hta", ".scr",
             ".lnk", ".jar", ".com", ".pif", ".wsf", ".reg", ".dll"}
ABUSE = [
    ("Gizlenmiş (kodlanmış) PowerShell komutu", re.compile(r"(powershell|pwsh)(\.exe)?\b.*\s-(e|ec|enc|encodedcommand)\s+[A-Za-z0-9+/=]{20,}", re.I)),
    ("Gizli pencerede internetten indirip çalıştıran PowerShell", re.compile(r"(powershell|pwsh).*(-w(indowstyle)?\s+hidden).*(downloadstring|downloadfile|invoke-webrequest|iwr|irm|invoke-expression|iex)", re.I)),
    ("mshta ile internetten betik", re.compile(r"mshta(\.exe)?\s+[\"']?(https?|javascript|vbscript):", re.I)),
    ("certutil ile dosya indirme/çözme", re.compile(r"certutil(\.exe)?\s+.*-(urlcache|decode|decodehex)", re.I)),
    ("rundll32 ile betik çalıştırma", re.compile(r"rundll32(\.exe)?\s+.*javascript:", re.I)),
    ("regsvr32 ile uzaktan betik", re.compile(r"regsvr32(\.exe)?\s+.*/i:\s*https?://", re.I)),
    ("bitsadmin ile gizli indirme", re.compile(r"bitsadmin(\.exe)?\s+.*/transfer", re.I)),
]
ALERT_TTL = 30 * 60
MAX_ALERTS_PER_10_MIN = 6
REPEAT_QUIET = 24 * 60 * 60  # the same file's medium alert is said once a day
KEEP_ALERTS = 200


def _user_dirs():
    home = Path.home()
    temp = Path(os.getenv("TEMP") or home / "AppData" / "Local" / "Temp")
    return {"temp": temp, "downloads": home / "Downloads"}


def _inside(path, folder) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path(folder).resolve())
    except (OSError, ValueError, TypeError):
        return False


def _location(path, dirs) -> str:
    if not path:
        return "other"
    if _inside(path, dirs["downloads"]):
        return "downloads"
    if _inside(path, dirs["temp"]):
        return "temp"
    return "other"


def _empty(path) -> bool:
    try:
        return bool(path) and os.path.getsize(path) == 0
    except OSError:
        return False


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# -- collectors (injectable for tests) ------------------------------------------------
def collect_processes():
    import psutil
    rows = []
    for proc in psutil.process_iter(["pid", "name", "exe", "create_time", "cmdline"]):
        info = proc.info
        rows.append({"pid": info.get("pid"), "name": info.get("name") or "", "exe": info.get("exe") or "",
                     "create": info.get("create_time") or 0.0,
                     "cmdline": " ".join(info.get("cmdline") or [])[:2000]})
    return rows


def collect_autoruns():
    rows = []
    try:
        import winreg
        for hive_name, hive in (("HKCU", winreg.HKEY_CURRENT_USER), ("HKLM", winreg.HKEY_LOCAL_MACHINE)):
            for key in (r"Software\Microsoft\Windows\CurrentVersion\Run", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        index = 0
                        while True:
                            try:
                                name, value, _ = winreg.EnumValue(handle, index)
                            except OSError:
                                break
                            rows.append({"kind": "registry", "hive": hive_name, "key": key, "name": name,
                                         "data": str(value)[:1000]})
                            index += 1
                except OSError:
                    continue
    except ImportError:
        pass
    appdata = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    for folder in (appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",):
        if folder.is_dir():
            for item in folder.iterdir():
                if item.is_file() and item.name.lower() != "desktop.ini":
                    rows.append({"kind": "startup", "path": str(item), "name": item.name})
    return rows


def collect_downloads():
    folder = _user_dirs()["downloads"]
    rows = []
    if folder.is_dir():
        for item in folder.iterdir():
            try:
                if item.is_file() and item.suffix.lower() in RISKY_EXT:
                    stat = item.stat()
                    rows.append({"path": str(item), "name": item.name, "size": stat.st_size, "mtime": stat.st_mtime})
            except OSError:
                continue
    return rows


def collect_defender(after_record=0):
    """Defender detections newer than ``after_record`` (readable without admin)."""
    query = "*[System[(EventID=1116 or EventID=1117 or EventID=1015)]]"
    try:
        out = subprocess.run(["wevtutil", "qe", "Microsoft-Windows-Windows Defender/Operational", f"/q:{query}",
                              "/c:20", "/rd:true", "/f:xml"], capture_output=True, text=True, timeout=20,
                             encoding="utf-8", errors="replace",
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for event in re.findall(r"<Event[ >].*?</Event>", out.stdout or "", re.S):
        record = re.search(r"<EventRecordID>(\d+)</EventRecordID>", event)
        if not record or int(record.group(1)) <= after_record:
            continue
        data = dict(re.findall(r"<Data Name='([^']+)'>([^<]*)</Data>", event))
        rows.append({"record": int(record.group(1)),
                     "event": int((re.search(r"<EventID>(\d+)</EventID>", event) or [0, 0])[1]),
                     "threat": data.get("Threat Name", "") or data.get("Threat name", ""),
                     "path": (data.get("Path", "") or "")[:500], "action": data.get("Action Name", ""),
                     "severity": data.get("Severity Name", "")})
    return rows


class SecurityWatch:
    def __init__(self, emit, *, collectors=None, clock=time.time, quarantine_root=None, interval=5.0,
                 signatures=None, state_path=None):
        self.emit = emit
        self.clock = clock
        self.collectors = {"processes": collect_processes, "autoruns": collect_autoruns,
                           "downloads": collect_downloads, "defender": collect_defender, **(collectors or {})}
        self.every = {"processes": 10, "autoruns": 60, "downloads": 30, "defender": 120}
        self.quarantine = Path(quarantine_root or Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Quartz" / "quarantine")
        # Signature verdicts: `paths -> {path: {"verdict", "publisher"}}` (core.security_signals).
        self.signatures = signatures or SignatureChecker().check
        # Remembered across restarts: autostart entries, Downloads and what was said (25 Nov).
        self.state_path = Path(state_path or self.quarantine.parent / "eos_state.json")
        self.interval = interval
        self._lock = threading.Lock()
        self._seen: dict[str, set] = {}
        self._last_run: dict[str, float] = {}
        self._defender_record = 0
        self._alerts: dict[str, dict] = {}
        self._recent: list[float] = []
        # File identity (SHA-256, else path) -> last time its medium alert was said.
        self._said: dict[str, float] = {}
        self._load_state()
        self._stop = threading.Event()
        self._thread = None

    # -- lifecycle -------------------------------------------------------------------
    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="spes-security-watch", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                pass  # one bad read never stops the watcher
            self._stop.wait(self.interval)

    # -- remembered state ------------------------------------------------------------
    def _load_state(self):
        data = load_json(self.state_path, {})
        if not isinstance(data, dict) or data.get("version") != 1:
            return
        for name in ("autoruns", "downloads"):
            keys = data.get(name)
            if isinstance(keys, list):
                self._seen[name] = {tuple(k) for k in keys if isinstance(k, list)}
        said = data.get("said")
        if isinstance(said, dict):
            now = self.clock()
            self._said = {str(k): float(v) for k, v in said.items()
                          if isinstance(v, (int, float)) and now - float(v) < REPEAT_QUIET}

    def _save_state(self):
        try:
            with self._lock:
                said = dict(self._said)
            atomic_write_json(self.state_path, {
                "version": 1,
                "autoruns": sorted([list(k) for k in self._seen.get("autoruns", set())], key=str),
                "downloads": sorted([list(k) for k in self._seen.get("downloads", set())], key=str),
                "said": said})
        except Exception:
            pass  # memory still works; the next save retries

    # -- scanning --------------------------------------------------------------------
    def tick(self, force=False):
        now = self.clock()
        for name in ("processes", "autoruns", "downloads", "defender"):
            if not force and now - self._last_run.get(name, 0) < self.every[name]:
                continue
            self._last_run[name] = now
            getattr(self, "_scan_" + name)()

    def _diff(self, name, rows, key):
        keys = {key(r): r for r in rows}
        first = name not in self._seen
        fresh = [] if first else [r for k, r in keys.items() if k not in self._seen[name]]
        self._seen[name] = set(keys)
        return fresh

    def _signatures(self, paths) -> dict:
        paths = [p for p in dict.fromkeys(paths) if p]
        if not paths:
            return {}
        try:
            return self.signatures(paths) or {}
        except Exception:
            return {}

    @staticmethod
    def _signature_text(sig) -> str:
        label = SIGNATURE_LABEL.get(sig.get("verdict"), "")
        who = sig.get("publisher")
        return f"{label} ({who})" if who and sig.get("verdict") in ("signed", "microsoft") else label

    def _scan_processes(self):
        dirs = _user_dirs()
        rows = []
        for row in self._diff("processes", self.collectors["processes"](), lambda r: (r["pid"], round(r["create"], 2))):
            abuse = next((label for label, pattern in ABUSE if pattern.search(row.get("cmdline") or "")), None)
            where = _location(row.get("exe"), dirs)
            if abuse or where != "other":
                rows.append((row, abuse, where))  # anything else carries no signal Eos reads
        signed = self._signatures([r["exe"] for r, abuse, where in rows if not abuse])
        for row, abuse, where in rows:
            sig = signed.get(row["exe"], {"verdict": "unknown", "publisher": ""}) if not abuse else {}
            own = not abuse and self.is_own(row["pid"], row["exe"])
            verdict = classify(Signals("process", where, sig.get("verdict", "unknown"), abuse, own, _empty(row["exe"])))
            if verdict.severity == "silent":
                continue
            target = {"pid": row["pid"], "create": row["create"], "name": row["name"], "exe": row["exe"]}
            parent = parent_name(row["pid"])
            started_by = f" Başlatan: {parent}." if parent else ""
            if verdict.rule == "abuse":
                self._alert("high", "process", f"Şüpheli komut: {abuse}",
                            f"{row['name']} (PID {row['pid']}) {abuse.lower()} kalıbıyla başladı. Komut satırı gizlilik "
                            f"için gösterilmiyor.{started_by}", target, ["stop", "ignore"], verdict)
                continue
            folder = {"downloads": "İndirilenler", "temp": "Geçici (Temp)"}.get(where, "Bir")
            kind_word = {"tampered": "imzası bozuk", "signed-elsewhere": "imzalı", "vanished": "kısa ömürlü"}.get(
                verdict.rule, "imzasız")
            actions = ["stop", "quarantine", "ignore"] if where == "downloads" else ["stop", "ignore"]
            self._alert(verdict.severity, "process", f"{folder} klasöründen {kind_word} program çalıştı",
                        f"{row['name']} (PID {row['pid']}) şuradan başladı: {row['exe']}. İmza: "
                        f"{self._signature_text(sig)}.{started_by}", target, actions, verdict)

    def _scan_autoruns(self):
        def key(r):
            return (r.get("kind"), r.get("hive"), r.get("key"), r.get("name"), r.get("data"), r.get("path"))
        fresh = self._diff("autoruns", self.collectors["autoruns"](), key)
        targets = {id(r): (command_target(r["data"]) if r["kind"] == "registry" else r.get("path", "")) for r in fresh}
        signed = self._signatures(list(targets.values()))
        for row in fresh:
            path = targets[id(row)]
            sig = signed.get(path, {"verdict": "unknown", "publisher": ""})
            verdict = classify(Signals("autorun" if row["kind"] == "registry" else "startup",
                                       _location(path, _user_dirs()), sig["verdict"], None, False,
                                       _empty(path), row.get("hive", "")))
            if verdict.severity == "silent":
                continue
            if row["kind"] == "registry":
                actions = ["remove_autorun", "ignore"] if row["hive"] == "HKCU" else ["ignore"]
                note = "" if row["hive"] == "HKCU" else " Kaldırmak yönetici izni ister; SpeS bunu yapmaz."
                self._alert(verdict.severity, "autorun", "Bilgisayar açılışına yeni program eklendi",
                            f"{row['hive']}\\...\\{row['key'].rsplit(chr(92), 1)[-1]}: '{row['name']}' → {row['data']}. "
                            f"İmza: {self._signature_text(sig)}.{note}", dict(row), actions, verdict)
            else:
                self._alert(verdict.severity, "autorun", "Başlangıç klasörüne yeni dosya eklendi",
                            f"{row['name']} ({row['path']}). İmza: {self._signature_text(sig)}.", dict(row),
                            ["quarantine", "ignore"], verdict)
        self._save_state()

    def _scan_downloads(self):
        fresh = self._diff("downloads", self.collectors["downloads"](), lambda r: (r["path"], r["mtime"], r["size"]))
        signed = self._signatures([r["path"] for r in fresh])
        for row in fresh:
            sig = signed.get(row["path"], {"verdict": "unknown", "publisher": ""})
            verdict = classify(Signals("download", "downloads", sig["verdict"], None, False, row.get("size") == 0))
            if verdict.severity == "silent":
                continue
            self._alert(verdict.severity, "download", "İndirilenler'e çalıştırılabilir dosya geldi",
                        f"{row['name']} ({row['size']} bayt). İmza: {self._signature_text(sig)}. "
                        "Tanımıyorsan açmadan önce sor.", dict(row), ["quarantine", "ignore"], verdict)
        self._save_state()

    def _scan_defender(self):
        rows = self.collectors["defender"](self._defender_record)
        if not rows:
            if "defender" not in self._seen:
                self._seen["defender"] = set()
            return
        newest = max(r["record"] for r in rows)
        first = "defender" not in self._seen
        self._seen["defender"] = set()
        self._defender_record = max(self._defender_record, newest)
        if first:
            return  # baseline: old detections are history
        for row in sorted(rows, key=lambda r: r["record"]):
            what = {1116: "tehdit buldu", 1117: "tehdide müdahale etti", 1015: "şüpheli davranış gördü"}.get(row["event"], "uyarı verdi")
            self._alert("high", "defender", f"Windows Defender {what}",
                        f"{row['threat'] or 'Bilinmeyen tehdit'} — {row['path'] or 'yol yok'}"
                        + (f" (eylem: {row['action']})" if row.get("action") else ""), dict(row), ["ignore"],
                        classify(Signals("defender")))


    _own_hashes = None

    @classmethod
    def own_helper_hashes(cls) -> set:
        """SHA-256 of SpeS's packaged helper, of which read-guard.exe and the observer guards
        are exact copies. Empty when running from source (the helper is a .py there)."""
        if cls._own_hashes is None:
            hashes = set()
            try:
                from core.helper_command import mcp_command
                helper = Path(mcp_command()[0])
                if helper.suffix.lower() == ".exe" and helper.is_file():
                    hashes.add(_sha256(helper))
            except Exception:
                pass
            cls._own_hashes = hashes
        return cls._own_hashes

    def is_own(self, pid, exe=None) -> bool:
        """A helper SpeS itself started or shipped. Live 14 Nov: its read-guard.exe (a copy
        of the packaged helper, started by the Antigravity CLI, so not in SpeS's process
        tree) ran from a Temp workspace and Eos reported it twice. Decided by the process
        tree or by the file's exact content (SHA-256), never by the path or the name."""
        try:
            import psutil
            me = os.getpid()
            if any(parent.pid == me for parent in psutil.Process(int(pid)).parents()):
                return True
        except Exception:
            pass
        if exe:
            try:
                return _sha256(exe) in self.own_helper_hashes()
            except OSError:
                return False
        return False


    # -- alerts ----------------------------------------------------------------------
    def _identity(self, kind, target) -> str:
        """What 'the same finding' means for repeat quiet: the file's content, never its name
        (a renamed program must not inherit another program's silence)."""
        path = target.get("exe") or target.get("path") or ""
        try:
            return "sha256:" + _sha256(path) if path else ""
        except OSError:
            return f"{kind}:{os.path.normcase(str(path))}" if path else ""

    def _alert(self, severity, kind, title, detail, target, actions, verdict=None):
        now = self.clock()
        identity = self._identity(kind, target) if severity == "medium" else ""
        with self._lock:
            alert = {"id": uuid.uuid4().hex[:16], "at": now, "severity": severity, "kind": kind, "title": title,
                     "detail": detail[:600], "actions": list(actions), "used": False, "expires": now + ALERT_TTL,
                     "_target": target}
            if verdict is not None:
                alert["rule"], alert["why"] = verdict.rule, verdict.why
            if kind in ("process",) and target.get("exe"):
                try:
                    alert["_target"]["sha256"] = _sha256(target["exe"]) if "quarantine" in actions else ""
                except OSError:
                    alert["actions"] = [a for a in alert["actions"] if a != "quarantine"]
            if kind in ("download",) or (kind == "autorun" and target.get("kind") == "startup"):
                try:
                    alert["_target"]["sha256"] = _sha256(target["path"])
                except OSError:
                    alert["actions"] = ["ignore"]
            # Recorded always: a burst of harmless findings must never blind Eos (25 Nov).
            self._alerts[alert["id"]] = alert
            if len(self._alerts) > KEEP_ALERTS:
                for old in sorted(self._alerts.values(), key=lambda a: a["at"])[:len(self._alerts) - KEEP_ALERTS]:
                    self._alerts.pop(old["id"], None)
            say = True
            if severity == "medium" and identity:
                last = self._said.get(identity)
                if last is not None and now - last < REPEAT_QUIET:
                    say = False  # kept in the list (and actionable there), not said again
                else:
                    self._said[identity] = now
            if say and severity != "high":
                self._recent = [t for t in self._recent if now - t < 600]
                if len(self._recent) >= MAX_ALERTS_PER_10_MIN:
                    say = False
                else:
                    self._recent.append(now)
        public = self.public(alert)
        if say:
            try:
                self.emit(public)
            except Exception:
                pass
        if severity == "medium" and identity:
            self._save_state()
        return public

    @staticmethod
    def public(alert):
        return {k: v for k, v in alert.items() if not k.startswith("_")}

    def alerts(self):
        with self._lock:
            return [self.public(a) for a in sorted(self._alerts.values(), key=lambda a: -a["at"])][:50]

    def act(self, alert_id, action):
        """Run one of the alert's own actions, once. Returns ``{"ok", "message", "undo"?}``."""
        with self._lock:
            alert = self._alerts.get(str(alert_id))
            if not alert:
                return {"ok": False, "message": "Bu uyarı bulunamadı."}
            if action not in alert["actions"] and not (action == "undo" and alert.get("_undo")):
                return {"ok": False, "message": "Bu uyarı için böyle bir işlem yok."}
            if alert["used"] and action != "undo":
                return {"ok": False, "message": "Bu uyarı için zaten bir işlem yapıldı."}
            if self.clock() > alert["expires"] and action != "undo":
                return {"ok": False, "message": "Uyarının süresi doldu; durum değişmiş olabilir. Yeni bir tarama bekleyin."}
            alert["used"] = True
        target = alert["_target"]
        try:
            if action == "ignore":
                return {"ok": True, "message": "Uyarı yok sayıldı."}
            if action == "stop":
                return self._stop_process(target)
            if action == "quarantine":
                result = self._quarantine(alert, target)
            elif action == "remove_autorun":
                result = self._remove_autorun(alert, target)
            elif action == "undo":
                result = self._undo(alert)
            else:
                result = {"ok": False, "message": "Bilinmeyen işlem."}
        except Exception as exc:
            result = {"ok": False, "message": f"İşlem yapılamadı: {type(exc).__name__}"}
        if not result.get("ok") and action != "undo":
            with self._lock:
                alert["used"] = False
        return result

    def _stop_process(self, target):
        import psutil
        try:
            proc = psutil.Process(int(target["pid"]))
            if abs(proc.create_time() - float(target["create"])) > 0.5 or proc.name() != target["name"]:
                return {"ok": False, "message": "O süreç artık çalışmıyor (aynı numara başka bir programa geçmiş olabilir)."}
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
            return {"ok": True, "message": f"{target['name']} (PID {target['pid']}) durduruldu."}
        except psutil.NoSuchProcess:
            return {"ok": True, "message": "Süreç zaten kapanmış."}
        except psutil.AccessDenied:
            return {"ok": False, "message": "Bu süreç yönetici yetkisiyle çalışıyor; SpeS durduramaz."}

    def _quarantine(self, alert, target):
        path = Path(target.get("path") or target.get("exe") or "")
        if not path.is_file():
            return {"ok": False, "message": "Dosya artık yerinde değil."}
        if not target.get("sha256") or _sha256(path) != target["sha256"]:
            return {"ok": False, "message": "Dosya uyarıdan sonra değişmiş; karantinaya alınmadı."}
        box = self.quarantine / alert["id"]
        box.mkdir(parents=True, exist_ok=False)
        stored = box / (path.name + ".karantina")
        shutil.move(str(path), stored)
        (box / "manifest.json").write_text(json.dumps({"original": str(path), "stored": str(stored),
                                                       "sha256": target["sha256"], "at": self.clock()},
                                                      ensure_ascii=False), encoding="utf-8")
        alert["_undo"] = {"kind": "file", "original": str(path), "stored": str(stored)}
        alert["actions"].append("undo")
        return {"ok": True, "message": f"{path.name} karantinaya alındı (geri alınabilir).", "undo": True}

    def _remove_autorun(self, alert, target):
        if target.get("hive") != "HKCU":
            return {"ok": False, "message": "Bu kayıt yönetici izni ister; SpeS kaldırmaz."}
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, target["key"], 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as handle:
            value, kind = winreg.QueryValueEx(handle, target["name"])
            if str(value)[:1000] != target["data"]:
                return {"ok": False, "message": "Kayıt uyarıdan sonra değişmiş; kaldırılmadı."}
            winreg.DeleteValue(handle, target["name"])
        alert["_undo"] = {"kind": "registry", "key": target["key"], "name": target["name"], "value": value, "type": kind}
        alert["actions"].append("undo")
        return {"ok": True, "message": f"'{target['name']}' açılıştan kaldırıldı (geri alınabilir).", "undo": True}

    def _undo(self, alert):
        undo = alert.pop("_undo", None)
        if not undo:
            return {"ok": False, "message": "Geri alınacak bir işlem yok."}
        if undo["kind"] == "file":
            original = Path(undo["original"])
            if original.exists():
                return {"ok": False, "message": "Aynı yerde yeni bir dosya var; geri alınmadı."}
            shutil.move(undo["stored"], original)
            return {"ok": True, "message": f"{original.name} yerine geri kondu."}
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, undo["key"], 0, winreg.KEY_SET_VALUE) as handle:
            winreg.SetValueEx(handle, undo["name"], 0, undo["type"], undo["value"])
        return {"ok": True, "message": f"'{undo['name']}' açılışa geri eklendi."}
