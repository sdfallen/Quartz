"""Web / HTML-JS project verification (core.web_check) — 28 Nov 2026."""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core import web_check as wc
from core.long_job import JobError, JobLedger, LongJob, finish_report
from tests.test_long_job_chat import FakeChat


class EntryDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_root_index_html_wins(self):
        (self.root / "index.html").write_text("<h1>Ana</h1>", encoding="utf-8")
        (self.root / "about.html").write_text("<h1>Hakkında</h1>", encoding="utf-8")
        entry, why = wc.detected_web_entry(self.root)
        self.assertEqual((entry.name, why), ("index.html", ""))

    def test_unique_subdir_index_or_unique_root_html_is_detected_and_ambiguity_is_refused(self):
        (self.root / "public").mkdir()
        (self.root / "public" / "index.html").write_text("<h1>Public</h1>", encoding="utf-8")
        entry, why = wc.detected_web_entry(self.root)
        self.assertEqual((entry.relative_to(self.root).as_posix(), why), ("public/index.html", ""))

        (self.root / "dist").mkdir()
        (self.root / "dist" / "index.html").write_text("<h1>Dist</h1>", encoding="utf-8")
        entry2, why2 = wc.detected_web_entry(self.root)
        self.assertIsNone(entry2)
        self.assertIn("belirsiz web giriş sayfası", why2)

    def test_multiple_root_html_without_index_is_ambiguous(self):
        (self.root / "a.html").write_text("<h1>A</h1>", encoding="utf-8")
        (self.root / "b.html").write_text("<h1>B</h1>", encoding="utf-8")
        entry, why = wc.detected_web_entry(self.root)
        self.assertIsNone(entry)
        self.assertIn("belirsiz web giriş sayfası", why)

    def test_wants_web_look_recognises_web_and_ui_milestones(self):
        self.assertTrue(wc.wants_web_look({"title": "Ana sayfa tasarımı", "acceptance": "kartlar ve menü hazır"}))
        self.assertFalse(wc.wants_web_look({"title": "Veri modeli", "acceptance": "birim testler geçiyor"}))


class StaticAndSyntaxCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "site"
        self.project.mkdir()

    def test_missing_local_asset_or_secret_escape_fails_as_broken_page(self):
        (self.project / "index.html").write_text(
            '<!doctype html><html><head><title>Bütçe</title>'
            '<link rel="stylesheet" href="eksik.css">'
            '<script src="https://cdn.example.com/ext.js"></script></head><body>Merhaba</body></html>',
            encoding="utf-8",
        )
        receipt = wc.observe_web(self.project / "index.html", self.project, self.root / "ev1",
                                 threading.Event(), edge_executable=None, node_executable=None)
        self.assertEqual(receipt["verdict"], "broken_page")
        self.assertIn("eksik.css", receipt["output_tail"])

        # Path traversal attempt in asset reference also fails closed.
        (self.project / "index.html").write_text(
            '<!doctype html><html><body><script src="../disari.js"></script></body></html>',
            encoding="utf-8",
        )
        (self.root / "disari.js").write_text("1;", encoding="utf-8")
        receipt2 = wc.observe_web(self.project / "index.html", self.project, self.root / "ev2",
                                  threading.Event(), edge_executable=None, node_executable=None)
        self.assertEqual(receipt2["verdict"], "broken_page")

    def test_javascript_syntax_error_is_caught_when_node_is_present(self):
        node = wc.find_node()
        if not node:
            self.skipTest("Node not installed on this machine")
        (self.project / "app.js").write_text("function bozuk( { return 1; }\n", encoding="utf-8")
        (self.project / "index.html").write_text(
            '<!doctype html><html><head><title>Test</title></head><body><script src="app.js"></script></body></html>',
            encoding="utf-8",
        )
        receipt = wc.observe_web(self.project / "index.html", self.project, self.root / "ev-js",
                                 threading.Event(), edge_executable=None, node_executable=node)
        self.assertEqual(receipt["verdict"], "broken_page")
        self.assertEqual(receipt["termination_reason"], "js_syntax_error")
        self.assertIn("app.js", receipt["output_tail"])

    def test_valid_static_page_passes_without_browser(self):
        (self.project / "style.css").write_text("body { color: #fff; }", encoding="utf-8")
        (self.project / "app.js").write_text("const ok = 42;\n", encoding="utf-8")
        (self.project / "index.html").write_text(
            '<!doctype html><html><head><title>Şafak Panel</title>'
            '<link rel="stylesheet" href="style.css"></head>'
            '<body><h1>Görevler</h1><script src="app.js"></script></body></html>',
            encoding="utf-8",
        )
        receipt = wc.observe_web(self.project / "index.html", self.project, self.root / "ev-ok",
                                 threading.Event(), edge_executable=None)
        self.assertEqual(receipt["verdict"], "static_ok")
        self.assertEqual(receipt["checked_assets"], 2)
        self.assertEqual(receipt["window_title"], "Şafak Panel")


