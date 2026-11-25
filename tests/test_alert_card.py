"""Eos's alert cards (25 Nov): short paths, expired alerts say so, the result shows on the card."""
import subprocess
import unittest

import gui


def _function(name, until):
    html = gui._HTML
    start = html.index(f"  function {name}(")
    return html[start:html.index(until, start)]


class AlertCardTests(unittest.TestCase):
    def run_js(self, script):
        code = _function("shortenWindowsPaths", "  function appendMessageText(") + script
        result = subprocess.run(["node", "-"], input=code, capture_output=True, text=True,
                                encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_long_temp_paths_keep_the_program_name_visible(self):
        out = self.run_js(r"""
console.log(shortenWindowsPaths(String.raw`DismHost.exe (PID 1) şuradan başladı: C:\Users\U\AppData\Local\Temp\A3C8DB23\DismHost.exe`));
console.log(shortenWindowsPaths(String.raw`C:\Users\U\AppData\Local\Temp\p5ee\resources\app\ServiceHub\Services\VS.Setup\BackgroundDownload.exe`));
console.log(shortenWindowsPaths(String.raw`C:\x\y.exe kısa`));
""")
        self.assertEqual(out[0], r"DismHost.exe (PID 1) şuradan başladı: …\Temp\A3C8DB23\DismHost.exe")
        self.assertEqual(out[1], r"…\Services\VS.Setup\BackgroundDownload.exe")
        self.assertEqual(out[2], r"C:\x\y.exe kısa", "short paths stay as they are")

    def test_an_expired_alert_offers_no_buttons_and_results_show_on_the_card(self):
        html = gui._HTML
        self.assertIn("Number(alert.expires) * 1000 < Date.now()", html)
        self.assertIn("'Bu uyarının süresi doldu; işlem artık yapılamaz.'", html)
        self.assertIn("note.textContent = action === 'ignore' ? 'Yoksayıldı.' : said;", html)
        self.assertIn("body.title = view.summary;", html)


if __name__ == "__main__":
    unittest.main()
