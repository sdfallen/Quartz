"""Piper voice for SpeS Mobil (user request 22 Nov 2026).

The phone's voice mode used to read every reply with Android's own voice. When Piper is
installed on this computer, the desktop turns the text into speech and the phone plays it.

Piper runs as a separate program from its own environment (it is GPL; SpeS never imports it):
  %LOCALAPPDATA%\\Quartz\\voice\\piper-venv   Python environment with the piper-tts package
  %LOCALAPPDATA%\\Quartz\\voice\\models       the voice model (tr_TR-dfki-medium.onnx + .json)

One worker process keeps the model loaded (loading takes about 2 s, a sentence about 0.5 s).
Nothing is sent anywhere: the text goes to the local worker and the audio comes back as WAV.
The Turkish voice is CC BY-NC-SA 4.0: personal use only, never bundled into a SpeS package.
"""

import json
import os
import queue
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from logger import get_logger

log = get_logger(__name__)

MAX_CHARS = 1200        # a spoken reply, not a document
REPLY_TIMEOUT = 45      # seconds for one synthesis (the first one also loads the model)
DEFAULT_VOICE = "tr_TR-dfki-medium"

# Runs inside Piper's own environment. Reads one JSON line per request, writes the WAV
# file it was given, answers with one JSON line.
_WORKER = r"""
import json, sys, wave
from piper import PiperVoice
voice = PiperVoice.load(sys.argv[1])
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    try:
        job = json.loads(line)
        with wave.open(job["out"], "wb") as out:
            voice.synthesize_wav(job["text"], out)
        print(json.dumps({"ok": True}), flush=True)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}), flush=True)
"""


def voice_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(os.environ.get("SPES_PIPER_DIR") or Path(base) / "Quartz" / "voice")


def clean_for_speech(text: str) -> str:
    """Speakable plain text: no markdown marks, links or code fences; bounded length."""
    text = re.sub(r"```.*?```", " ", str(text or ""), flags=re.S)
    text = re.sub(r"https?://\S+", "bağlantı", text)
    text = re.sub(r"[`*_#>|~\[\]]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_CHARS:
        cut = text[:MAX_CHARS]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[:end + 1] if end > MAX_CHARS // 2 else cut
    return text


class PiperSpeech:
    def __init__(self, root=None, voice=DEFAULT_VOICE, popen=subprocess.Popen):
        self.root = Path(root) if root else voice_root()
        self.voice = voice
        self._popen = popen
        self._lock = threading.Lock()
        self._proc = None
        self._lines = None

    @property
    def python(self) -> Path:
        return self.root / "piper-venv" / "Scripts" / "python.exe"

    @property
    def model(self) -> Path:
        return self.root / "models" / f"{self.voice}.onnx"

    def available(self) -> bool:
        return (self.python.is_file() and self.model.is_file()
                and Path(str(self.model) + ".json").is_file())

    def _start(self):
        self._proc = self._popen(
            [str(self.python), "-I", "-c", _WORKER, str(self.model)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=str(self.root), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        lines = queue.Queue()
        stdout = self._proc.stdout

        def pump():
            for raw in iter(stdout.readline, b""):
                lines.put(raw)
            lines.put(None)
        threading.Thread(target=pump, name="piper-reader", daemon=True).start()
        self._lines = lines
        if not self._reply().get("ready"):
            raise RuntimeError("Piper başlatılamadı")

    def _reply(self) -> dict:
        try:
            raw = self._lines.get(timeout=REPLY_TIMEOUT)
        except queue.Empty:
            raise RuntimeError("Piper yanıt vermedi") from None
        if raw is None:
            raise RuntimeError("Piper kapandı")
        return json.loads(raw.decode("utf-8", "replace"))

    def synthesize(self, text: str) -> bytes:
        """WAV bytes for the text. LookupError when Piper is not installed."""
        text = clean_for_speech(text)
        if not text:
            raise ValueError("Okunacak metin yok")
        if not self.available():
            raise LookupError("Piper bu bilgisayarda kurulu değil")
        with self._lock:
            handle, out = tempfile.mkstemp(prefix="spes-piper-", suffix=".wav")
            os.close(handle)
            try:
                for attempt in (1, 2):  # one restart if the worker died in between
                    try:
                        if self._proc is None or self._proc.poll() is not None:
                            self._start()
                        self._proc.stdin.write((json.dumps({"text": text, "out": out}) + "\n").encode("ascii"))
                        self._proc.stdin.flush()
                        reply = self._reply()
                        break
                    except (OSError, RuntimeError, ValueError):
                        self._kill()
                        if attempt == 2:
                            raise RuntimeError("Piper sesi üretemedi") from None
                if not reply.get("ok"):
                    raise RuntimeError("Piper sesi üretemedi")
                return Path(out).read_bytes()
            finally:
                try:
                    os.unlink(out)
                except OSError:
                    pass

    def _kill(self):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def close(self):
        with self._lock:
            self._kill()
