"""Local admission gate for a future authenticated Notion tool transport.

Not wired into chat or any network endpoint. This is NOT a Notion API protocol.
Only the local owner supplies scope, handlers and authorization. Existing broker
checks still apply inside each handler; no bearer is accepted from model text.
Receipts are process-local: never automatically resubmit after a process crash.
"""
from copy import deepcopy
import hashlib
import json
import math
import re
import threading
import time


class NotionLocalTools:
    FIELDS = {"schema_version", "task_id", "session_id", "request_id",
              "tool_name", "arguments", "project_id", "scope_ref", "deadline"}

    def __init__(self, *, task_id, session_id, project_id, scope_ref, tools,
                 authorize, expires_at, enabled=False, cancel=None,
                 clock=time.monotonic, max_receipts=256):
        for value in (task_id, session_id, project_id, scope_ref):
            self._identifier(value)
        if not callable(authorize) or not tools or any(
                not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", k)
                or not callable(v) for k, v in tools.items()):
            raise ValueError("Yerel araç bağlaması geçersiz.")
        if (not self._number(expires_at) or expires_at <= clock() or
                type(max_receipts) is not int or not 1 <= max_receipts <= 1000 or
                (cancel is not None and not callable(cancel))):
            raise ValueError("Yerel görev sınırları geçersiz.")
        self._binding = dict(task_id=task_id, session_id=session_id,
                             project_id=project_id, scope_ref=scope_ref)
        self._tools, self._authorize = dict(tools), authorize
        self._expires, self._clock = expires_at, clock
        self._enabled = enabled is True
        self._cancel, self._limit = cancel, max_receipts
        self._lock, self._stopped = threading.RLock(), threading.Event()
        self._receipts, self._active = {}, None
        self._revoked = False

    @staticmethod
    def _identifier(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
            raise ValueError("Araç isteği kimliği geçersiz.")

    @staticmethod
    def _number(value):
        return type(value) in (int, float) and math.isfinite(value)

    def _validate(self, request):
        if not isinstance(request, dict) or set(request) != self.FIELDS:
            raise ValueError("Araç isteği şeması geçersiz.")
        if type(request["schema_version"]) is not int or request["schema_version"] != 1:
            raise ValueError("Araç isteği sürümü desteklenmiyor.")
        for key in self._binding.keys() | {"request_id"}:
            self._identifier(request[key])
        if any(request[k] != v for k, v in self._binding.items()):
            raise PermissionError("Araç isteği etkin görev kapsamına ait değil.")
        if not isinstance(request["tool_name"], str) or request["tool_name"] not in self._tools:
            raise PermissionError("Bu araç görev için bağlanmamış.")
        if not isinstance(request["arguments"], dict) or not self._number(request["deadline"]):
            raise ValueError("Araç parametreleri veya süre sınırı geçersiz.")
        # Round-trip separates mutable caller data; JSON rejects opaque objects,
        # NaN and Infinity. Notion/model output is never evaluated as Python.
        encoded = json.dumps(request, allow_nan=False, sort_keys=True, ensure_ascii=True)
        if len(encoded) > 32768:
            raise ValueError("Araç isteği boyut sınırını aştı.")
        return json.loads(encoded), hashlib.sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _reply(request_id, status, **extra):
        return {"request_id": request_id, "status": status,
                "verification": "none", **extra}

    def call(self, request):
        request, digest = self._validate(request)
        rid = request["request_id"]
        with self._lock:
            if not self._enabled or self._stopped.is_set() or self._clock() >= self._expires:
                return self._reply(rid, "blocked", error="Yerel araç bağlantısı kapalı veya sona ermiş.")
            old = self._receipts.get(rid)
            if old:
                if old["digest"] != digest:
                    raise PermissionError("İstek kimliği farklı içerikle yeniden kullanılamaz.")
                return deepcopy(old["reply"])
            if self._clock() >= request["deadline"]:
                return self._reply(rid, "blocked", error="İsteğin süresi dolmuş.")
            if self._active is not None:
                return self._reply(rid, "blocked", error="Önceki araç işlemi sürüyor; yeni işlem başlatılmadı.")
            if len(self._receipts) >= self._limit:
                return self._reply(rid, "blocked", error="Görev işlem kaydı sınırına ulaştı.")
            self._active = rid
            self._receipts[rid] = {"digest": digest, "reply": self._reply(rid, "executing")}
        dispatched = False
        try:
            # This callback must consult CURRENT local task/scope state. A model
            # echoing scope_ref is not an authorization grant.
            approved = self._authorize(request["tool_name"], deepcopy(request["arguments"]))
            with self._lock:
                if (approved is not True or self._stopped.is_set() or
                        self._clock() >= min(self._expires, request["deadline"])):
                    reply = self._reply(rid, "blocked", error="Güncel yerel yetki veya süre doğrulanamadı.")
                else:
                    dispatched = True
                    reply = None
            if dispatched:
                # Handlers must check stopped and their existing broker/writer
                # capability at the actual side-effect boundary. stop() revokes
                # that owner capability through cancel(), outside this lock.
                result = self._tools[request["tool_name"]](deepcopy(request["arguments"]), self._stopped)
                reply = self._reply(rid, "completed", result=deepcopy(result))
        except Exception:
            # Exceptions can contain paths, credentials or user content. Preserve
            # uncertainty without returning raw exception text or retrying.
            reply = self._reply(rid, "failed", uncertain=dispatched,
                                error="Yerel araç işlemi tamamlanamadı; otomatik tekrar yapılmadı.")
        finally:
            with self._lock:
                if self._stopped.is_set():
                    reply = self._reply(rid, "cancelled", uncertain=dispatched)
                elif dispatched and self._clock() >= min(self._expires, request["deadline"]):
                    reply = self._reply(rid, "failed", uncertain=True,
                                        error="İşlem sırasında süre doldu; sonuç yeniden gözlenmeli.")
                self._receipts[rid]["reply"] = reply
                self._active = None
        return deepcopy(reply)

    def stop(self):
        with self._lock:
            first = not self._stopped.is_set()
            self._stopped.set()
        if first and self._cancel:
            try:
                self._revoked = self._cancel() is True
            except Exception:
                self._revoked = False
        return {"stopped": True, "owner_revocation_verified":
                self._revoked}
