import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from core.warband_workspace import WarbandWorkspace, SaveGuard, safe_path, digest, KEYS
from tests import test_natural_desktop as natural_tests


class WarbandWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.project=self.root/"project"; self.project.mkdir()
        self.saves=self.root/"saves"; self.saves.mkdir()
        self.game=self.root/"game"; (self.game/"Modules/AI_Island_Test").mkdir(parents=True)
        (self.game/"Modules/AI_Island_Test/scripts.txt").write_text("scripts")
        self.workspace=WarbandWorkspace(self.root/"evidence",root=self.project,game=self.game,saves=self.saves,config=self.root/"config")
        (self.project/"parley_guide.py").write_bytes(b"value = 1\r\n")

    def tearDown(self):
        self.workspace.shutdown(); self.temp.cleanup()

    def test_source_requires_grant_and_does_not_grant_play(self):
        with self.assertRaises(PermissionError): self.workspace.source()
        self.workspace.grant(["inspect"])
        row=self.workspace.source("read","parley_guide.py")
        self.assertEqual(row["untrusted_source_lines"],[(1,"value = 1")])
        with self.assertRaises(PermissionError): self.workspace.launch()

    def test_paths_and_protected_file_edit_are_rejected(self):
        self.workspace.grant(["develop"])
        (self.project/"build.ps1").write_text("protected")
        for value in ("../outside.py",str(self.root/"outside.py")):
            with self.assertRaises(PermissionError): safe_path(self.project,value)
        with self.assertRaises(PermissionError): self.workspace.source("replace","build.ps1",old="protected",new="changed")
        self.assertEqual((self.project/"build.ps1").read_text(),"protected")

    def test_write_checkpoint_hash_and_official_syntax_gate(self):
        self.workspace.grant(["develop"])
        path=self.project/"parley_guide.py"; sha=digest(path)
        with self.assertRaises(PermissionError): self.workspace.source("replace",path.name,old="value = 1",new="value = 2",sha256=sha)
        self.workspace.prepared={"source_hashes":{}}
        with patch.object(self.workspace,"_preflight"),patch.object(self.workspace,"_backup",return_value={"verified":True}) as backup,patch.object(self.workspace,"_command"):
            with self.assertRaises(ValueError): self.workspace.source("replace",path.name,old="value = 1",new="value = 2",sha256="stale")
            backup.assert_not_called()
            result=self.workspace.source("replace",path.name,old="value = 1",new="value = 2",sha256=sha)
            self.assertEqual(path.read_bytes(),b"value = 2\r\n")
            self.assertEqual(result["level"],"SOURCE CHANGED; NOT BUILT/LIVE")
            backup.assert_called_once()
            diff=self.workspace.source("changes")["changes"][0]["untrusted_diff"]
            self.assertIn("-value = 1",diff);self.assertIn("+value = 2",diff)

    def test_failed_checkpoint_never_writes(self):
        self.workspace.grant(["develop"]); self.workspace.prepared={}
        self.workspace.prepared={"at":1}
        path=self.project/"parley_guide.py"
        with patch.object(self.workspace,"_preflight"),patch.object(self.workspace,"_backup",side_effect=RuntimeError("UM backup failed")):
            with self.assertRaises(RuntimeError): self.workspace.source("replace",path.name,old="value = 1",new="value = 2",sha256=digest(path))
        self.assertEqual(path.read_bytes(),b"value = 1\r\n")

    def test_game_inputs_need_owned_fresh_one_use_snapshot(self):
        self.workspace.grant(["play"])
        with self.assertRaises(PermissionError): self.workspace.act("fake","key",key="enter")
        self.workspace.snapshot={"id":"s","at":time.time()-16}
        with self.assertRaises(PermissionError): self.workspace.act("s","key",key="enter")
        self.assertIsNone(self.workspace.snapshot)
        self.assertNotIn("f12",KEYS)

    def test_observation_cannot_bypass_operator_lease_or_resume_paused_scope(self):
        self.workspace.grant(["play"])
        with patch.object(self.workspace,"_target",return_value=(Mock(),{})),patch.object(self.workspace,"_um") as um:
            with self.assertRaisesRegex(PermissionError,"initial focus"):self.workspace.observe()
            um.assert_not_called()
        lease=Mock();self.workspace.input_lease=lease;self.workspace.focused=True
        self.workspace.snapshot={"id":"old","at":time.time()}
        self.workspace.pause_input()
        lease.close.assert_called_once()
        with self.assertRaises(PermissionError):self.workspace.require("play")
        self.assertIsNone(self.workspace.snapshot)

    def test_failed_official_build_restores_only_exact_module_snapshot(self):
        self.workspace.grant(["develop"]);self.workspace.prepared={"at":1}
        archive=self.root/"checkpoint"/"build.zip"
        with patch.object(self.workspace,"_preflight"),patch.object(self.workspace,"_backup",return_value={"archive":str(archive)}),\
             patch.object(self.workspace,"_command",side_effect=RuntimeError("compiler failed")),\
             patch.object(self.workspace,"_um",return_value={"log":"rollback.log"}) as restore:
            with self.assertRaisesRegex(RuntimeError,"pre-build module restored"): self.workspace._run("build")
            args=restore.call_args.args
            self.assertIn("restore",args);self.assertNotIn("--clean",args)
            self.assertIn(self.game/"Modules/AI_Island_Test",args)
            self.assertIn(archive,args)

    def test_log_evidence_is_scoped_not_model_success(self):
        self.workspace.grant(["inspect"])
        self.workspace.snapshot={"id":"s","at":time.time(),"log":{"untrusted_log":["BP return restoreErrors=0"]},"image_sha256":"h","image":"game.png"}
        result=self.workspace.verify("s","restoreErrors=0")
        self.assertEqual(result["status"],"RGL CRITERION VERIFIED")
        self.assertIn("not whole Gate B",result["scope"])
        self.assertEqual(self.workspace.verify("s","success")["status"],"NOT VERIFIED")

    def test_launcher_never_changes_module_or_uses_stale_selection(self):
        self.workspace.grant(["play"])
        target={"handle":1,"pid":2,"started":3,"exe":"game","rect":[0,0,640,480]}
        state={"can_start":True,"selected_modules":["AI_Island_Test"],"play_rect":None,"module_rect":[100,10,400,50]}
        def snapshot():self.workspace.snapshot={"id":"s","at":time.time(),"target":target,"width":640,"height":480,"launcher":state}
        with patch.object(self.workspace,"_target",return_value=(Mock(),target)),\
             patch.object(self.workspace,"_launcher_state",return_value=state),\
             patch.object(self.workspace,"_geometry",return_value=((0,0,640,480),[])),\
             patch.object(self.workspace,"_drive") as drive:
            snapshot()
            with self.assertRaises(PermissionError):self.workspace.start_game("s",200,25)
            drive.assert_not_called();self.assertIsNone(self.workspace.snapshot)
            snapshot();self.workspace.snapshot["launcher"]={"can_start":False,"selected_modules":["Native"]}
            with self.assertRaises(PermissionError):self.workspace.start_game("s",150,130)
            drive.assert_not_called()

    @unittest.skipUnless(os.name=="nt","Windows sharing contract")
    def test_real_file_sharing_guard_allows_read_denies_overwrite_and_rename(self):
        path=self.saves/"sg08.sav"; path.write_bytes(b"original-save")
        guard=SaveGuard(self.saves)
        try:
            guard.acquire()
            self.assertEqual(path.read_bytes(),b"original-save")
            with self.assertRaises(OSError): path.open("wb")
            with self.assertRaises(OSError): path.rename(self.saves/"replaced.sav")
            self.assertTrue(guard.verify()["unchanged"])
            self.assertTrue(guard.intact())
        finally: guard.close()
        self.assertEqual(path.read_bytes(),b"original-save")


