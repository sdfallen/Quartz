"""App preview pane: loopback-only addresses, bridge-free preview window, markup."""
import http.server
import re
import socket
import threading
import unittest
from unittest.mock import patch

import gui
from core.preview_url import PreviewUrlError, frame_policy, normalize_preview_url
from ui.app_js import APPLICATION_JS, SCRIPT_PARTS
from ui.js_preview import JAVASCRIPT as PREVIEW_JS
from ui.shell import SHELL_MARKUP


class PreviewUrlTests(unittest.TestCase):
    def test_loopback_addresses_are_normalised(self):
        cases = {
            "http://127.0.0.1:8000": "http://127.0.0.1:8000/",
            "127.0.0.1:8000/docs": "http://127.0.0.1:8000/docs",
            "localhost:5173": "http://localhost:5173/",
            ":3000": "http://localhost:3000/",
            "HTTP://LocalHost:8080/a?b=1#c": "http://localhost:8080/a?b=1#c",
            "https://app.localhost/x": "https://app.localhost/x",
            "http://[::1]:9000/": "http://[::1]:9000/",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_preview_url(raw), expected)

    def test_non_local_or_unsafe_addresses_are_refused(self):
        for raw in ("https://example.com", "http://192.168.1.5:8000", "http://127.0.0.2:8000",
                    "file:///C:/Windows/win.ini", "javascript:alert(1)", "data:text/html,x",
                    "http://user:pw@localhost:8000/", "http://localhost.evil.com/",
                    "http://localhost:99999/", "http://local host/", "", "   ",
                    "http://localhost/" + "a" * 3000, None, 8000):
            with self.subTest(raw=raw):
                with self.assertRaises(PreviewUrlError):
                    normalize_preview_url(raw)


class _Handler(http.server.BaseHTTPRequestHandler):
    ROUTES = {
        "/open": (200, {}),
        "/xfo": (200, {"X-Frame-Options": "DENY"}),
        "/same": (200, {"X-Frame-Options": "SAMEORIGIN"}),
        "/csp": (200, {"Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'"}),
        "/csp-any": (200, {"Content-Security-Policy": "frame-ancestors *"}),
        "/missing": (404, {}),
        "/to-local": (303, {"Location": "/xfo"}),
        "/to-remote": (302, {"Location": "https://example.com/"}),
        "/loop": (302, {"Location": "/loop"}),
    }

    def do_GET(self):
        self.server.paths.append(self.path)
        code, headers = self.ROUTES.get(self.path, (200, {}))
        self.send_response(code)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


class FramePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.paths = []
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_headers_decide_whether_the_pane_can_frame_the_app(self):
        expected = {"/open": "allowed", "/xfo": "blocked", "/same": "blocked", "/csp": "blocked",
                    "/csp-any": "allowed", "/missing": "allowed", "/to-local": "blocked",
                    "/to-remote": "allowed", "/loop": "allowed"}
        for path, policy in expected.items():
            with self.subTest(path=path):
                self.assertEqual(frame_policy(self.base + path), policy)

    def test_redirects_never_leave_loopback_and_are_bounded(self):
        self.server.paths.clear()
        frame_policy(self.base + "/loop")
        self.assertEqual(self.server.paths, ["/loop"] * 4)

    def test_closed_port_is_unreachable(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.assertEqual(frame_policy(f"http://127.0.0.1:{port}/", timeout=1), "unreachable")

    def test_probe_refuses_non_loopback_input(self):
        with self.assertRaises(PreviewUrlError):
            frame_policy("https://example.com/")


class PreviewApiTests(unittest.TestCase):
    def test_check_url_reports_errors_without_raising(self):
        api = gui.Api.__new__(gui.Api)
        self.assertEqual(api.preview_check_url("127.0.0.1:8000")["status"], "ok")
        self.assertEqual(api.preview_check_url("https://example.com")["status"], "error")

    def test_preview_window_has_no_js_bridge(self):
        api = gui.Api.__new__(gui.Api)
        with patch.object(gui.webview, "create_window") as create:
            result = api.preview_open_window("localhost:8000/panel")
        self.assertEqual(result, {"status": "ok", "data": "http://localhost:8000/panel"})
        create.assert_called_once()
        self.assertEqual(create.call_args.kwargs["url"], "http://localhost:8000/panel")
        self.assertNotIn("js_api", create.call_args.kwargs)
        self.assertNotIn("html", create.call_args.kwargs)

    def test_refused_address_opens_no_window(self):
        api = gui.Api.__new__(gui.Api)
        with patch.object(gui.webview, "create_window") as create:
            result = api.preview_open_window("https://example.com")
        self.assertEqual(result["status"], "error")
        create.assert_not_called()


class PreviewMarkupTests(unittest.TestCase):
    def test_pane_and_rail_button_are_shipped(self):
        for element_id in ("btnPreview", "previewPane", "previewBar", "previewAddress", "previewFrame",
                           "btnPreviewReload", "btnPreviewWindow", "btnPreviewClose", "previewNote"):
            self.assertEqual(SHELL_MARKUP.count(f'id="{element_id}"'), 1, element_id)
        self.assertNotIn("@@i:", SHELL_MARKUP)
        self.assertIn(PREVIEW_JS, SCRIPT_PARTS)
        self.assertIn("window.QuartzPreview", APPLICATION_JS)

    def test_frame_sandbox_cannot_navigate_or_escape_quartz(self):
        sandbox = re.search(r'id="previewFrame"[^>]*sandbox="([^"]+)"', SHELL_MARKUP).group(1).split()
        for token in ("allow-top-navigation", "allow-top-navigation-by-user-activation",
                      "allow-popups-to-escape-sandbox", "allow-popups"):
            self.assertNotIn(token, sandbox)

    def test_script_uses_python_check_and_refuses_own_origin(self):
        self.assertIn("preview_check_url", PREVIEW_JS)
        self.assertIn("location.origin", PREVIEW_JS)
        self.assertNotIn("innerHTML", PREVIEW_JS)

    def test_new_bridge_methods_exist(self):
        for name in ("preview_check_url", "preview_frame_policy", "preview_open_window"):
            self.assertTrue(callable(getattr(gui.Api, name, None)), name)

    def test_reply_links_stop_at_escaped_newlines_and_skip_remote_hosts(self):
        import json
        import subprocess
        start = PREVIEW_JS.index("  const PREVIEW_LINK_RE")
        regex = PREVIEW_JS[start:PREVIEW_JS.index("\n", start)]
        links = PREVIEW_JS[PREVIEW_JS.index("  function localPreviewLinks"):PREVIEW_JS.index("  // Adds \"Önizle\"")]
        sample = ("Duman: http://localhost:18431/login\\r\\nalembic.ini\\napp ve http://127.0.0.1:8000/docs. "
                  "Dış https://example.com ve http://localhost:18431/login tekrar")
        script = regex + "\n" + links + f"\nconsole.log(JSON.stringify(localPreviewLinks({json.dumps(sample)})));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["http://localhost:18431/login", "http://127.0.0.1:8000/docs"])


if __name__ == "__main__":
    unittest.main()
