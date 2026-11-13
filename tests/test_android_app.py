"""SpeS Android app: static guarantees that do not need the Android toolchain."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "app"
SOURCES = APP / "src" / "main" / "java" / "app" / "spes" / "mobile"


class AndroidAppTests(unittest.TestCase):
    def test_manifest_is_https_only_and_keeps_the_key_out_of_backups(self):
        manifest = (APP / "src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android:usesCleartextTraffic="false"', manifest)
        self.assertIn('android:allowBackup="false"', manifest)
        self.assertIn('android:foregroundServiceType="remoteMessaging"', manifest)
        # Only the alert, service and boot hooks; no exported components beyond launcher and boot.
        self.assertEqual(manifest.count('android:exported="true"'), 2)

    def test_device_key_travels_only_in_the_authorization_header(self):
        api = (SOURCES / "SpesApi.kt").read_text(encoding="utf-8")
        self.assertIn('setRequestProperty("Authorization", "Bearer $token")', api)
        self.assertNotRegex(api, r"[?&]token=")
        self.assertIn("Yalnız https adresi kullanılır", api)

    def test_phone_never_sends_write_permissions(self):
        for path in SOURCES.glob("*.kt"):
            text = path.read_text(encoding="utf-8")
            for flag in ("confirm_write", "full_access", "permission_level"):
                self.assertNotIn(flag, text, path.name)

    def test_release_key_is_not_in_the_repository(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("*.apk", "*.jks", "android/app/build/"):
            self.assertIn(pattern, ignored)
        gradle = (APP / "build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn('System.getenv("SPES_KEYSTORE")', gradle)
        self.assertNotRegex(gradle, r'storePassword\s*=\s*"')

    def test_launcher_icon_uses_the_brand_geometry(self):
        from scripts.build_brand_assets import TAIL, facets
        icon = (APP / "src/main/res/drawable/ic_launcher_foreground.xml").read_text(encoding="utf-8")
        for polygon in [*facets(), TAIL]:
            first = f"M{polygon[0][0]:.2f},{polygon[0][1]:.2f}"
            self.assertIn(first, icon)

    def test_voice_mode_uses_android_speech_and_stays_read_only(self):
        manifest = (APP / "src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn("android.permission.RECORD_AUDIO", manifest)
        self.assertIn('android:name=".VoiceActivity"', manifest)
        voice = (SOURCES / "VoiceActivity.kt").read_text(encoding="utf-8")
        commands = (SOURCES / "VoiceCommands.kt").read_text(encoding="utf-8")
        self.assertIn("SpeechRecognizer", voice)
        self.assertIn("TextToSpeech", voice)
        self.assertIn('"dur"', commands)
        self.assertIn("TEKNIK_AYRINTILAR", commands)  # technical details are never read aloud
        # The phone never holds the NVIDIA key or calls NVIDIA; the desktop does (/api/voice).
        for name in ("nvidia", "nvapi", "openai", "integrate.api"):
            self.assertNotIn(name, voice.lower())
        self.assertIn('"/api/voice"', (SOURCES / "SpesApi.kt").read_text(encoding="utf-8"))

    def test_stop_silences_and_does_not_listen_again(self):
        voice = (SOURCES / "VoiceActivity.kt").read_text(encoding="utf-8")
        stop = voice[voice.index("private fun stopEverything"):voice.index("private fun ask")]
        for needed in ("tts?.stop()", "recognizer?.cancel()", "generation++", "api.stop()", "listenAfter = false"):
            self.assertIn(needed, stop)
        self.assertNotIn("Başka bir şey var mı", voice)

    def test_personas_match_the_desktop(self):
        theme = (SOURCES / "Theme.kt").read_text(encoding="utf-8")
        import mobile_server
        for name in set(mobile_server.PERSONA.values()):
            self.assertIn(f'"{name}" ->', theme)
        self.assertTrue(re.search(r"accent = Color\(0xFF8FCFB0\)", theme))


if __name__ == "__main__":
    unittest.main()
