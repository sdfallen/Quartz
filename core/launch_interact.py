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
    if not _number(at) or (since is not None and at < since) or time.time() - at > PROBE_FRESH_SECONDS:
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
    """Fides D2: a hold that Stop and a lost foreground end at once; the key is always released."""
    import pyautogui
    pyautogui.FAILSAFE = False
    backend._before_input(target)
    pyautogui.keyDown(key)
    try:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if stop.is_set():
                raise PermissionError("Durduruldu; tuş bırakıldı")
            if not backend.is_foreground(target):
                raise PermissionError("Pencere öndeki yerini kaybetti; tuş bırakıldı")
            time.sleep(.02)
    finally:
        pyautogui.keyUp(key)


def run(backend, hwnd, steps, stop, *, report_path, review_dir, alive, pid=None, max_seconds=MAX_SECONDS,
        settle=SETTLE_SECONDS, client_area=None, cursor=None) -> dict:
    """Run validated steps in the proved window; always returns a receipt, never raises."""
    client_area = client_area or _client_area
    cursor = cursor or _cursor
    review = Path(review_dir)
    review.mkdir(parents=True, exist_ok=True)
    results, began = [], time.monotonic()
    out = {"state": "passed", "steps": results, "reason": "", "instrumented": True,
           "actions": 0, "asserted": 0, "unmeasured": 0}

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
    try:
        target = backend.identity(hwnd)
        backend.validate_target(target)
        backend.focus(target)
        if not backend.is_foreground(target):
            return end("blocked", "pencere öne getirilemedi")
        baseline = report()
        known_errors = int((baseline or {}).get("error_count") or 0)
    except Exception as exc:
        return end("blocked", f"pencere hazırlanamadı ({type(exc).__name__})")
    pointer = cursor()
    for number, step in enumerate(steps, 1):
        item = {"n": number, "do": step["do"], "ok": None, "note": ""}
        results.append(item)
        if stop.is_set():
            return end("cancelled", "durduruldu", item)
        if time.monotonic() - began > max_seconds:
            return end("blocked", "süre doldu", item)
        if not alive():
            return end("crashed", "program kapandı", item)
        now = cursor()
        if pointer and now and max(abs(now[0] - pointer[0]), abs(now[1] - pointer[1])) > POINTER_SLACK:
            # Fides Q4: someone else is using the mouse; SpeS stops and never takes focus back.
            return end("blocked", "fare SpeS dışında hareket etti; deneme durdu", item)
        try:
            if step["do"] == "wait":
                if stop.wait(step["seconds"]):
                    return end("cancelled", "durduruldu", item)
                item["ok"] = True
                continue
            if step["do"] == "expect":
                deadline = time.monotonic() + EXPECT_SECONDS
                while True:
                    current = report()
                    if current is None or current.get("kind") != "tk":
                        item.update(ok=None, note="ölçülemedi (yalnız tkinter, taze sonda raporu yok)")
                        out["unmeasured"] += 1
                        break
                    texts = [" ".join(str(w.get("text", "")).split()) for w in current.get("widgets", [])]
                    hit = any((step["text"] in t) if step["contains"] else (t == step["text"]) for t in texts)
                    if hit:
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
            # D1: the broker's fences, here — input session, identity, foreground, a fresh
            # observation taken right before this one action and used once.
            backend.validate_input_session()
            current = backend.identity(hwnd)
            if not backend.is_foreground(current):
                return end("blocked", "pencere öndeki yerini kaybetti", item)
            before = backend.observe(current)
            if not before.get("image_base64"):
                return end("blocked", "pencere görüntüsü alınamadı", item)
            item["before"] = shot(before, f"adim-{number:02d}-once.png")
            if stop.is_set():
                return end("cancelled", "durduruldu", item)
            backend.input_cancelled = stop.is_set
            if step["do"] == "click_text":
                current_report = read_report(report_path, pid=pid)
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
                backend.act(current, before, {"action": "click", "x": x, "y": y})
            elif step["do"] == "click_at":
                x, y = to_window_pixels(current, read_report(report_path, pid=pid),
                                        step["x"], step["y"], client_area(hwnd))
                backend.act(current, before, {"action": "click", "x": x, "y": y})
            elif step["do"] == "key":
                backend.act(current, before, {"action": "key", "key": step["keys"]})
            elif step["do"] == "hold":
                _hold(backend, current, step["key"], step["seconds"], stop)
            out["actions"] += 1
            pointer = cursor()
            if stop.wait(settle):
                return end("cancelled", "durduruldu", item)
            if alive():
                try:
                    item["after"] = shot(backend.observe(backend.identity(hwnd)), f"adim-{number:02d}-sonra.png")
                except Exception:
                    item["after"] = ""
            item["ok"] = True
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
        latest = report() or {}
        if int(latest.get("error_count") or 0) > known_errors:
            out["error"] = str((latest.get("errors") or [""])[-1])[-1200:]
            return end("failed", "program bu adımda hata verdi", item)
    if not alive():
        return end("crashed", "program son adımdan sonra kapandı")
    if not out["asserted"]:
        # Fides Q2: input without one measured expectation is a smoke test, not acceptance.
        out.update(state="smoke", reason="hiçbir beklenen ölçülmedi")
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
    last = steps[-1]["n"] if steps else 0
    label = {"failed": "geçmedi", "crashed": "program kapandı", "blocked": "denenemedi",
             "cancelled": "durduruldu"}.get(state, state)
    return f"Etkileşim {label}: adım {last} — {result.get('reason') or ''} ({counts})."
