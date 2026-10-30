import copy
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from core.desktop_broker import DesktopBroker
from core.desktop_mcp import handle, TOOLS
from core.desktop_native import NativeDesktopBackend


class FakeBackend:
    def __init__(self):
        self.target = {"handle": 1, "pid": 42, "started": 100, "exe": "test.exe", "title": "Test", "rect": [0, 0, 800, 600]}
        self.foreground = False
        self.actions = []
        self.leases = []
    def identity(self, _): return copy.deepcopy(self.target)
    def validate_target(self, target): pass
    def validate_input_session(self): pass
    def acquire_lease(self):
        lease = io.BytesIO(); self.leases.append(lease); return lease
    def is_foreground(self, _): return self.foreground
    def focus(self, _): self.foreground = True
    def observe(self, _): return {"ui": {"elements": []}, "image_base64": "cG5n", "width": 800, "height": 600}
    def act(self, _, observation, args): self.actions.append(dict(args))
    def windows(self): return [copy.deepcopy(self.target)]


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend(); self.now = 0
        self.broker = DesktopBroker(self.backend, clock=lambda: self.now)
    def tearDown(self): self.broker.close()
    def grant(self):
        self.connection = self.broker.grant(1, "codex", confirmed=True)
        return self.connection["token"]
    def focus(self):
        token = self.grant()
        return token, self.broker.call(token, {"name": "desktop_focus"})
    def act(self, token, snapshot):
        return self.broker.call(token, {"name": "desktop_act", "arguments": {"snapshot_id": snapshot, "action": "key", "key": "tab"}})
    def test_requires_strict_confirmation_and_one_operator(self):
        for confirmation in (None, False, "true", 1):
            with self.assertRaises(PermissionError): self.broker.grant(1, "codex", confirmed=confirmation)
        with self.assertRaises(ValueError): self.broker.grant(1, "both", confirmed=True)
        self.grant()
        with self.assertRaises(RuntimeError): self.broker.grant(1, "antigravity", confirmed=True)
    def test_action_has_fresh_observation_but_does_not_claim_goal(self):
        token, first = self.focus()
        second = self.act(token, first["snapshot_id"])
        self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertFalse(second["goal_verified"])
        self.assertEqual(len(self.backend.actions), 1)
    def test_bad_and_expired_snapshots_are_consumed(self):
        token, first = self.focus()
        with self.assertRaises(PermissionError): self.act(token, "wrong")
        with self.assertRaises(PermissionError): self.act(token, first["snapshot_id"])
        fresh = self.broker.call(token, {"name": "desktop_observe"})
        self.now = 16
        with self.assertRaises(PermissionError): self.act(token, fresh["snapshot_id"])
        self.assertEqual(self.backend.actions, [])
    def test_no_action_before_focus(self):
        token = self.grant()
        observation = self.broker.call(token, {"name": "desktop_observe"})
        with self.assertRaises(PermissionError): self.act(token, observation["snapshot_id"])
    def test_unavailable_input_desktop_prevents_grant(self):
        self.backend.validate_input_session = MagicMock(side_effect=PermissionError("desktop unavailable"))
        with self.assertRaises(PermissionError): self.grant()
        self.assertFalse(self.broker.status()["active"])
        self.assertEqual(self.backend.leases, [])
    def test_foreground_takeover_revokes_grant(self):
        token, first = self.focus(); self.backend.foreground = False
        with self.assertRaises(PermissionError): self.act(token, first["snapshot_id"])
        self.assertFalse(self.broker.status()["active"])
        self.assertTrue(self.backend.leases[0].closed)

    def test_persistent_focus_recovery_refreshes_without_replaying_input(self):
        token = self.broker.grant(1, "codex", confirmed=True, persistent_control=True)["token"]
        first = self.broker.call(token, {"name": "desktop_focus"})
        self.backend.foreground = False
        self.assertTrue(self.broker.status()["active"])
        refreshed = self.act(token, first["snapshot_id"])
        self.assertTrue(refreshed["action_skipped"])
        self.assertTrue(refreshed["focus_recovered"])
        self.assertEqual(self.backend.actions, [])
        self.assertNotEqual(first["snapshot_id"], refreshed["snapshot_id"])
        self.act(token, refreshed["snapshot_id"])
        self.assertEqual(len(self.backend.actions), 1)

    def test_failed_recovery_is_bounded_and_keeps_task_without_input(self):
        token = self.broker.grant(1, "codex", confirmed=True, persistent_control=True)["token"]
        first = self.broker.call(token, {"name": "desktop_focus"})
        self.backend.foreground = False
        self.backend.focus = MagicMock()
        with self.assertRaises(PermissionError): self.act(token, first["snapshot_id"])
        self.backend.focus.assert_called_once()
        self.assertEqual(self.backend.actions, [])
        self.assertTrue(self.broker.status()["active"])
        self.assertIsNone(self.broker._session["snapshot"])

    def test_recovery_cannot_cross_locked_session_or_replaced_window(self):
        token = self.broker.grant(1, "codex", confirmed=True, persistent_control=True)["token"]
        first = self.broker.call(token, {"name": "desktop_focus"})
        self.backend.foreground = False
        self.backend.focus = MagicMock()
        self.backend.validate_input_session = MagicMock(side_effect=PermissionError("locked"))
        with self.assertRaises(PermissionError): self.act(token, first["snapshot_id"])
        self.backend.focus.assert_not_called()
        self.backend.target["pid"] += 1
        with self.assertRaises(PermissionError): self.broker.call(token, {"name": "desktop_observe"})
        self.assertFalse(self.broker.status()["active"])

    def test_stop_never_recovers_focus(self):
        token = self.broker.grant(1, "codex", confirmed=True, persistent_control=True)["token"]
        self.broker.stop()
        self.backend.focus = MagicMock()
        with self.assertRaises(PermissionError): self.broker.call(token, {"name": "desktop_observe"})
        self.backend.focus.assert_not_called()
    def test_pid_or_start_time_reuse_revokes(self):
        for field in ("pid", "started", "exe"):
            token, first = self.focus()
            self.backend.target[field] = str(self.backend.target[field]) + "changed"
            with self.assertRaises(PermissionError): self.act(token, first["snapshot_id"])
            self.assertFalse(self.broker.status()["active"])
    def test_window_move_invalidates_previous_geometry(self):
        token, first = self.focus(); self.backend.target["rect"][0] += 10
        with self.assertRaises(PermissionError): self.act(token, first["snapshot_id"])
        self.assertEqual(self.backend.actions, [])
    def test_title_change_is_not_process_replacement(self):
        token, first = self.focus(); self.backend.target["title"] = "*Edited Test"
        self.act(token, first["snapshot_id"])
        self.assertTrue(self.broker.status()["active"])
    def test_stop_and_expiry_revoke_tokens(self):
        token = self.grant(); self.broker.stop()
        with self.assertRaises(PermissionError): self.broker.call(token, {"name": "desktop_observe"})
        token = self.grant(); self.now = 601
        with self.assertRaises(PermissionError): self.broker.call(token, {"name": "desktop_observe"})
        self.assertTrue(self.backend.leases[-1].closed)
    def test_no_second_automatic_focus(self):
        token, _ = self.focus()
        with self.assertRaises(PermissionError): self.broker.call(token, {"name": "desktop_focus"})
    def test_action_error_consumes_snapshot(self):
        token, first = self.focus()
        self.backend.act = MagicMock(side_effect=ValueError("not executed"))
        with self.assertRaises(ValueError): self.act(token, first["snapshot_id"])
        with self.assertRaises(PermissionError): self.act(token, first["snapshot_id"])
    def test_http_auth_and_no_secrets_in_status_or_audit(self):
        token = self.grant()
        req = urllib.request.Request(self.connection["url"], data=b'{"name":"desktop_observe"}', headers={"Authorization": "Bearer wrong"})
        with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(req)
        req.add_header("Authorization", "Bearer " + token)
        with urllib.request.urlopen(req) as response: self.assertIn("snapshot_id", json.load(response))
        self.assertNotIn(token, json.dumps(self.broker.status()))
        self.assertNotIn(token, json.dumps(self.broker.audit))
    def test_same_process_holds_one_lease_only(self):
        self.grant(); self.broker.stop(); self.grant()
        self.assertTrue(self.backend.leases[0].closed)
        self.assertFalse(self.backend.leases[1].closed)