@unittest.skipUnless(os.name == "nt" and wc.find_edge() is not None, "Windows headless Edge")
class HeadlessBrowserRenderTests(unittest.TestCase):
    def test_headless_edge_renders_js_dom_captures_isolated_png_and_blocks_external_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "site"
            site.mkdir()
            (site / "style.css").write_text("body { background: #14213d; color: #fca311; }", encoding="utf-8")
            (site / "app.js").write_text(
                'document.title = "Canlı Bütçe";\n'
                'document.getElementById("out").textContent = "Toplam: 1250 TL";\n',
                encoding="utf-8",
            )
            (site / "index.html").write_text(
                '<!doctype html><html><head><meta charset="utf-8"><title>Başlangıç</title>'
                '<link rel="stylesheet" href="style.css"></head>'
                '<body><h1 id="out">Yükleniyor</h1><script src="app.js"></script></body></html>',
                encoding="utf-8",
            )
            ev = root / "evidence"
            receipt = wc.observe_web(site / "index.html", site, ev, threading.Event())
            self.assertEqual(receipt["verdict"], "page_seen", receipt)
            self.assertEqual(receipt["capture_state"], "captured")
            self.assertEqual(receipt["window_title"], "Canlı Bütçe")
            self.assertGreater(receipt["rendered_text_chars"], 5)
            # Reviewer folder contains ONLY window.png (Fides L5 isolation).
            review_files = [p.name for p in (ev / "denetci").iterdir()]
            self.assertEqual(review_files, ["window.png"])
            self.assertGreater((ev / "denetci" / "window.png").stat().st_size, 500)


class LongJobWebIntegrationTests(unittest.TestCase):
    def test_broken_web_milestone_is_sent_back_to_writer_then_passes_and_open_page_uses_ledger_only(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"QUARTZ_JOBS_HOME": str(Path(tmp) / "jobs")}):
            project = Path(tmp) / "webproj"
            project.mkdir()
            attempts = [0]

            def run_milestone(ledger, milestone, writer, stop):
                attempts[0] += 1
                if attempts[0] == 1:
                    # First attempt writes HTML with a missing script!
                    (project / "index.html").write_text(
                        '<html><head><title>Notlar</title></head><body><script src="yok.js"></script></body></html>',
                        encoding="utf-8",
                    )
                else:
                    (project / "app.js").write_text("const x = 1;\n", encoding="utf-8")
                    (project / "index.html").write_text(
                        '<html><head><title>Notlar</title></head><body><h1>Hazır</h1>'
                        '<script src="app.js"></script></body></html>',
                        encoding="utf-8",
                    )
                return {"status": "completed", "summary": "yazıldı", "report": "KANIT: index.html"}

            ledger = JobLedger.create({
                "goal": "Notlar web sitesi",
                "project_path": str(project),
                "conversation_id": "c1",
                "hours": 1,
                "permission_level": "full",
                "review": False,
                "milestones": [{"title": "Ana web sayfası", "acceptance": "index.html sayfası açılıyor"}],
            })
            job = LongJob(
                ledger,
                run_milestone=run_milestone,
                verify=lambda stop: {"ok": True, "summary": "Kontrol komutu tanımlanmadı."},
                baseline=lambda: {"status": "ok", "ref": "base"},
                checkpoint=lambda: {"status": "ok", "ref": "cp"},
                commit=lambda files, msg: "deadbeef1234",
                launch=lambda l, m, s: wc.observe_web(
                    project / "index.html", project, Path(tmp) / f"ev-{attempts[0]}", s, edge_executable=None),
            )
            job.run()
            self.assertEqual(attempts[0], 2)
            self.assertEqual(ledger.data["status"], "done")
            report = finish_report(ledger)
            self.assertIn("Web sayfası denetlendi", report)

            chat = FakeChat(project, replies=[])
            opened = []
            with patch("os.startfile", side_effect=opened.append, create=True):
                res = chat.job_control(ledger.data["id"], "open_page")
            self.assertEqual(res["status"], "opened")
            self.assertEqual(opened, [str((project / "index.html").resolve())])

            # Non-web project refuses open_page cleanly.
            (project / "index.html").unlink()
            with patch("os.startfile", side_effect=opened.append, create=True), self.assertRaises(JobError):
                chat.job_control(ledger.data["id"], "open_page")


if __name__ == "__main__":
    unittest.main()
