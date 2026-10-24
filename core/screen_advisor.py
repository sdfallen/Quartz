"""Opt-in, rate-limited screen change observer for Quartz."""

import threading
import time


class ScreenAdvisor:
    """Watch inexpensive image fingerprints and analyze meaningful changes.

    Captures stay local until a task is active and the user explicitly enables
    the advisor. AI analysis is cooldown-limited to protect CPU and API usage.
    """

    def __init__(self, capture, analyze, on_advice, is_task_active,
                 *, interval=4.0, cooldown=35.0, change_threshold=0.10):
        self._capture = capture
        self._analyze = analyze
        self._on_advice = on_advice
        self._is_task_active = is_task_active
        self._interval = max(1.0, float(interval))
        self._cooldown = max(self._interval, float(cooldown))
        self._change_threshold = float(change_threshold)
        self._enabled = False
        self._stop = threading.Event()
        self._thread = None
        self._last_fingerprint = None
        self._last_analysis = 0.0
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> bool:
        with self._lock:
            self._enabled = bool(enabled)
            self._last_fingerprint = None
            if self._enabled and (not self._thread or not self._thread.is_alive()):
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._run, name="quartz-screen-advisor", daemon=True)
                self._thread.start()
            return self._enabled

    def stop(self) -> None:
        with self._lock:
            self._enabled = False
            self._stop.set()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    @staticmethod
    def fingerprint(image) -> tuple:
        sample = image.convert("L").resize((20, 12))
        getter = getattr(sample, "get_flattened_data", sample.getdata)
        return tuple(getter())

    @staticmethod
    def difference(before: tuple, after: tuple) -> float:
        if not before or not after or len(before) != len(after):
            return 1.0
        return sum(abs(a - b) for a, b in zip(before, after)) / (255 * len(before))

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            if not self.enabled or not self._is_task_active():
                continue
            try:
                image = self._capture(save=False)
                if image is None:
                    continue
                current = self.fingerprint(image)
                previous = self._last_fingerprint
                self._last_fingerprint = current
                if previous is None:
                    continue
                if self.difference(previous, current) < self._change_threshold:
                    continue
                now = time.monotonic()
                if now - self._last_analysis < self._cooldown:
                    continue
                self._last_analysis = now
                advice = self._analyze(
                    "Aktif Quartz görevi açısından bu ekran değişikliğini incele. "
                    "Yalnızca gerçekten faydalıysa Türkçe, kısa ve uygulanabilir bir "
                    "sonraki adım veya görünür engel bildir. Sorun yoksa yalnızca "
                    "NO_ADVICE yaz.", image=image)
                if advice and "NO_ADVICE" not in str(advice).upper():
                    self._on_advice(str(advice).strip())
            except Exception:
                # Monitoring must never destabilize the main assistant.
                continue
