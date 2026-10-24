import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.desktop_broker import DesktopBroker
from core.desktop_launch import describe_launch, validate_launch
from core.desktop_mcp import operator_tool_allowed
from core.desktop_native import NativeDesktopBackend
from tests.test_desktop_broker import FakeBackend


class MultiBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.items = {h: {**copy.deepcopy(self.target), "handle":h, "pid":40+h, "title":str(h)} for h in (1,2,3)}
        self.fg = 0
    def identity(self, handle): return copy.deepcopy(self.items[handle])
    def windows(self): return list(copy.deepcopy(self.items).values())
    def focus(self, target): self.fg = target["handle"]
    def is_foreground(self, target): return self.fg == target["handle"]
    def act(self, target, observation, args): self.actions.append((target["handle"],dict(args)))


class MultiWindowTests(unittest.TestCase):
    def setUp(self):
        self.backend=MultiBackend(); self.now=0
        self.broker=DesktopBroker(self.backend,clock=lambda:self.now)
        self.token=self.broker.grant([1,2],"codex",confirmed=True)["token"]
    def tearDown(self): self.broker.close()
    def call(self,name,**args): return self.broker.call(self.token,{"name":name,"arguments":args})
    def test_a_b_a_and_snapshot_binding(self):
        a=self.call("desktop_focus"); b=self.call("desktop_switch",handle=2)
        with self.assertRaises(PermissionError): self.call("desktop_act",snapshot_id=a["snapshot_id"],action="key",key="tab")
        b=self.call("desktop_observe")
        self.call("desktop_act",snapshot_id=b["snapshot_id"],action="key",key="tab")
        self.assertEqual(self.backend.actions[0][0],2)
        self.assertEqual(self.call("desktop_switch",handle=1)["target"]["handle"],1)
    def test_unapproved_c_no_focus_or_input(self):
        self.call("desktop_focus")
        with self.assertRaises(PermissionError): self.call("desktop_switch",handle=3)
        self.assertEqual(self.backend.fg,1); self.assertFalse(self.backend.actions)
        self.assertEqual([w["handle"] for w in self.call("desktop_windows")["targets"]],[1,2])
    def test_new_hwnd_same_process_not_adopted(self):
        self.backend.items[4]={**self.backend.items[2],"handle":4}
        with self.assertRaises(PermissionError): self.call("desktop_switch",handle=4)
    def test_destination_reuse_is_not_title_trusted(self):
        self.call("desktop_focus"); self.backend.items[2]["started"]+=1
        self.assertEqual(len(self.call("desktop_windows")["targets"]),1)
        with self.assertRaises(PermissionError): self.call("desktop_switch",handle=2)
        self.assertEqual(self.backend.fg,1)
    def test_closed_current_revokes_and_releases(self):
        self.call("desktop_focus"); del self.backend.items[1]
        with self.assertRaises(PermissionError): self.call("desktop_observe")
        self.assertFalse(self.broker.status()["active"]); self.assertTrue(self.backend.leases[-1].closed)
    def test_closed_destination_does_not_steal_focus(self):
        self.call("desktop_focus"); del self.backend.items[2]
        with self.assertRaises(KeyError): self.call("desktop_switch",handle=2)
        self.assertEqual(self.backend.fg,1); self.assertFalse(self.backend.actions)
    def test_external_focus_even_on_approved_window_revokes(self):
        self.call("desktop_focus"); self.backend.fg=2
        with self.assertRaises(PermissionError): self.call("desktop_switch",handle=1)
        self.assertFalse(self.broker.status()["active"])
    def test_failed_activation_revokes(self):
        self.call("desktop_focus")
        with patch.object(self.backend,"focus"):
            with self.assertRaises(PermissionError): self.call("desktop_switch",handle=2)
        self.assertFalse(self.broker.status()["active"]); self.assertFalse(self.backend.actions)
    def test_stop_old_capability_cannot_control_new_task(self):
        self.broker.stop(); new=self.broker.grant(3,"antigravity",confirmed=True)
        with self.assertRaises(PermissionError): self.call("desktop_switch",handle=3)
        self.assertTrue(self.broker.status()["active"])
        self.assertNotEqual(new["token"],self.token)
    def test_expiry_releases_all_windows(self):
        self.now=601
        with self.assertRaises(PermissionError): self.call("desktop_windows")
        self.assertTrue(self.backend.leases[-1].closed)
    def test_grant_checks_proposal_identity_before_lease(self):
        self.broker.stop(); expected=self.backend.windows(); self.backend.items[2]["pid"]+=1
        with self.assertRaises(PermissionError): self.broker.grant([1,2],"codex",confirmed=True,expected_targets=expected)
        self.assertFalse(self.broker.status()["active"])
    def test_empty_duplicate_or_large_set_denied(self):
        self.broker.stop()
        for handles in ([],[1,1],list(range(13))):
            with self.assertRaises(ValueError): self.broker.grant(handles,"codex",confirmed=True)
    def test_unapproved_launch_never_runs(self):
        with patch("core.desktop_launch.launch_approved") as launch:
            with self.assertRaises(PermissionError): self.call("desktop_launch",app_id="not-approved")
            launch.assert_not_called()


