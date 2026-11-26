"""SpeS tries what a job built, inside its window (launch_check v2) — 26 Nov 2026.

Measured 26 Nov 20:21: a tkinter window's buttons, labels and entries have no UI Automation names,
so the desktop operator's reference actions cannot reach the programs SpeS's jobs build. This
module adds the two missing pieces and nothing else (Fides's design review 26 Nov, ŞARTLI):

- a small probe SpeS starts the program through (stdlib only). For tkinter it reports each mapped
  widget's text and place inside the main window and errors raised in callbacks; for pygame the
  drawing surface's size. It runs inside the program, so its report is "instrumented" data: it
  locates targets and is read for expectations, but never counts as independent proof, never as
  an instruction, and never chooses a target outside the window launch_check proved.
- a bounded scenario the writer leaves in the project (``spes_deneme.json``), read once and
  validated whole before any input, run by SpeS with real input through NativeDesktopBackend.act.
  Before every action the runner applies the desktop broker's fences itself (D1): Stop, a fresh
  single-use observation taken right before the action, the input session, the step budget, the
  window's identity and foreground, and a hand on the mouse (Q4: the user moved the pointer).

Outcomes stay apart: "passed" (every expectation held), "smoke" (input was sent, nothing was
asserted), "failed" (an expectation did not hold or the program raised an error), "crashed" (the
program ended with an error), "blocked" (the desktop could not be used safely, never a code
defect) and "cancelled" (Stop).
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import time
from pathlib import Path

SCENARIO_NAME = "spes_deneme.json"
SCHEMA_VERSION = 1
MAX_BYTES = 16 * 1024
MAX_STEPS = 20
MAX_SECONDS = 60.0
MAX_WAIT = 3.0
EXPECT_SECONDS = 2.0
SETTLE_SECONDS = 0.4
SCALE_TOLERANCE = 0.03
PROBE_FRESH_SECONDS = 3.0
CALL_SECONDS = 10.0
POINTER_SLACK = 3
# Fides D1: the scenario's keys are a small subset of the desktop profile — no modifiers, no
# Windows/function/media/browser keys.
SCENARIO_KEYS = frozenset({
    "enter", "tab", "escape", "esc", "up", "down", "left", "right", "space", "backspace",
    "home", "end", "pageup", "pagedown",
    *{chr(c) for c in range(ord("a"), ord("z") + 1)}, *{str(d) for d in range(10)},
    "+", "-", "*", "/", "=", ".", ",",
})

PROBE_SOURCE = r'''"""SpeS probe: runs a program unchanged and reports what its window shows (stdlib only)."""
import json, os, runpy, sys, time, traceback
OUT = os.environ.get("SPES_PROBE_OUT", "")
ENTRY = os.path.abspath(sys.argv[1])
sys.argv = [ENTRY] + sys.argv[2:]
sys.path[0] = os.path.dirname(ENTRY)
_errors, _roots, _seq = [], [], [0]
_MAX_WIDGETS, _MAX_TEXT = 200, 120


def _write(data):
    _seq[0] += 1
    data.update(pid=os.getpid(), seq=_seq[0], at=time.time())
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, OUT)


def _text(w):
    cls = w.winfo_class()
    if cls in ("Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox"):
        try:
            if str(w.cget("show")):
                return None  # a password-style field: its value is never read
        except Exception:
            pass
        try:
            return str(w.get())[:_MAX_TEXT]
        except Exception:
            return ""
    try:
        return str(w.cget("text"))[:_MAX_TEXT]
    except Exception:
        return ""


def _enabled(w):
    try:
        return str(w.cget("state")) != "disabled"
    except Exception:
        return True


def _dump_tk():
    root = next((r for r in _roots if _exists(r)), None)
    if root is None:
        return
    rx, ry = root.winfo_rootx(), root.winfo_rooty()
    items, queue = [], list(root.winfo_children())
    while queue and len(items) < _MAX_WIDGETS:
        w = queue.pop(0)
        try:
            queue.extend(w.winfo_children())
            if not w.winfo_ismapped() or w.winfo_toplevel() is not root:
                continue
            text = _text(w)
            if text is None:
                continue
            items.append({"class": w.winfo_class(), "text": text, "enabled": _enabled(w),
                          "x": w.winfo_rootx() - rx, "y": w.winfo_rooty() - ry,
                          "w": w.winfo_width(), "h": w.winfo_height()})
        except Exception:
            continue
    _write({"kind": "tk", "w": root.winfo_width(), "h": root.winfo_height(), "roots": len(_roots),
            "widgets": items, "errors": _errors[-3:], "error_count": len(_errors)})


def _exists(r):
    try:
        return bool(r.winfo_exists())
    except Exception:
        return False


try:
    import tkinter as _tk
except Exception:
    _tk = None
if _tk is not None and OUT:
    _init = _tk.Tk.__init__
    _report = _tk.Tk.report_callback_exception

    def _patched(self, *a, **k):
        _init(self, *a, **k)
        _roots.append(self)

        def tick():
            try:
                _dump_tk()
            except Exception:
                pass
            try:
                self.after(250, tick)
            except Exception:
                pass
        self.after(50, tick)

    def _recorded(self, exc, val, tb):
        # The program's own handling is kept; SpeS only records that a callback failed.
        _errors.append("".join(traceback.format_exception(exc, val, tb))[-1200:])
        return _report(self, exc, val, tb)
    _tk.Tk.__init__ = _patched
    _tk.Tk.report_callback_exception = _recorded

if os.environ.get("SPES_PROBE_PYGAME") == "1" and OUT:
    # Only when the entry itself imports pygame (SpeS parsed it): the display size is the
    # program's own coordinate system for clicks.
    try:
        import pygame.display as _display
        _last = [0.0]

        def _report_size(force=False):
            # Each frame the program shows refreshes the report (at most twice a second), so a
            # fresh report also means the program is still drawing.
            if not force and time.monotonic() - _last[0] < 0.5:
                return
            surface = _display.get_surface()
            if surface is None:
                return
            w, h = surface.get_size()
            _last[0] = time.monotonic()
            _write({"kind": "pygame", "w": w, "h": h, "widgets": [], "errors": [], "error_count": 0})

        def _wrap(name, force=False):
            original = getattr(_display, name)

            def wrapped(*a, **k):
                result = original(*a, **k)
                try:
                    _report_size(force)
                except Exception:
                    pass
                return result
            setattr(_display, name, wrapped)
        _wrap("set_mode", force=True)
        _wrap("flip")
        _wrap("update")
    except Exception:
        pass

runpy.run_path(ENTRY, run_name="__main__")
'''


class ScenarioError(ValueError):
    pass


def _no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ScenarioError("aynı anahtar iki kez yazılmış")
    return dict(pairs)


def _no_constant(name):
    raise ScenarioError(f"{name} geçerli bir sayı değil")


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def load_scenario(project) -> tuple[dict | None, str]:
    """({"steps", "sha256"}, "") from the project's spes_deneme.json, read once (Fides Q3: the run
    keeps this snapshot even if the file changes); (None, why) when there is none or it is invalid.
    Validated whole before any input: one bad step runs no step at all."""
    path = Path(str(project or "")) / SCENARIO_NAME
    if not path.is_file():
        return None, "senaryo yok"
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_BYTES:
            raise ScenarioError("dosya çok büyük")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
        if isinstance(data, dict):
            unknown = set(data) - {"adimlar", "surum"}
            if unknown:
                raise ScenarioError(f"bilinmeyen alan: {sorted(unknown)[0][:40]}")
            if data.get("surum", SCHEMA_VERSION) != SCHEMA_VERSION:
                raise ScenarioError(f"desteklenen sürüm {SCHEMA_VERSION}")
            steps = data.get("adimlar")
        else:
            steps = data
        return {"steps": validate(steps), "sha256": hashlib.sha256(raw).hexdigest()}, ""
    except (OSError, ValueError) as exc:
        return None, f"senaryo geçersiz: {str(exc)[:160]}"


def validate(steps) -> list:
    from core.desktop_native import CRITICAL, MAX_KEY_SEQUENCE
    if not isinstance(steps, list) or not steps:
        raise ScenarioError("'adimlar' boş olmayan bir liste olmalı")
    if len(steps) > MAX_STEPS:
        raise ScenarioError(f"en çok {MAX_STEPS} adım")
    clean = []
    for n, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not step:
            raise ScenarioError(f"adım {n}: tek eylemli bir nesne olmalı")
        if set(step) == {"tikla"}:
            value = step["tikla"]
            if isinstance(value, str) and 0 < len(value.strip()) <= 100:
                if CRITICAL.search(value):
                    # Fides D1: Tk has no UIA names, so act() cannot see what this button does.
                    raise ScenarioError(f"adım {n}: '{value.strip()[:40]}' sonuçlu bir işlem; SpeS basmaz")
                clean.append({"do": "click_text", "text": value.strip()})
            elif (isinstance(value, list) and len(value) == 2
                  and all(type(v) is int and 0 <= v <= 10000 for v in value)):
                clean.append({"do": "click_at", "x": value[0], "y": value[1]})
            else:
                raise ScenarioError(f"adım {n}: 'tikla' bir metin ya da [x, y] olmalı")
        elif set(step) == {"tus"}:
            keys = step["tus"].strip().lower().split() if isinstance(step["tus"], str) else []
            if not keys or len(keys) > MAX_KEY_SEQUENCE or any(k not in SCENARIO_KEYS for k in keys):
                raise ScenarioError(f"adım {n}: izinli tuşlar dışında ya da çok uzun")
            clean.append({"do": "key", "keys": " ".join(keys)})
        elif set(step) <= {"bas", "sure"} and "bas" in step:
            key = step["bas"].strip().lower() if isinstance(step["bas"], str) else ""
            seconds = step.get("sure", 0.3)
            if key not in SCENARIO_KEYS or not _number(seconds) or not 0 < seconds <= 1:
                raise ScenarioError(f"adım {n}: 'bas' izinli tek tuş, 'sure' 0'dan büyük ve en çok 1 sn olmalı")
            clean.append({"do": "hold", "key": key, "seconds": float(seconds)})
        elif set(step) == {"bekle"}:
            seconds = step["bekle"]
            if not _number(seconds) or not 0 < seconds <= MAX_WAIT:
                raise ScenarioError(f"adım {n}: 'bekle' 0'dan büyük ve en çok {MAX_WAIT:g} sn olmalı")
            clean.append({"do": "wait", "seconds": float(seconds)})
        elif set(step) in ({"beklenen"}, {"beklenen_icerir"}):
            field = next(iter(step))
            value = step[field]
            if not isinstance(value, str) or not 0 < len(" ".join(value.split())) <= 120:
                raise ScenarioError(f"adım {n}: '{field}' kısa bir metin olmalı")
            # Fides Q2: exact by default ("Sayı: 1" never passes on "Sayı: 10"); containment is explicit.
            clean.append({"do": "expect", "text": " ".join(value.split()), "contains": field == "beklenen_icerir"})
        else:
            raise ScenarioError(f"adım {n}: bilinmeyen ya da birden çok eylem ({', '.join(map(str, step))[:40]})")
    return clean


def write_probe(evidence_dir) -> Path:
    path = Path(evidence_dir) / "spes_probe.py"
    path.write_text(PROBE_SOURCE, encoding="utf-8")
    return path


def read_report(path, pid=None, since=None) -> dict | None:
    """The probe's latest report, or None when missing, broken, from another process or stale."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("widgets"), list):
        return None
    if pid is not None and data.get("pid") != pid:
        return None
    at = data.get("at")
    now = time.time()
    if not _number(at) or (since is not None and at < since) or now - at > PROBE_FRESH_SECONDS or at > now + 1:
        return None
    return data


