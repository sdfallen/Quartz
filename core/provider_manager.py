"""Runtime provider health, diagnostics and non-secret telemetry."""

import threading
import time
from datetime import datetime, timezone


def classify_provider_error(exc) -> tuple[str, str]:
    text = str(exc)
    lowered = text.casefold()
    if "401" in text:
        return "invalid_key", "API anahtarı geçersiz veya iptal edilmiş."
    if "403" in text:
        return "permission", "API anahtarının bu modele erişim izni yok."
    if "404" in text:
        return "model_missing", "Seçili model sağlayıcıda bulunamadı."
    if "410" in text:
        return "model_retired", "Seçili model kullanımdan kaldırılmış."
    if "429" in text or "rate limit" in lowered:
        return "rate_limit", "Sağlayıcı kullanım kotası doldu."
    if any(code in text for code in ("500", "502", "503", "504")):
        return "provider_unavailable", "Sağlayıcı geçici olarak kullanılamıyor."
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout", "Sağlayıcı zamanında yanıt vermedi."
    return "request_failed", "Model isteği başarısız oldu."


class ProviderManager:
    """Tracks one active provider. It never exposes credentials or auto-fails over."""

    def __init__(self, provider: str, model: str, configured: bool, clock=time.monotonic):
        self._lock = threading.RLock()
        self._clock = clock
        self._provider = provider
        self._model = model
        self._configured = bool(configured)
        self._status = "unchecked" if configured else "missing_key"
        self._latency_ms = None
        self._last_check = None
        self._last_error_code = None
        self._last_error = None
        self._requests = 0
        self._failures = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._probe_thread = None

    def replace(self, provider: str, model: str, configured: bool) -> None:
        with self._lock:
            self._provider, self._model = provider, model
            self._configured = bool(configured)
            self._status = "unchecked" if configured else "missing_key"
            self._latency_ms = self._last_check = None
            self._last_error_code = self._last_error = None

    def record_success(self, seconds: float, usage=None) -> None:
        with self._lock:
            self._status = "ready"
            self._latency_ms = round(max(0.0, seconds) * 1000)
            self._last_check = datetime.now(timezone.utc).isoformat()
            self._last_error_code = self._last_error = None
            self._requests += 1
            self._input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self._output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)

    def record_error(self, exc) -> None:
        code, message = classify_provider_error(exc)
        with self._lock:
            self._status = "degraded" if code in {"rate_limit", "timeout", "provider_unavailable"} else "error"
            self._last_check = datetime.now(timezone.utc).isoformat()
            self._last_error_code, self._last_error = code, message
            self._requests += 1
            self._failures += 1

    def probe(self, client) -> dict:
        with self._lock:
            if not self._configured:
                return self.snapshot()
            self._status = "checking"
        started = self._clock()
        try:
            response = client.models.list()
            ids = {getattr(item, "id", "") for item in getattr(response, "data", [])}
            if ids and self._model not in ids:
                raise ValueError(f"404 model not listed: {self._model}")
            self.record_success(self._clock() - started)
        except Exception as exc:
            self.record_error(exc)
        return self.snapshot()

    def probe_async(self, client) -> None:
        with self._lock:
            if self._probe_thread and self._probe_thread.is_alive():
                return
            self._probe_thread = threading.Thread(
                target=self.probe, args=(client,), name="provider-health", daemon=True)
            self._probe_thread.start()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "provider": self._provider,
                "model": self._model,
                "configured": self._configured,
                "status": self._status,
                "latency_ms": self._latency_ms,
                "last_check": self._last_check,
                "last_error_code": self._last_error_code,
                "last_error": self._last_error,
                "requests": self._requests,
                "failures": self._failures,
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "automatic_failover": False,
                "policy": "Sağlayıcı otomatik değiştirilmez; böylece araç işlemleri tekrarlanmaz.",
            }