class MCPTests(unittest.TestCase):
    def test_stdio_is_utf8_even_if_windows_parent_requests_cp1254(self):
        request = {"jsonrpc": "2.0", "id": "işlem-漢字", "method": "initialize"}
        env = os.environ.copy(); env["PYTHONIOENCODING"] = "cp1254"
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "core/desktop_mcp.py")],
                                input=(json.dumps(request, ensure_ascii=False)+"\n").encode("utf-8"),
                                capture_output=True, env=env, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.decode("utf-8"))["id"], request["id"])
    def test_action_schema_is_flat_and_strict_client_compatible(self):
        schema = next(tool["inputSchema"] for tool in TOOLS if tool["name"] == "desktop_act")
        self.assertNotIn("anyOf", schema)
        self.assertEqual(set(schema["properties"]), set(schema["required"]))
        self.assertFalse(schema["additionalProperties"])
        for name, definition in schema["properties"].items():
            if name not in {"snapshot_id", "action"}: self.assertIn("null", definition["type"])
    def test_tools_and_initialize(self):
        names={tool["name"] for tool in handle({"method": "tools/list"})["tools"]}
        self.assertTrue({"desktop_focus","desktop_observe","desktop_act","desktop_windows","desktop_switch","desktop_launch"} <= names)
        self.assertTrue({"desktop_request_access","task_context","task_wait","task_message","task_read_log","desktop_verify"} <= names)
        self.assertIn("protocolVersion", handle({"method": "initialize"}))
    def test_real_image_content_is_separate_from_text(self):
        result = handle({"method": "tools/call", "params": {"name": "desktop_observe"}},
                        lambda _: {"observation": {"image_base64": "PNG", "width": 800}})
        self.assertEqual(result["content"][1], {"type": "image", "data": "PNG", "mimeType": "image/png"})
        self.assertNotIn("image_base64", result["content"][0]["text"])
    def test_only_broker_action_reference_is_exposed_to_agent(self):
        original = {"snapshot_id": "broker-reference", "observation": {
            "ui": {"snapshot_id": "internal-uia-reference", "note": "internal instructions", "elements": [{"ref": "1"}]}}}
        result = handle({"method": "tools/call", "params": {"name": "desktop_observe"}}, lambda _: original)
        text = result["content"][0]["text"]
        parsed = json.loads(text)
        self.assertEqual(parsed["snapshot_id"], "broker-reference")
        self.assertNotIn("internal-uia-reference", text)
        self.assertEqual(parsed["observation"]["ui"]["elements"], [{"ref": "1"}])
        self.assertEqual(original["observation"]["ui"]["snapshot_id"], "internal-uia-reference")
    def test_tool_error_is_not_success(self):
        result = handle({"method": "tools/call", "params": {"name": "desktop_act"}}, lambda _: {"error": "denied"})
        self.assertTrue(result["isError"])
    def test_sidecar_without_parent_has_no_authority(self):
        with patch.dict("os.environ", {}, clear=True):
            result = handle({"method": "tools/call", "params": {"name": "desktop_observe"}})
        self.assertTrue(result["isError"])
    def test_unknown_tool_cannot_reach_broker(self):
        transport = MagicMock()
        with self.assertRaises(ValueError): handle({"method": "tools/call", "params": {"name": "shell"}}, transport)
        transport.assert_not_called()


