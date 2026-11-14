"""The work panel shows what the team built and what the user sent (14 Nov 2026)."""
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from tests.test_team_turn import make_chat


class WorkPanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.project = base / "kafe"
        (self.project / "css").mkdir(parents=True)
        (self.project / "index.html").write_text("<h1>Kafe Lavanta</h1>", encoding="utf-8")
        (self.project / "css" / "style.css").write_text("h1{color:purple}", encoding="utf-8")
        (self.project / "README.md").write_text("# Kafe", encoding="utf-8")
        (self.project / "gizli.txt").write_text("sonuçlarda yok", encoding="utf-8")
        self.env = patch.dict("os.environ", {"QUARTZ_ATTACHMENTS_HOME": str(base / "att")})
        self.env.start()
        self.chat = make_chat(base)
        from core.attachments import AttachmentStore
        self.chat.attachments = AttachmentStore()
        projects = self.chat.agent_service.projects
        projects.get.return_value = {"id": "kafe", "path": str(self.project)}
        projects.selected.return_value = {"id": "kafe", "path": str(self.project)}
        self.cid = self.chat.new_conversation(agent="collaboration", project_id="kafe")["id"]
        self.chat.store.append_message(self.cid, "assistant", "Yazdım.", sender="claude",
                                       metadata={"run_id": "r1", "status": "completed"})
        self.chat.agent_service.run_evidence.side_effect = lambda rid: {
            "files_changed": [str(self.project / "index.html"), str(self.project / "css" / "style.css"),
                              str(self.project / "README.md"), "C:/baska/yer.txt"]} if rid == "r1" else {}

    def tearDown(self):
        self.chat.previews.stop_all()
        self.chat._diagnostics.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_result_opens_the_page_live_on_loopback(self):
        data = self.chat.panel_result(self.cid)
        self.assertEqual(sorted(data["project"]), ["README.md", "css/style.css", "index.html"])  # outside path dropped
        self.assertEqual(data["open"]["kind"], "web")
        url = data["open"]["url"]
        self.assertTrue(url.startswith("http://127.0.0.1:") and url.endswith("/index.html"))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as response:
            self.assertIn(b"Kafe Lavanta", response.read())

    def test_reader_only_opens_listed_files(self):
        self.assertEqual(self.chat.panel_read(self.cid, "project", "README.md")["text"], "# Kafe")
        for bad in ("gizli.txt", "../kafe/README.md", "C:/baska/yer.txt"):
            with self.subTest(bad=bad), self.assertRaises(PermissionError):
                self.chat.panel_read(self.cid, "project", bad)
        with self.assertRaises(ValueError):
            self.chat.panel_read(self.cid, "disk", "README.md")

    def test_attachments_are_listed_and_readable(self):
        self.chat.attachments.add(self.cid, "not.txt", "ek notu".encode())
        batch = self.chat.attachments.take(self.cid)
        self.chat.store.append_message(self.cid, "user", "bak", sender="user",
                                       metadata={"attachments": batch["items"], "attachment_batch": batch["batch"]})
        files = self.chat.panel_files(self.cid)
        self.assertEqual(files["attachments"][0]["name"], "not.txt")
        self.assertEqual(self.chat.panel_read(self.cid, "attachment", "not.txt", batch["batch"])["text"], "ek notu")
        with self.assertRaises(PermissionError):
            self.chat.panel_read(self.cid, "attachment", "not.txt", "baska-batch")

    def test_without_a_page_the_best_file_opens(self):
        self.chat.agent_service.run_evidence.side_effect = lambda rid: {"files_changed": [str(self.project / "README.md")]}
        self.assertEqual(self.chat.panel_result(self.cid)["open"], {"kind": "file", "scope": "project", "path": "README.md"})


if __name__ == "__main__":
    unittest.main()
