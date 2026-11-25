"""Piper voice for SpeS Mobil (22 Nov 2026): local worker, WAV over the gateway, fallback when absent."""
import json
import queue
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import mobile_server
from core.piper_speech import MAX_CHARS, PiperSpeech, clean_for_speech, voice_root
from tests.test_mobile_server import FakeAssistant, FakeChat

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt "


def install(root: Path):
    (root / "piper-venv" / "Scripts").mkdir(parents=True)
    (root / "piper-venv" / "Scripts" / "python.exe").write_bytes(b"")
    (root / "models").mkdir()
    (root / "models" / "tr_TR-dfki-medium.onnx").write_bytes(b"")
    (root / "models" / "tr_TR-dfki-medium.onnx.json").write_text("{}")


class FakeStdout:
    def __init__(self):
        self.lines = queue.Queue()

    def readline(self):
        return self.lines.get()


class FakeStdin:
    def __init__(self, proc):
        self.proc, self.buffer = proc, b""

    def write(self, data):
        if self.proc.dead:
            raise OSError("broken pipe")
        self.buffer += data

    def flush(self):
        line, self.buffer = self.buffer, b""
        job = json.loads(line)
        self.proc.jobs.append(job["text"])
        Path(job["out"]).write_bytes(WAV + job["text"].encode())
        self.proc.stdout.lines.put(b'{"ok": true}\n')

    def close(self):
        self.proc.dead = True
        self.proc.stdout.lines.put(b"")


class FakeProc:
    def __init__(self):
        self.stdout, self.jobs, self.dead = FakeStdout(), [], False
        self.stdin = FakeStdin(self)
        self.stdout.lines.put(b'{"ready": true}\n')

    def poll(self):
        return 0 if self.dead else None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.dead = True


class FakePopen:
    def __init__(self):
        self.procs, self.argv = [], []

    def __call__(self, argv, **kwargs):
        self.argv.append(argv)
        self.procs.append(FakeProc())
        return self.procs[-1]


class CleanTextTests(unittest.TestCase):
    def test_markdown_links_and_code_are_not_read_aloud(self):
        text = clean_for_speech("**Bitti.** Bkz. https://x.dev/a ```print(1)``` `kod` # Başlık")
        self.assertEqual(text, "Bitti. Bkz. bağlantı kod Başlık")

    def test_long_text_is_cut_at_a_sentence(self):
        text = clean_for_speech("Bir cümle burada. " * 200)
        self.assertLessEqual(len(text), MAX_CHARS)
        self.assertTrue(text.endswith("."))

    def test_voice_lives_under_local_app_data(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": r"C:\Veri", "SPES_PIPER_DIR": ""}):
            self.assertEqual(voice_root(), Path(r"C:\Veri") / "Quartz" / "voice")


class PiperSpeechTests(unittest.TestCase):
    def test_not_installed_is_a_lookup_error_and_starts_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            popen = FakePopen()
            speech = PiperSpeech(root=directory, popen=popen)
            self.assertFalse(speech.available())
            with self.assertRaises(LookupError):
                speech.synthesize("Merhaba")
            self.assertEqual(popen.procs, [])

    def test_one_worker_keeps_the_model_loaded_for_every_sentence(self):
        with tempfile.TemporaryDirectory() as directory:
            install(Path(directory))
            popen = FakePopen()
            speech = PiperSpeech(root=directory, popen=popen)
            self.assertTrue(speech.available())
            self.assertEqual(speech.synthesize("Merhaba, ben **SpeS**."), WAV + "Merhaba, ben SpeS .".encode())
            self.assertTrue(speech.synthesize("İkinci cümle.").startswith(WAV))
            self.assertEqual(len(popen.procs), 1)
            self.assertEqual(popen.procs[0].jobs, ["Merhaba, ben SpeS .", "İkinci cümle."])
            argv = popen.argv[0]
            self.assertEqual(argv[1:3], ["-I", "-c"], "Piper runs isolated, as its own program")
            self.assertTrue(argv[-1].endswith("tr_TR-dfki-medium.onnx"))
            speech.close()
            self.assertTrue(popen.procs[0].dead)

    def test_a_dead_worker_is_restarted_once(self):
        with tempfile.TemporaryDirectory() as directory:
            install(Path(directory))
            popen = FakePopen()
            speech = PiperSpeech(root=directory, popen=popen)
            speech.synthesize("Bir.")
            popen.procs[0].dead = True
            self.assertTrue(speech.synthesize("İki.").startswith(WAV))
            self.assertEqual(len(popen.procs), 2)
            speech.close()

    def test_empty_text_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            install(Path(directory))
            with self.assertRaises(ValueError):
                PiperSpeech(root=directory, popen=FakePopen()).synthesize(" ``` ``` ")


class FakeSpeech:
    def __init__(self, installed=True):
        self.installed, self.texts, self.closed = installed, [], False

    def available(self):
        return self.installed

    def synthesize(self, text):
        if not self.installed:
            raise LookupError("Piper bu bilgisayarda kurulu değil")
        self.texts.append(text)
        return WAV

    def close(self):
        self.closed = True


class SpeechEndpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.patch = patch.object(mobile_server, "ACCESS_FILE", Path(self.directory.name) / "access.json")
        self.patch.start()
        self.gateway = mobile_server.MobileGateway(FakeAssistant(), port=0, agent_chat=lambda: FakeChat())
        self.gateway._speech = self.speech = FakeSpeech()
        threading.Thread(target=self.gateway.start, daemon=True).start()
        deadline = time.time() + 3
        while self.gateway._server is None and time.time() < deadline:
            time.sleep(.01)
        self.port = self.gateway._server.server_address[1]

    def tearDown(self):
        self.gateway.stop()
        self.patch.stop()
        self.directory.cleanup()

    def post(self, payload, token=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/speech", data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + (self.gateway.token if token is None else token),
                     "Content-Type": "application/json"})
        return urllib.request.urlopen(request, timeout=3)

    def test_the_phone_gets_wav_audio_for_its_text(self):
        with self.post({"text": "Fides: testler geçti."}) as response:
            self.assertEqual(response.headers["Content-Type"], "audio/wav")
            self.assertEqual(response.read(), WAV)
        self.assertEqual(self.speech.texts, ["Fides: testler geçti."])

    def test_speech_needs_the_device_key(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post({"text": "Merhaba"}, token="yanlis")
        self.assertEqual(error.exception.code, 401)
        error.exception.close()
        self.assertEqual(self.speech.texts, [])

    def test_without_piper_the_phone_is_told_to_use_its_own_voice(self):
        self.speech.installed = False
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post({"text": "Merhaba"})
        self.assertEqual(error.exception.code, 503)
        error.exception.close()

    def test_ping_says_whether_the_desktop_can_speak(self):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/ping",
                                         headers={"Authorization": "Bearer " + self.gateway.token})
        with urllib.request.urlopen(request, timeout=3) as response:
            body = json.loads(response.read())
        self.assertEqual((body["api"], body["speech"]), (6, True))

    def test_stopping_the_gateway_closes_piper(self):
        self.gateway.stop()
        self.assertTrue(self.speech.closed)


@unittest.skipUnless(PiperSpeech().available(), "Piper is not installed on this computer")
class RealPiperTests(unittest.TestCase):
    def test_real_piper_speaks_turkish(self):
        speech = PiperSpeech()
        try:
            audio = speech.synthesize("Merhaba, ben SpeS.")
        finally:
            speech.close()
        self.assertEqual(audio[:4], b"RIFF")
        self.assertGreater(len(audio), 20_000)


if __name__ == "__main__":
    unittest.main()