class NativePolicyTests(unittest.TestCase):
    def test_foreground_requires_active_input_desktop_and_exact_window(self):
        backend = NativeDesktopBackend()
        user32 = MagicMock()
        target = {"handle": 12, "pid": 42}
        with patch.object(backend, "_user32", return_value=user32), \
             patch.object(backend, "_input_desktop_matches", return_value=False):
            user32.GetForegroundWindow.return_value = 12
            self.assertFalse(backend.is_foreground(target))
        with patch.object(backend, "_user32", return_value=user32), \
             patch.object(backend, "_input_desktop_matches", return_value=True):
            user32.GetForegroundWindow.return_value = 0
            self.assertFalse(backend.is_foreground(target))
            user32.GetForegroundWindow.return_value = 99
            user32.GetAncestor.return_value = 0
            self.assertFalse(backend.is_foreground(target))
            user32.GetForegroundWindow.return_value = 12
            self.assertTrue(backend.is_foreground(target))

    def test_capture_rejects_desktop_change_after_image_grab(self):
        from PIL import Image
        backend = NativeDesktopBackend()
        target = {"handle": 12, "rect": [0, 0, 100, 80]}
        window = MagicMock()
        window.descendants.return_value = []
        @contextmanager
        def scope(): yield MagicMock()
        with patch.object(backend.controller, "_desktop", scope), \
             patch.object(backend.controller, "_window", return_value=window), \
             patch.object(backend.controller, "inspect", return_value={"elements": []}), \
             patch.object(backend, "_safe_controls"), \
             patch.object(backend, "_input_desktop_matches", return_value=True), \
             patch.object(backend, "is_foreground", side_effect=[True, False]), \
             patch("PIL.ImageGrab.grab", return_value=Image.new("RGB", (100, 80))):
            with self.assertRaisesRegex(PermissionError, "changed during capture"):
                backend.observe(target)

    def run_mock_click(self, *, name="TEST BUTTON", password=False, covered=False, lost=False):
        backend = NativeDesktopBackend()
        desktop = MagicMock()
        @contextmanager
        def scope(): yield desktop
        user32 = MagicMock()
        user32.GetAncestor.return_value = 2 if covered else 1
        mouse = MagicMock()
        def late_guard(_):
            if not backend.is_foreground({}): raise PermissionError("Target lost foreground before click")
        with patch.object(backend.controller, "_desktop", scope), \
             patch.object(backend, "is_foreground", side_effect=[True, not lost]), \
             patch.object(backend, "_safe_controls"), \
             patch.object(backend, "_before_input", side_effect=late_guard), \
             patch.object(backend, "_user32", return_value=user32), \
             patch.object(backend.controller, "_describe", return_value={"name": name, "password": password}), \
             patch.dict("sys.modules", {"pyautogui": mouse}):
            try:
                backend.act({"handle": 1, "rect": [100, 200, 900, 800]},
                            {"width": 800, "height": 600, "image_base64": "png"},
                            {"action": "click", "x": 23, "y": 24})
                return mouse, None
            except PermissionError as exc:
                return mouse, exc

    def test_pixel_click_keeps_window_relative_geometry(self):
        mouse, error = self.run_mock_click()
        self.assertIsNone(error)
        mouse.click.assert_called_once_with(123, 224)

    def test_pixel_click_blocks_consequential_and_private_targets(self):
        for kwargs in ({"name": "Delete"}, {"password": True}, {"name": "Sign in"}):
            with self.subTest(kwargs=kwargs):
                mouse, error = self.run_mock_click(**kwargs)
                self.assertIsInstance(error, PermissionError)
                mouse.click.assert_not_called()

    def test_pixel_click_blocks_occlusion_and_late_focus_loss(self):
        for kwargs in ({"covered": True}, {"lost": True}):
            with self.subTest(kwargs=kwargs):
                mouse, error = self.run_mock_click(**kwargs)
                self.assertIsInstance(error, PermissionError)
                mouse.click.assert_not_called()

    def test_pixel_click_rejects_mismatched_capture_geometry(self):
        backend = NativeDesktopBackend()
        mouse = MagicMock()
        with patch.object(backend, "is_foreground", return_value=True), \
             patch.object(backend, "_safe_controls"), \
             patch.dict("sys.modules", {"pyautogui": mouse}):
            with self.assertRaisesRegex(PermissionError, "different geometry"):
                backend.act({"handle": 1, "rect": [100, 200, 900, 800]},
                            {"width": 799, "height": 600, "image_base64": "png"},
                            {"action": "click", "x": 23, "y": 24})
        mouse.click.assert_not_called()

    def test_native_action_keeps_one_outer_apartment_during_safety_scan(self):
        backend = NativeDesktopBackend()
        depth = []
        @contextmanager
        def scope():
            depth.append(True)
            try: yield MagicMock()
            finally: depth.pop()
        def safety(_): self.assertEqual(len(depth), 1)
        with patch.object(backend.controller, "_desktop", scope), \
             patch.object(backend, "is_foreground", return_value=True), \
             patch.object(backend, "_safe_controls", side_effect=safety):
            with self.assertRaises(ValueError):
                backend.act({}, {}, {"action": "unsupported"})
        self.assertEqual(depth, [])
    def test_focus_waits_for_acknowledgement_without_repeating_request(self):
        backend = NativeDesktopBackend()
        window = MagicMock()
        desktop = MagicMock()
        @contextmanager
        def desktop_scope(): yield desktop
        with patch.object(backend.controller, "_desktop", desktop_scope), \
             patch.object(backend.controller, "_window", return_value=window), \
             patch.object(backend, "is_foreground", side_effect=[False, False, True]), \
             patch("core.desktop_native.time.sleep") as sleep:
            backend.focus({"handle": 1})
        window.set_focus.assert_called_once()
        self.assertEqual(sleep.call_count, 2)
    def test_protected_apps_and_warband_are_not_generic_targets(self):
        for exe in ("powershell.exe", "cmd.exe", "regedit.exe", "consent.exe", "mb_warband.exe", "Quartz.exe", "codex-computer-use.exe"):
            with self.subTest(exe=exe), self.assertRaises(PermissionError):
                NativeDesktopBackend.validate_target({"exe": exe, "title": "normal"})
    def test_password_dialog_is_denied_even_for_allowed_process(self):
        with self.assertRaises(PermissionError): NativeDesktopBackend.validate_target({"exe": "app.exe", "title": "Enter password"})
    def test_normal_app_is_allowed(self):
        NativeDesktopBackend.validate_target({"exe": "notepad.exe", "title": "Untitled - Notepad"})