class WarbandNaturalTests(unittest.TestCase):
    call=natural_tests.NaturalTaskTests.call
    tearDown=natural_tests.NaturalTaskTests.tearDown
    def setUp(self):
        natural_tests.NaturalTaskTests.setUp(self)
        self.task.warband=WarbandWorkspace(self.task.evidence,root=self.root,game=self.root,saves=self.root,config=self.root/"config")

    def test_warband_inline_consent_and_reviewer_write_denial(self):
        self.call("warband_request_access",{"capabilities":["inspect","develop"],"reason":"Kaynak kusurunu incele ve düzelt"})
        self.assertEqual(self.task.pending["kind"],"warband")
        self.assertEqual(self.task.warband.capabilities,set())
        self.task.approve(self.task.pending["id"],confirmed=True)
        self.assertIn("develop",self.task.warband.capabilities)
        with self.assertRaises(PermissionError): self.call("warband_run",{"operation":"build"},"review")
        with self.assertRaises(PermissionError): self.call("warband_request_access",{"capabilities":["play"],"reason":"input"},"review")
        self.assertFalse(self.broker.status()["active"])

    def test_generic_session_never_exposes_warband_capability(self):
        self.task.warband=None
        with self.assertRaises(PermissionError): self.call("warband_run",{"operation":"launch"})

    def test_explicit_warband_operator_precedes_later_screen_mentions(self):
        roles=natural_tests.task_roles("Codex, bilgisayar kontrolünü al ve Warband testini yap. Gemini, logları ve ekran kanıtını incele.")
        self.assertEqual(roles["operator"],"codex")
        roles=natural_tests.task_roles("Codex, ekran kanıtlarını incele. Gemini, bilgisayar kontrolünü al ve oyunu aç.")
        self.assertEqual(roles["operator"],"antigravity")