def _client_area(hwnd):
    """The window's client area: (screen left, screen top, width, height) in physical pixels."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    rect, point = wintypes.RECT(), wintypes.POINT(0, 0)
    if not user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(rect)) or \
            not user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(point)):
        raise PermissionError("Pencerenin iç alanı okunamadı")
    return point.x, point.y, rect.right - rect.left, rect.bottom - rect.top


def to_window_pixels(target, report, x, y, client):
    """A point in the program's own client coordinates -> a pixel of the window screenshot.

    Fides D3: the screenshot is the whole window rectangle (frame included) in physical pixels;
    the program draws in its client area, possibly at another DPI. The client corner is read
    fresh, the scale comes from the probe's size against the real client size and is refused when
    the axes disagree or no size is known for a program-coordinate click."""
    left, top, width, height = client
    if not report or not report.get("w") or not report.get("h"):
        raise PermissionError("Programın çizim ölçüsü bilinmiyor; nokta tıklaması güvenilir değil")
    sx, sy = width / float(report["w"]), height / float(report["h"])
    if abs(sx - sy) > SCALE_TOLERANCE * max(sx, sy):
        raise PermissionError("Programın ölçüsü pencereyle tutmuyor; tıklama yeri güvenilir değil")
    px, py = x * sx, y * sy
    if not (0 <= px < width and 0 <= py < height):
        raise ValueError("Nokta pencerenin içinde değil")
    return int(left + px - target["rect"][0]), int(top + py - target["rect"][1])


def _cursor():
    import ctypes
    from ctypes import wintypes
    point = wintypes.POINT()
    return (point.x, point.y) if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)) else None


def _hold(backend, target, key, seconds, stop):
    """Fides I4: a hold goes through the same Native act path as a key — its focused-control
    (CRITICAL), identity, integrity and foreground guards — and Native ends it on Stop
    (input_cancelled) with the key released. A refusal raises before any key is pressed."""
    previous = getattr(backend, "input_cancelled", None)
    backend.input_cancelled = previous if callable(previous) else stop.is_set
    backend.act(target, {"ui": {"elements": []}}, {"action": "hold", "key": key, "seconds": seconds})


class _Call:
    """One backend call on its own thread, owned until it ends (Fides I5).

    The runner waits for it only while Stop is clear and the deadline holds; when it gives up the
    call stays on the run's worker list (launch_check keeps the look unconfirmed and blocks the
    next launch until it ends) and the fence makes any input it would still try refused."""

    def __init__(self, fn, *args):
        import threading
        self.result, self.error, self.done = None, None, threading.Event()
        self.thread = threading.Thread(target=self._run, args=(fn, args), daemon=True, name="spes-interact-call")
        self.thread.start()

    def _run(self, fn, args):
        try:
            self.result = fn(*args)
        except BaseException as exc:  # handed back to the runner, never lost
            self.error = exc
        finally:
            self.done.set()

    def finished(self, timeout: float) -> bool:
        return self.done.wait(max(0.0, timeout))


class _GaveUp(Exception):
    def __init__(self, state, reason):
        super().__init__(reason)
        self.state, self.reason = state, reason


def run(backend, hwnd, steps, stop, *, report_path, review_dir, alive, pid=None, max_seconds=MAX_SECONDS,
        settle=SETTLE_SECONDS, client_area=None, cursor=None, workers=None, call_seconds=CALL_SECONDS) -> dict:
    """Run validated steps in the proved window; always returns a receipt, never raises."""
    import threading
    client_area = client_area or _client_area
    cursor = cursor or _cursor
    workers = workers if workers is not None else []
    review = Path(review_dir)
    review.mkdir(parents=True, exist_ok=True)
    results, began = [], time.monotonic()
    out = {"state": "passed", "steps": results, "reason": "", "instrumented": True,
           "actions": 0, "asserted": 0, "unmeasured": 0}
    abandoned = threading.Event()
    pinned = {}

    def over():
        return time.monotonic() - began > max_seconds

    def call(fn, *args, budget=None):
        # Fides I5: Stop and the deadline are honoured while a call is inside UIA/COM or a capture.
        job = _Call(fn, *args)
        limit = time.monotonic() + (call_seconds if budget is None else budget)
        while not job.finished(0.02):
            if stop.is_set() or over() or time.monotonic() > limit:
                abandoned.set()
                workers.append(job)
                if stop.is_set():
                    raise _GaveUp("cancelled", "durduruldu")
                raise _GaveUp("blocked", "masaüstü çağrısı süresinde bitmedi; SpeS bekletmeden bıraktı")
        if job.error is not None:
            raise job.error
        return job.result

    def same_owner(current):
        # Fides I3: a fresh identity is compared with the one launch proved; never re-authorised.
        return all(current.get(k) == pinned.get(k) for k in ("handle", "pid", "started", "exe", "rect"))

    def fresh_target():
        current = call(backend.identity, hwnd)
        if not same_owner(current):
            raise _GaveUp("blocked", "pencerenin sahibi ya da yeri değişti; girdi gönderilmedi")
        return current

    # Fides I5: an input a given-up call would still try is refused at Native's own last guard.
    original_before = backend._before_input

    def fence(target):
        if abandoned.is_set() or stop.is_set():
            raise PermissionError("SpeS denemeyi bıraktı; geç girdi gönderilmedi")
        if not same_owner(target):
            raise PermissionError("Pencere sahibi değişti; girdi gönderilmedi")
        if over():
            raise PermissionError("Süre doldu; girdi gönderilmedi")

    def fenced(target):
        fence(target)
        result = original_before(target)
        # Fides IR1: the original checks can block; a Stop or give-up that came meanwhile is read
        # again here, right before Native presses or clicks.
        fence(target)
        return result
    backend._before_input = fenced
    backend.input_cancelled = lambda: abandoned.is_set() or stop.is_set()

    def report():
        return read_report(report_path, pid=pid)

    def shot(observation, name):
        data = observation.get("image_base64") if isinstance(observation, dict) else None
        if data:
            (review / name).write_bytes(base64.b64decode(data))
            return name
        return ""

    def end(state, reason, step=None):
        out.update(state=state, reason=reason)
        if step is not None:
            step.update(ok=False, note=reason)
        return out

    def program_error(current):
        # Fides I2: any callback error in a report fails the run, in the same snapshot as a match.
        if current and int(current.get("error_count") or 0) > 0:
            out["error"] = str((current.get("errors") or [""])[-1])[-1200:]
            return True
        return False

    if stop.is_set():
        return end("cancelled", "durduruldu")
    try:
        target = call(backend.identity, hwnd)
        if pid is not None and target.get("pid") != pid:
            return end("blocked", "pencere SpeS'in başlattığı programın değil")
        pinned.update(target)
        backend.validate_target(target)
        call(backend.focus, target)
        if not backend.is_foreground(target):
            return end("blocked", "pencere öne getirilemedi")
        if program_error(report()):
            # A program that raised while starting has no clean baseline (Fides I2).
            return end("failed", "program açılırken hata verdi")
    except _GaveUp as gave:
        return end(gave.state, gave.reason)
    except Exception as exc:
        return end("blocked", f"pencere hazırlanamadı ({type(exc).__name__})")
    pointer = cursor()
    action_seq = None
    for number, step in enumerate(steps, 1):
        item = {"n": number, "do": step["do"], "ok": None, "note": ""}
        results.append(item)
        if stop.is_set():
            return end("cancelled", "durduruldu", item)
        if over():
            return end("blocked", "süre doldu", item)
        if not alive():
            return end("crashed", "program kapandı", item)
        now = cursor()
        if pointer and now and max(abs(now[0] - pointer[0]), abs(now[1] - pointer[1])) > POINTER_SLACK:
            # Fides Q4: someone else is using the mouse; SpeS stops and never takes focus back.
            return end("blocked", "fare SpeS dışında hareket etti; deneme durdu", item)
        try:
            if step["do"] == "wait":
                remaining = max_seconds - (time.monotonic() - began)
                if stop.wait(min(step["seconds"], max(0.0, remaining))):
                    return end("cancelled", "durduruldu", item)
                if over():
                    return end("blocked", "süre doldu", item)
                if program_error(report()):
                    return end("failed", "program beklerken hata verdi", item)
                item["ok"] = True
                continue
            if step["do"] == "expect":
                deadline = min(time.monotonic() + EXPECT_SECONDS, began + max_seconds)
                while True:
                    current = report()
                    if current is not None and action_seq is not None and int(current.get("seq") or 0) <= action_seq:
                        # Fides: an expectation after an input is read from a sample taken after it.
                        if time.monotonic() <= deadline:
                            if stop.wait(0.1):
                                return end("cancelled", "durduruldu", item)
                            continue
                        current = None
                    if current is None or current.get("kind") != "tk":
                        item.update(ok=None, note="ölçülemedi (yalnız tkinter, taze sonda raporu yok)")
                        out["unmeasured"] += 1
                        break
                    if program_error(current):
                        return end("failed", "program hata verdi", item)
                    texts = [" ".join(str(w.get("text", "")).split()) for w in current.get("widgets", [])]
                    if any((step["text"] in t) if step["contains"] else (t == step["text"]) for t in texts):
                        item["ok"] = True
                        out["asserted"] += 1
                        break
                    if time.monotonic() > deadline:
                        item["seen"] = [t for t in texts if t][:12]
                        out["asserted"] += 1
                        return end("failed", f"'{step['text']}' görülmedi", item)
                    if stop.wait(0.2):
                        return end("cancelled", "durduruldu", item)
                continue
            # D1: the broker's fences, here — input session, the launch-proved owner, foreground, a
            # fresh observation taken right before this one action and used once.
            call(backend.validate_input_session)
            current = fresh_target()
            if not backend.is_foreground(current):
                return end("blocked", "pencere öndeki yerini kaybetti", item)
            before = call(backend.observe, current)
            if not before.get("image_base64"):
                return end("blocked", "pencere görüntüsü alınamadı", item)
            item["before"] = shot(before, f"adim-{number:02d}-once.png")
            # Fides I6: nothing is sent once Stop or the deadline came during the observation.
            if stop.is_set():
                return end("cancelled", "durduruldu", item)
            if over():
                return end("blocked", "süre doldu", item)
            if step["do"] == "click_text":
                current_report = report()
                if current_report is None or current_report.get("kind") != "tk":
                    return end("blocked", "metinle tıklama yalnız tkinter'da ve taze sonda raporuyla", item)
                found = [w for w in current_report.get("widgets", [])
                         if " ".join(str(w.get("text", "")).split()) == step["text"]
                         and w.get("enabled", True) and w.get("w", 0) > 0 and w.get("h", 0) > 0]
                if len(found) != 1:
                    return end("failed", f"'{step['text']}' yazılı, görünür ve etkin "
                               + ("tek bir öğe yok" if not found else "birden çok öğe var"), item)
                w = found[0]
                x, y = to_window_pixels(current, current_report, w["x"] + w["w"] / 2, w["y"] + w["h"] / 2,
                                        client_area(hwnd))
                args = {"action": "click", "x": x, "y": y}
            elif step["do"] == "click_at":
                x, y = to_window_pixels(current, report(), step["x"], step["y"], client_area(hwnd))
                args = {"action": "click", "x": x, "y": y}
            elif step["do"] == "key":
                args = {"action": "key", "key": step["keys"]}
            else:
                args = {"action": "hold", "key": step["key"], "seconds": step["seconds"]}
            if stop.is_set() or over():
                return end("cancelled" if stop.is_set() else "blocked", "durduruldu" if stop.is_set() else "süre doldu",
                           item)
            sample = report()
            action_seq = int((sample or {}).get("seq") or 0)
            if step["do"] == "hold":
                call(_hold, backend, current, step["key"], step["seconds"], stop, budget=call_seconds + step["seconds"])
            else:
                call(backend.act, current, before, args)
            out["actions"] += 1
            pointer = cursor()
            if stop.wait(settle):
                return end("cancelled", "durduruldu", item)
            if alive():
                try:
                    item["after"] = shot(call(backend.observe, fresh_target()), f"adim-{number:02d}-sonra.png")
                except _GaveUp:
                    raise
                except Exception:
                    item["after"] = ""
            if program_error(report()):
                return end("failed", "program bu adımda hata verdi", item)
            item["ok"] = True
        except _GaveUp as gave:
            return end(gave.state, gave.reason, item)
        except PermissionError as exc:
            if stop.is_set():
                return end("cancelled", "durduruldu", item)
            return end("blocked", f"SpeS adımı güvenli bulmadı: {str(exc)[:160]}", item)
        except ValueError as exc:
            return end("failed", f"adım uygulanamadı: {str(exc)[:160]}", item)
        except Exception as exc:
            if not alive():
                return end("crashed", "program kapandı", item)
            return end("blocked", f"girdi verilemedi ({type(exc).__name__})", item)
    if not alive():
        return end("crashed", "program son adımdan sonra kapandı")
    return finish(out)


def finish(out: dict) -> dict:
    """Fides I1: every asked expectation must be measured for a pass; an unmeasured one makes the
    whole run "unproven", and input without any expectation is only "smoke"."""
    if out.get("unmeasured"):
        out.update(state="unproven", reason=f"{out['unmeasured']} beklenen ölçülemedi")
    elif not out.get("asserted"):
        out.update(state="smoke", reason="hiçbir beklenen ölçülmedi")
    else:
        out["state"] = "passed"
    return out


_NAMES = {"click_text": "tıkla (metin)", "click_at": "tıkla (nokta)", "key": "tuş", "hold": "basılı tut",
          "wait": "bekle", "expect": "beklenen"}


def step_lines(result: dict) -> list:
    """Per step, for the reviewer: what SpeS did, the outcome and the images in its folder."""
    lines = []
    for s in (result or {}).get("steps") or []:
        mark = {True: "geçti", False: "GEÇMEDİ", None: "ölçülemedi"}[s.get("ok")]
        images = ", ".join(x for x in (s.get("before"), s.get("after")) if x)
        lines.append(f"  {s['n']}. {_NAMES.get(s['do'], s['do'])}: {mark}"
                     + (f" — {s['note']}" if s.get("note") and s.get("ok") is not None else "")
                     + (f" [görülen: {'; '.join(s['seen'])[:300]}]" if s.get("seen") else "")
                     + (f" ({images})" if images else ""))
    if result and result.get("error"):
        lines.append("Programın verdiği hata (veri):\n" + str(result["error"])[-800:])
    return lines


def summary(result: dict | None) -> str:
    """One line for the finish report and the reviewer: actions and assertions counted apart."""
    if not result:
        return ""
    state = result.get("state")
    steps = result.get("steps") or []
    counts = (f"{result.get('actions', 0)} girdi gönderildi, {result.get('asserted', 0)} beklenen ölçüldü"
              + (f", {result['unmeasured']} beklenen ölçülemedi" if result.get("unmeasured") else ""))
    if state == "passed":
        return f"Etkileşim: SpeS programı içinde denedi — {counts}, hepsi tuttu (sonda ölçümü)."
    if state == "smoke":
        return f"Etkileşim: SpeS programı içinde denedi — {counts}; yalnız duman testi, işlev ölçülmedi."
    if state == "unproven":
        return f"Etkileşim kanıtlanamadı: SpeS programı içinde denedi — {counts}; ölçülemeyen beklenen var."
    last = steps[-1]["n"] if steps else 0
    label = {"failed": "geçmedi", "crashed": "program kapandı", "blocked": "denenemedi",
             "cancelled": "durduruldu"}.get(state, state)
    return f"Etkileşim {label}: adım {last} — {result.get('reason') or ''} ({counts})."