class LaunchTests(unittest.TestCase):
    def test_last_moment_native_guard_checks_all_identity_and_geometry(self):
        backend=NativeDesktopBackend();target=MultiBackend().items[1]
        for field in ("handle","pid","started","exe","rect"):
            current={**copy.deepcopy(target),field:"changed"}
            with patch.object(backend,"validate_input_session"),patch.object(backend,"identity",return_value=current),patch.object(backend,"is_foreground",return_value=True):
                with self.subTest(field=field),self.assertRaises(PermissionError):backend._before_input(target)
    def test_operator_hook_rejects_other_tools_and_integrations(self):
        self.assertTrue(operator_tool_allowed({"tool_name":"mcp_quartz-desktop_desktop_switch"}))
        self.assertTrue(operator_tool_allowed({"tool_name":"call_mcp_tool","tool_input":{"ServerName":"quartz-desktop","ToolName":"desktop_switch"}}))
        self.assertTrue(operator_tool_allowed({"toolCall":{"name":"call_mcp_tool","args":{"ServerName":"quartz-desktop","ToolName":"desktop_windows"}}}))
        self.assertFalse(operator_tool_allowed({"toolCall":{"name":"run_command","args":{"CommandLine":"anything"}}}))
        self.assertFalse(operator_tool_allowed({"tool_name":"call_mcp_tool","tool_input":{"ServerName":"other","ToolName":"desktop_switch"}}))
        for name in ("run_command","read_file","desktop_switch","mcp_other_desktop_switch","mcp_quartz-desktop_shell"):
            self.assertFalse(operator_tool_allowed({"tool_name":name}))
        self.assertFalse(operator_tool_allowed(None))
    def test_executable_hash_identity_and_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            exe=Path(directory)/"harmless.exe"; exe.write_bytes(b"MZfixture")
            item=describe_launch(exe); self.assertEqual(validate_launch(item),item)
            with self.assertRaises(PermissionError): validate_launch({**item,"args":["unapproved"]})
            exe.write_bytes(b"MZchanged")
            with self.assertRaises(PermissionError): validate_launch(item)
    def test_interpreters_scripts_and_warband_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("cmd.exe","wscript.exe","node.exe","python.exe","mb_warband.exe","script.js"):
                exe=Path(directory)/name;exe.write_bytes(b"MZtest")
                with self.subTest(name=name),self.assertRaises(PermissionError): describe_launch(exe)
    def test_launch_once_even_if_result_is_uncertain(self):
        backend=MultiBackend(); broker=DesktopBroker(backend)
        try:
            with tempfile.TemporaryDirectory() as directory:
                exe=Path(directory)/"harmless.exe";exe.write_bytes(b"MZfixture"); item=describe_launch(exe)
                token=broker.grant([1,2],"codex",confirmed=True,launches=[item])["token"]
                with patch("core.desktop_launch.launch_approved",side_effect=RuntimeError("no unique HWND")) as launch:
                    with self.assertRaises(RuntimeError): broker.call(token,{"name":"desktop_launch","arguments":{"app_id":item["id"]}})
                    with self.assertRaises(PermissionError): broker.call(token,{"name":"desktop_launch","arguments":{"app_id":item["id"]}})
                    self.assertEqual(launch.call_count,1)
        finally: broker.close()
