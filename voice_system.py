"""
voice_system.py  —  Quartz Voice I/O
Push-to-talk speech-to-text, always-on wake-word
listening ("hey quartz"), and text-to-speech.
Used by gui.py — the backend (main.py/assistant.py)
is untouched; voice just feeds transcribed text into
the same IPC "chat" action typed messages already use.

Notes / trade-offs (worth knowing):
  - STT uses Google's free Web Speech API via the
    `speech_recognition` package. No API key needed,
    but it sends short audio clips to Google's servers
    over the internet — not fully offline/private.
  - Wake-word detection works by continuously
    transcribing short phrases and checking for
    "quartz" in the text. This is simple and free, but
    has a noticeable delay (roughly 1-2s) compared to a
    dedicated offline wake-word engine like Picovoice
    Porcupine. Good enough for personal use; can be
    swapped later if snappier detection is wanted.
  - TTS uses pyttsx3 (fully offline, no API key).
"""

import re
import threading
import time

from logger import get_logger
from config import VOICE_LANGUAGE, VOICE_TTS_RATE

log = get_logger(__name__)

try:
    import speech_recognition as sr
except ImportError:
    sr = None
    log.warning(
        "speech_recognition not installed — "
        "voice input disabled. "
        "pip install SpeechRecognition pyaudio")

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None
    log.warning(
        "pyttsx3 not installed — "
        "voice output disabled. pip install pyttsx3")

WAKE_WORDS = ("hey quartz", "hi quartz", "hello quartz", "quartz")
_MAX_SPEAK_CHARS = 600  # keep TTS replies from droning on


class VoiceSystem:

    def __init__(self):
        self._recognizer = None
        self._mic = None
        self._mic_available = False
        self._stop_wake_fn = None
        self._wake_active = False

        self._tts_engine = None
        self._tts_lock = threading.Lock()
        self._tts_enabled = True

        if sr is not None:
            try:
                self._recognizer = sr.Recognizer()
                self._recognizer.pause_threshold = 0.8
                self._mic = sr.Microphone()
                with self._mic as source:
                    self._recognizer.adjust_for_ambient_noise(
                        source, duration=0.6)
                self._mic_available = True
                log.info("Microphone ready")
            except Exception as exc:
                log.warning(
                    "Microphone init failed: %s", exc)

        if pyttsx3 is not None:
            try:
                self._tts_engine = pyttsx3.init()
                self._tts_engine.setProperty(
                    "rate", VOICE_TTS_RATE)
            except Exception as exc:
                log.warning("TTS init failed: %s", exc)
                self._tts_engine = None

    # ── Status ────────────────────────────────────────────

    @property
    def mic_available(self) -> bool:
        return self._mic_available

    @property
    def tts_available(self) -> bool:
        return self._tts_engine is not None

    @property
    def wake_active(self) -> bool:
        return self._wake_active

    def set_tts_enabled(self, enabled: bool):
        self._tts_enabled = enabled
        if not enabled:
            self.stop_speaking()

    # ── Push-to-talk (blocking; call from a bg thread) ────

    def listen_once(self, timeout=6,
                     phrase_time_limit=15) -> str:
        if not self._mic_available:
            return ""
        try:
            with self._mic as source:
                audio = self._recognizer.listen(
                    source, timeout=timeout,
                    phrase_time_limit=phrase_time_limit)
            return self._transcribe(audio)
        except sr.WaitTimeoutError:
            return ""
        except Exception as exc:
            log.warning("listen_once error: %s", exc)
            return ""

    def _transcribe(self, audio) -> str:
        try:
            return self._recognizer.recognize_google(
                audio, language=VOICE_LANGUAGE).strip()
        except sr.UnknownValueError:
            return ""
        except Exception as exc:
            log.warning("STT error: %s", exc)
            return ""

    # ── Wake-word loop ────────────────────────────────────

    def start_wake_loop(self, on_wake, on_command):
        """
        on_wake()          fired the instant a wake word is heard
        on_command(text)   fired with whatever followed the wake
                            word in the same utterance (may be '')
        Both run on the background listener thread — the
        caller (gui.py) is responsible for hopping back onto
        the UI thread (e.g. via webview evaluate_js, which is
        thread-safe to call directly).
        """
        if not self._mic_available or self._wake_active:
            return False

        def callback(recognizer, audio):
            if not self._wake_active:
                return
            text = self._transcribe(audio)
            if not text:
                return
            low = text.lower()
            hit = next(
                (w for w in WAKE_WORDS if w in low), None)
            if not hit:
                return
            log.info("Wake word detected: %s", text[:80])
            try:
                on_wake()
            except Exception:
                log.exception("on_wake callback failed")
            remainder = low.split(hit, 1)[-1].strip(" ,.!?")
            try:
                on_command(remainder)
            except Exception:
                log.exception("on_command callback failed")

        self._stop_wake_fn = self._recognizer.listen_in_background(
            self._mic, callback, phrase_time_limit=6)
        self._wake_active = True
        log.info("Wake-word loop started")
        return True

    def stop_wake_loop(self):
        self._wake_active = False
        if self._stop_wake_fn:
            self._stop_wake_fn(wait_for_stop=False)
            self._stop_wake_fn = None
        log.info("Wake-word loop stopped")

    # ── Text to speech ────────────────────────────────────

    def speak(self, text: str):
        if not self._tts_engine or not text or not self._tts_enabled:
            return
        clean = re.sub(r"[*_`#]", "", text)[:_MAX_SPEAK_CHARS]

        def run():
            with self._tts_lock:
                try:
                    self._tts_engine.say(clean)
                    self._tts_engine.runAndWait()
                except Exception as exc:
                    log.warning("TTS speak error: %s", exc)

        threading.Thread(target=run, daemon=True).start()

    def stop_speaking(self):
        if self._tts_engine:
            try:
                self._tts_engine.stop()
            except Exception:
                pass
