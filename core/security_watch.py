"""Eos, the security watcher: runs while SpeS is open, task or not (user request 14 Nov 2026).

What it watches (cheap on two cores: psutil and winreg, no PowerShell per tick):
- new processes: a program started from Temp or Downloads, and known abuse patterns in
  a command line (encoded PowerShell, mshta/certutil/rundll32/regsvr32/bitsadmin tricks);
- autostart entries: Run/RunOnce registry values and the Startup folders;
- new executables and scripts in Downloads;
- Windows Defender's own detections (event 1116/1117/1015), every two minutes.

What it does (agreed with the user, 14 Nov):
- Reports every finding in the chat as Eos; high severity rings the phone like a call.
- Safe, reversible one-tap actions, each bound to its alert: stop that exact process
  (PID + start time + name must still match), move that exact file (same SHA-256) to
  SpeS's quarantine, remove that exact per-user autostart value (backed up first).
  Undo for quarantine and autostart. Nothing needing administrator rights is offered.
- No automatic action. The only trustworthy independent signal readable without admin
  is Defender's own detection, and Defender already acts on it; a ransomware guard
  that could act safely would need administrator access, so it is not shipped.
The first scan is a baseline: what already exists when SpeS starts is not reported.
Screen, file and command-line text never decides anything here; it is data.
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


def _user_dirs():
    home = Path.home()
    temp = Path(os.getenv("TEMP") or home / "AppData" / "Local" / "Temp")
    return {"temp": temp, "downloads": home / "Downloads"}


def _inside(path, folder) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path(folder).resolve())
    except (OSError, ValueError, TypeError):
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
    def __init__(self, emit, *, collectors=None, clock=time.time, quarantine_root=None, interval=5.0):
        self.emit = emit
        self.clock = clock
        self.collectors = {"processes": collect_processes, "autoruns": collect_autoruns,
                           "downloads": collect_downloads, "defender": collect_defender, **(collectors or {})}
        self.every = {"processes": 10, "autoruns": 60, "downloads": 30, "defender": 120}
        self.quarantine = Path(quarantine_root or Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Quartz" / "quarantine")
        self.interval = interval
        self._lock = threading.Lock()
        self._seen: dict[str, set] = {}
        self._last_run: dict[str, float] = {}
        self._defender_record = 0
        self._alerts: dict[str, dict] = {}
        self._recent: list[float] = []
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

    def _scan_processes(self):
        dirs = _user_dirs()
        for row in self._diff("processes", self.collectors["processes"](), lambda r: (r["pid"], round(r["create"], 2))):
            abuse = next((label for label, pattern in ABUSE if pattern.search(row.get("cmdline") or "")), None)
            target = {"pid": row["pid"], "create": row["create"], "name": row["name"], "exe": row["exe"]}
            if abuse:
                self._alert("high", "process", f"Şüpheli komut: {abuse}",
                            f"{row['name']} (PID {row['pid']}) {abuse.lower()} kalıbıyla başladı. Komut satırı gizlilik "
                            "için gösterilmiyor.", target, ["stop", "ignore"])
            elif row["exe"] and (_inside(row["exe"], dirs["temp"]) or _inside(row["exe"], dirs["downloads"])):
                where = "İndirilenler" if _inside(row["exe"], dirs["downloads"]) else "Geçici (Temp)"
                actions = ["stop", "quarantine", "ignore"] if _inside(row["exe"], dirs["downloads"]) else ["stop", "ignore"]
                self._alert("medium", "process", f"{where} klasöründen yeni program çalıştı",
                            f"{row['name']} (PID {row['pid']}) şuradan başladı: {row['exe']}", target, actions)

    def _scan_autoruns(self):
        def key(r):
            return (r.get("kind"), r.get("hive"), r.get("key"), r.get("name"), r.get("data"), r.get("path"))
        for row in self._diff("autoruns", self.collectors["autoruns"](), key):
            if row["kind"] == "registry":
                actions = ["remove_autorun", "ignore"] if row["hive"] == "HKCU" else ["ignore"]
                note = "" if row["hive"] == "HKCU" else " Kaldırmak yönetici izni ister; SpeS bunu yapmaz."
                self._alert("medium", "autorun", "Bilgisayar açılışına yeni program eklendi",
                            f"{row['hive']}\\...\\{row['key'].rsplit(chr(92), 1)[-1]}: '{row['name']}' → {row['data']}{note}",
                            dict(row), actions)
            else:
                self._alert("medium", "autorun", "Başlangıç klasörüne yeni dosya eklendi",
                            f"{row['name']} ({row['path']})", dict(row), ["quarantine", "ignore"])

    def _scan_downloads(self):
        for row in self._diff("downloads", self.collectors["downloads"](), lambda r: (r["path"], r["mtime"], r["size"])):
            self._alert("low", "download", "İndirilenler'e çalıştırılabilir dosya geldi",
                        f"{row['name']} ({row['size']} bayt). Tanımıyorsan açmadan önce sor.", dict(row),
                        ["quarantine", "ignore"])

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
                        + (f" (eylem: {row['action']})" if row.get("action") else ""), dict(row), ["ignore"])

    # -- alerts ----------------------------------------------------------------------
    def _alert(self, severity, kind, title, detail, target, actions):
        now = self.clock()
        with self._lock:
            self._recent = [t for t in self._recent if now - t < 600]
            if severity != "high" and len(self._recent) >= MAX_ALERTS_PER_10_MIN:
                return None
            self._recent.append(now)
            alert = {"id": uuid.uuid4().hex[:16], "at": now, "severity": severity, "kind": kind, "title": title,
                     "detail": detail[:600], "actions": list(actions), "used": False, "expires": now + ALERT_TTL,
                     "_target": target}
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
            self._alerts[alert["id"]] = alert
        public = self.public(alert)
        try:
            self.emit(public)
        except Exception:
            pass
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
