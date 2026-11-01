"""Main-chat lifecycle for the verified read-only Notion Worker fixture.

Scope: ONLY the disposable read-only test project (one ``fixture.txt`` created
here per approved task). No general file access, shell, writing, screenshots,
Desktop Broker, REA or Squad. The verified transport (signed grant/request/
result, durable SQLite receipt, file identity/hash checks) lives unchanged in
``core.notion_worker_bridge``; this module only drives it from a chat turn.

Authority comes from the local owner, never from remote text:
- the manifest/scope is created here after an in-chat approval of a pending
  record that is bound to conversation, message and expiry;
- model output, queue rows and Squad messages never create or widen scope;
- Stop/timeout/shutdown revoke locally first; a late result is not published;
- on construction, any non-terminal fixture from an earlier process is fenced
  (``.stopped``), so a restart never revives an old grant.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import threading
import time
import uuid

from core.atomic_json import atomic_write_json, load_json
from core.notion_cli import NotionCli, NotionError, profile_root
from core.notion_worker_bridge import NotionQueueApi, ReadOnlyWorkerBridge, load_bridge_key, rich, sign

MODE = "readonly-fixture"
PROJECT_ID = "quartz-readonly-fixture"
TOOL = "read_test_file"
TERMINAL = {"completed", "blocked", "failed", "cancelled"}
SCOPE_SUMMARY = "Quartz test projesi · yalnız fixture.txt · salt okunur · 15 dakika"

# Conservative intent: the user must name the test project/file AND ask to read
# or inspect it. Anything else stays a normal cloud chat turn.
_TARGET = re.compile(r"\b(test|deneme)\s*(projes|dosya|klasör)\w*|\bfixture(\.txt)?\b", re.I)
_ACTION = re.compile(r"\b(oku|incele|kontrol|bak|göster|özetle|read|inspect|check|open|aç)\w*", re.I)


def wants_local_read(text):
    text = str(text or "")
    return bool(_TARGET.search(text) and _ACTION.search(text))


class NotionToolCancelled(RuntimeError):
    pass


class NotionWorkerTasks:
    APPROVAL_TTL = 120
    GRANT_TTL = 900
    REQUEST_WAIT = 100
    RESULT_WAIT = 70
    POLL = 2.0

    def __init__(self, runtime, *, home=None, queue_factory=NotionQueueApi, cli_factory=NotionCli,
                 key_loader=load_bridge_key, clock=time.time, sleep=None):
        self.runtime = runtime
        self.home = Path(home or profile_root())
        self.fixtures = self.home / "worker-fixtures"
        self.queue_factory, self.cli_factory, self.key_loader = queue_factory, cli_factory, key_loader
        self.clock = clock
        self._wake = threading.Event()
        self._sleep = sleep or (lambda seconds: self._wake.wait(seconds))
        self._lock = threading.RLock()
        self._pending = None          # awaiting in-chat approval
        self._view = None             # what the UI renders (notion_tools.task)
        self._revision = 0
        self._active = None           # {"bridge", "stop_path", "run_id", "stopped": Event}
        self._key_cache = (0.0, None)
        self.fenced_on_start = self._fence_stale()

    # ---------------------------------------------------------------- state
    def _fence_stale(self):
        """Restart safety: no earlier grant can become active again."""
        fenced = 0
        if not self.fixtures.is_dir():
            return fenced
        root = self.fixtures.resolve()
        for manifest_path in root.glob("*/manifest.json"):
            try:
                if manifest_path.resolve().parent.parent != root:
                    continue
                manifest = load_json(manifest_path, {})
                if manifest.get("state") in {"completed", "observed", "verified", "stopped", "expired",
                                             "denied", "failed", "blocked", "cancelled"}:
                    continue
                (manifest_path.parent / ".stopped").touch()
                manifest["state"] = "expired"
                manifest["fenced_reason"] = "restart"
                atomic_write_json(manifest_path, manifest)
                fenced += 1
            except Exception:
                continue
        return fenced

    def _set_view(self, **values):
        with self._lock:
            self._revision += 1
            base = self._view or {}
            self._view = {**base, **values, "revision": self._revision}
            return deepcopy(self._view)

    def _bridge_config(self):
        config = self.runtime.configuration()
        bridge = load_json(self.home / "worker-bridge.json", {})
        if not isinstance(bridge, dict):
            bridge = {}
        return config, bridge

    def _key(self):
        checked, key = self._key_cache
        if time.monotonic() - checked < 60:
            return key
        try:
            _, bridge = self._bridge_config()
            key = self.key_loader(bridge["credential_target"])
            key = key if isinstance(key, bytes) and len(key) == 32 else None
        except Exception:
            key = None
        self._key_cache = (time.monotonic(), key)
        return key

    def availability(self):
        """Local checks only; the network check is the runtime's cached background probe."""
        config, bridge = self._bridge_config()
        if (bridge.get("mode") != MODE or not bridge.get("queue_id") or not bridge.get("credential_target")
                or not config.get("workspace_id") or bridge.get("workspace_id") != config.get("workspace_id")):
            return "unavailable", "Bu profilde salt okunur araç köprüsü yapılandırılmamış."
        if bridge.get("enabled") is False or bridge.get("main_chat") is not True:
            return "unavailable", ("Araç köprüsü bu profilde ana sohbet için kapalı. "
                                   "Etkinleştirme açık bir yönetici adımıdır.")
        if self._key() is None:
            return "blocked", "İmza anahtarı bu Windows profilinde bulunamadı. Köprü kurulumunu kontrol edin."
        connection = self.runtime.connection_status() if hasattr(self.runtime, "connection_status") else {}
        if not connection.get("ready"):
            if connection.get("checking"):
                return "checking", "Notion bağlantısı doğrulanıyor."
            return "blocked", connection.get("error") or "Notion bağlantısı doğrulanmadı."
        return "ready", "Yalnız onaylı test projesi okunabilir. Her işlem için izin istenir."

    def payload(self, conversation_id=None):
        try:
            availability, message = self.availability()
        except Exception:
            availability, message = "blocked", "Araç köprüsü durumu okunamadı."
        with self._lock:
            task = deepcopy(self._view) if self._view else None
        if task and conversation_id and task.get("conversation_id") != conversation_id:
            task = None
        return {"schema_version": 1, "availability": availability,
                "capabilities": [TOOL] if availability == "ready" else [],
                "message": message, "task": task}

    # ------------------------------------------------------------- approval
    def decide(self, pending_id, conversation_id, accept, *, confirmed=False):
        """Single-use, bound to the CURRENT pending record of the CURRENT turn."""
        with self._lock:
            pending = self._pending
            if not pending or pending["id"] != pending_id:
                raise PermissionError("Bu izin isteği artık geçerli değil.")
            if pending["conversation_id"] != conversation_id:
                raise PermissionError("İzin başka bir sohbete ait.")
            if pending["decision"] is not None:
                raise PermissionError("Bu izin zaten işlendi.")
            if self.clock() >= pending["expires_at"]:
                raise PermissionError("İzin isteğinin süresi doldu.")
            if not pending["is_active"]():
                raise PermissionError("İzin isteyen sohbet turu bitti veya durduruldu.")
            if accept and confirmed is not True:
                raise PermissionError("Onay açıkça teyit edilmedi.")
            pending["decision"] = "approved" if accept else "denied"
            self._wake.set()
            return {"decision": pending["decision"]}

    def _await_decision(self, pending, cancelled):
        while True:
            with self._lock:
                decision = pending["decision"]
            if decision:
                return decision
            if cancelled():
                return "cancelled"
            if self.clock() >= pending["expires_at"]:
                return "expired"
            self._wake.clear()
            self._sleep(0.25)

    # -------------------------------------------------------------- the run
    def run_turn(self, *, conversation_id, message_id, prompt, session_id, cancelled, publish):
        """Blocking; called on the chat worker thread. Returns (status, text, session_id).

        ``publish(text, view)`` updates the chat message; ``cancelled()`` is
        the turn's Stop state. Never raises with remote/user content.
        """
        with self._lock:
            if self._pending or self._active:
                return "blocked", "Önceki Notion araç görevi sürüyor; yeni yerel işlem başlatılmadı.", session_id
            task_id = uuid.uuid4().hex
            pending = {"id": uuid.uuid4().hex, "conversation_id": conversation_id, "message_id": message_id,
                       "expires_at": self.clock() + self.APPROVAL_TTL, "decision": None,
                       "is_active": lambda: not cancelled()}
            self._pending = pending
            self._revision = 0
            self._view = None
        view = self._set_view(task_id=task_id, session_id=session_id or "", conversation_id=conversation_id,
                              state="awaiting_approval", operator="notion", verification="none",
                              message="Notion yerel test dosyasını okumak istiyor.",
                              request={"tool_name": TOOL, "scope_summary": SCOPE_SUMMARY},
                              pending={"id": pending["id"], "expires_at": pending["expires_at"]},
                              remote={"status": "", "stop_verified": None})
        publish("Notion yerel test dosyasını okumak için izin istiyor. Kapsam: " + SCOPE_SUMMARY +
                ". İzin kartından onaylayın veya reddedin.", view)
        decision = self._await_decision(pending, cancelled)
        with self._lock:
            self._pending = None
        if decision != "approved":
            text = {"denied": "İzin verilmedi. Notion'a istek gönderilmedi; yerel işlem yapılmadı.",
                    "expired": "İzin süresi doldu. Notion'a istek gönderilmedi; yerel işlem yapılmadı.",
                    "cancelled": "Görev durduruldu. Notion'a istek gönderilmedi; yerel işlem yapılmadı."}[decision]
            self._set_view(state="cancelled", pending=None, message=text)
            return "cancelled", text, session_id
        try:
            return self._execute(task_id, conversation_id, prompt, session_id, cancelled, publish)
        except NotionToolCancelled:
            return "cancelled", self._view["message"], self._view.get("session_id") or session_id
        except Exception as exc:
            # Before a local scope existed: nothing to revoke beyond the cloud run.
            text = (str(exc) if isinstance(exc, NotionError) else
                    "Araç görevi başlatılamadı; yerel işlem yapılmadı.")
            self._set_view(state="failed", message=text)
            return "failed", text, session_id
        finally:
            with self._lock:
                self._active = None

    def _check(self, cancelled, stop):
        if cancelled() or stop.is_set():
            raise NotionToolCancelled()

    def _wait_run(self, run_id, cancelled, stop, deadline):
        while True:
            run = self.runtime.get(run_id)
            if run["status"] in self.runtime.TERMINAL:
                return run
            if cancelled() or stop.is_set() or self.clock() >= deadline:
                return run
            self._sleep(0.2)

    def _stop_remote(self, run_id):
        """Local stop is immediate; the remote state is reported separately."""
        if not run_id:
            return None
        try:
            current = self.runtime.get(run_id)
            if current["status"] in self.runtime.TERMINAL and current["status"] != "blocked":
                return "idle"   # nothing was running remotely
            self.runtime.cancel(run_id)
        except Exception:
            return False
        end = time.monotonic() + 8
        while time.monotonic() < end:
            run = self.runtime.get(run_id)
            if run["status"] in self.runtime.TERMINAL and run["status"] != "blocked":
                return run["status"] == "cancelled" and not run.get("remote_uncertain")
            time.sleep(0.2)
        return False

    def _finish_stopped(self, manifest_path, manifest, stop_path, run_id, reason):
        stop_path.touch()
        manifest["state"] = "stopped"
        atomic_write_json(manifest_path, manifest)
        verified = self._stop_remote(run_id)
        remote = {True: "Notion oturumunun durduğu doğrulandı.",
                  False: "Notion oturumunun durduğu doğrulanamadı; Notion'da kontrol edin.",
                  "idle": "Notion tarafında çalışan işlem yoktu.",
                  None: "Notion'a istek gönderilmemişti."}[verified]
        text = reason + " Yerel işlem durduruldu; yeni yerel işlem başlatılmaz. " + remote
        self._set_view(state="cancelled", message=text, remote={"status": "", "stop_verified": verified})
        raise NotionToolCancelled()

    def _execute(self, task_id, conversation_id, prompt, session_id, cancelled, publish):
        config, bridge = self._bridge_config()
        if self.availability()[0] != "ready":
            text = "Yerel araç bağlantısı hazır değil; işlem başlatılmadı."
            self._set_view(state="blocked", message=text)
            return "blocked", text, session_id
        key = self._key()
        stop = threading.Event()
        run_id = None
        self._set_view(state="observing", message="Notion oturumu ve yerel kapsam hazırlanıyor.")
        # 1) Owned cloud session. Only sessions this adapter created are continued.
        if session_id and not self.runtime._owned(session_id, config):
            text = "Bu Notion oturumu seçili Quartz bağlantısına ait değil; işlem başlatılmadı."
            self._set_view(state="blocked", message=text)
            return "blocked", text, session_id
        if not session_id:
            run = self.runtime.start("Quartz yerel test görevi için oturum açılıyor. Bu mesajda araç çağırma; "
                                     "bir sonraki mesajda imzalı test iznini vereceğim.")
            run_id = run["id"]
            run = self._wait_run(run_id, cancelled, stop, self.clock() + self.RESULT_WAIT)
            if cancelled():
                self._stop_remote(run_id)
                self._set_view(state="cancelled", message="Görev durduruldu. Yerel işlem yapılmadı.")
                raise NotionToolCancelled()
            if run["status"] != "completed" or not run.get("session_id"):
                text = "Notion oturumu açılamadı; yerel işlem yapılmadı."
                self._set_view(state="failed", message=text)
                return "failed", text, session_id
            session_id = run["session_id"]
        self._set_view(session_id=session_id)
        # 2) Local manifest/scope from the trusted local lifecycle (never remote input).
        folder = self.fixtures / task_id
        folder.mkdir(parents=True, exist_ok=False)
        stop_path = folder / ".stopped"
        path = folder / "fixture.txt"
        proof = uuid.uuid4().hex + uuid.uuid4().hex
        path.write_text("Quartz yerel test dosyası. Okuma kanıtı: " + proof, encoding="utf-8")
        stat = path.stat()
        manifest = {"task_id": task_id, "session_id": session_id, "project_id": PROJECT_ID,
                    "scope_ref": uuid.uuid4().hex, "request_id": uuid.uuid4().hex,
                    "relative_path": "fixture.txt", "expires_at": self.clock() + self.GRANT_TTL,
                    "root": str(folder.resolve()), "file_identity": [stat.st_dev, stat.st_ino, stat.st_size],
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "proof": proof,
                    "agent_id": config["agent_id"], "conversation_id": conversation_id,
                    "origin": "main_chat", "state": "preparing"}
        manifest_path = folder / "manifest.json"
        atomic_write_json(manifest_path, manifest)
        api = self.queue_factory(config["workspace_id"], bridge["queue_id"])
        local = ReadOnlyWorkerBridge(api, key, manifest, folder / "receipts.sqlite", clock=self.clock)
        with self._lock:
            self._active = {"bridge": local, "stop": stop}
        try:
            self._check(cancelled, stop)
            grant = {k: manifest[k] for k in ("task_id", "session_id", "project_id", "scope_ref",
                                              "request_id", "relative_path", "expires_at")}
            grant["tool_name"] = TOOL
            row = api.create("grant:" + task_id, {
                "Task ID": rich(task_id), "Session ID": rich(session_id), "Project ID": rich(PROJECT_ID),
                "State": {"select": {"name": "completed"}},
                "Expires At": {"date": {"start": datetime.fromtimestamp(manifest["expires_at"], timezone.utc).isoformat()}},
                "Signed Result": rich(sign("grant", grant, key))})
            api.page(row["id"])
            manifest.update(grant_page_id=row["id"], state="prepared")
            atomic_write_json(manifest_path, manifest)
            self._check(cancelled, stop)
            # 3) One submission. Persisted BEFORE the uncertain network boundary.
            manifest["request_submitted"] = True
            atomic_write_json(manifest_path, manifest)
            message = (str(prompt).strip() + "\n\n[Quartz] Bu görev için yerel salt okunur test izni verildi. "
                       "quartzReadTestFile aracını bir kez çağır: grant_page_id=" + row["id"] +
                       ", request_id=" + manifest["request_id"] + ", relative_path=fixture.txt. "
                       "Kuyruğa alındıysa sonucu uydurma; Quartz'ın hazır bildirimini bekle.")
            run_id = self.runtime.start(message, session_id=session_id)["id"]
            self._set_view(state="executing", operator="quartz",
                           message="Notion aracı çağırıyor; Quartz yerel okuyucusu imzalı isteği bekliyor.")
            publish("Notion yerel okuma isteğini hazırlıyor…", self._view)
            local_result, done_without_request = None, 0
            end = min(self.clock() + self.REQUEST_WAIT, manifest["expires_at"])
            while self.clock() < end:
                if cancelled() or stop.is_set():
                    local.stop()
                    self._finish_stopped(manifest_path, manifest, stop_path, run_id, "Görev durduruldu.")
                run = self.runtime.get(run_id)
                # Once the signed result is published, only wait for the cloud
                # turn to finish. Re-querying/re-publishing the same receipt adds
                # network roundtrips without adding evidence or local work.
                for page in ([] if local_result else api.query(task_id, session_id)):
                    if page.get("properties", {}).get("Signed Request", {}).get("rich_text"):
                        local_result = local.process(page)
                        if local_result is None:   # stopped during processing: never published
                            self._finish_stopped(manifest_path, manifest, stop_path, run_id, "Görev durduruldu.")
                        manifest.update(request_page_id=page["id"], local_result=local_result)
                        atomic_write_json(manifest_path, manifest)
                if local_result and run["status"] in self.runtime.TERMINAL:
                    break
                if run["status"] == "blocked":
                    text = "Notion ajanı kendi tarafında onay bekliyor; Quartz bunu otomatik onaylamadı."
                    self._stop_remote(run_id)
                    self._set_view(state="blocked", message=text)
                    return "blocked", text, session_id
                if run["status"] in {"failed", "cancelled"}:
                    text = "Notion oturumu araç isteği oluşmadan sona erdi."
                    self._set_view(state="failed", message=text)
                    return "failed", (run.get("result", "") + "\n\n" + text).strip(), session_id
                if run["status"] == "completed" and not local_result:
                    done_without_request += 1
                    if done_without_request >= 2:
                        text = "Notion yanıt verdi ama imzalı araç isteği oluşmadı; yerel okuma yapılmadı."
                        self._set_view(state="failed", message=text)
                        return "failed", (run.get("result", "") + "\n\n" + text).strip(), session_id
                self._sleep(self.POLL)
            if not local_result:
                local.stop()
                stop_path.touch()
                text = "İmzalı araç isteği süre içinde gelmedi; yerel okuma yapılmadı ve istek tekrarlanmadı."
                self._stop_remote(run_id)
                self._set_view(state="failed", message=text)
                return "failed", text, session_id
            if local_result.get("status") != "completed":
                text = "Yerel okuyucu isteği reddetti (kapsam, süre veya dosya kimliği doğrulanamadı)."
                self._set_view(state="failed", message=text)
                return "failed", text, session_id
            first = self.runtime.get(run_id)
            self._set_view(state="verifying", verification="observed",
                           message="Dosya yerelde okundu; Notion'ın sonucu kullanması bekleniyor.")
            self._check(cancelled, stop)
            if not manifest.get("result_notice_submitted"):
                manifest["result_notice_submitted"] = True
                atomic_write_json(manifest_path, manifest)
                run_id = self.runtime.start("Yerel okuyucu işlemi bitirdi. quartzReadResult aracını request_page_id=" +
                                            manifest["request_page_id"] + " ile kullan. Dosyadaki okuma kanıtını ve "
                                            "sha256 değerini yalnız gerçek araç sonucundan okuyarak yaz.",
                                            session_id=session_id)["id"]
            final = self._wait_run(run_id, cancelled, stop, self.clock() + self.RESULT_WAIT)
            if cancelled() or stop.is_set():
                local.stop()
                self._finish_stopped(manifest_path, manifest, stop_path, run_id, "Görev durduruldu.")
            if final["status"] not in self.runtime.TERMINAL:
                self._stop_remote(run_id)
                text = "Notion sonucu süre içinde kullanmadı. Dosya yerelde okundu; ajan yanıtı doğrulanmadı."
                self._set_view(state="failed", verification="observed", message=text)
                return "failed", text, session_id
            answer = "\n\n".join(part for part in (first.get("result", ""), final.get("result", "")) if part).strip()
            used = manifest["proof"] in answer and manifest["sha256"] in answer
            manifest.update(state="verified" if used else "observed", proof_in_cloud_response=used)
            atomic_write_json(manifest_path, manifest)
            stop_path.touch()   # single-use grant: closed after the result
            if final["status"] == "completed" and used:
                self._set_view(state="completed", verification="verified",
                               message="Notion gerçek dosya sonucunu yanıtında kullandı (kanıt ve SHA-256 eşleşti).")
                return "completed", answer, session_id
            text = ("Dosya yerelde okundu, ancak Notion yanıtında gerçek sonucun kullanıldığı doğrulanamadı."
                    if final["status"] == "completed" else "Notion sonucu kullanmadan sona erdi.")
            self._set_view(state="completed" if final["status"] == "completed" else "failed",
                           verification="observed", message=text)
            return ("completed" if final["status"] == "completed" else "failed"), (answer + "\n\n" + text).strip(), session_id
        except NotionToolCancelled:
            raise
        except Exception as exc:
            local.stop()
            if cancelled() or stop.is_set():
                # A Stop raced the local step: report it as a stop, not a failure.
                self._finish_stopped(manifest_path, manifest, stop_path, run_id, "Görev durduruldu.")
            stop_path.touch()
            uncertain = bool(getattr(exc, "uncertain", False)) or bool(manifest.get("request_submitted"))
            safe = str(exc) if isinstance(exc, NotionError) else "Araç görevi güvenli biçimde durduruldu."
            text = safe + (" İstek otomatik tekrarlanmadı." if uncertain and "tekrarlanmadı" not in safe else "")
            manifest["state"] = "failed"
            atomic_write_json(manifest_path, manifest)
            self._stop_remote(run_id)
            self._set_view(state="failed", message=text)
            return "failed", text, session_id

    # ------------------------------------------------------------ shutdown
    def stop_all(self):
        with self._lock:
            if self._pending and self._pending["decision"] is None:
                self._pending["decision"] = "cancelled"
            active = self._active
        self._wake.set()
        if active:
            active["stop"].set()
            active["bridge"].stop()
        return {"stopped": True}
