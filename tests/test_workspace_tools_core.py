"""Shared pieces for attachments, the work panel and result cards (14 Nov 2026)."""
import json
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from core.local_preview import PreviewError, PreviewServers, best_preview_file, read_for_panel, resolve_inside
from core.result_cards import extract_cards, hide_open_block, wants_cards
from core.safe_archive import ArchiveError, extract_zip


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in entries.items():
            bundle.writestr(name, data)
    return path


class SafeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_normal_zip_extracts_and_skips_secrets(self):
        z = make_zip(self.root / "a.zip", {"site/index.html": "<h1>x</h1>", "site/.env": "SECRET=1", "notes.md": "n"})
        out = extract_zip(z, self.root / "out")
        self.assertEqual(sorted(out["files"]), ["notes.md", "site/index.html"])
        self.assertEqual(out["skipped_secret"], ["site/.env"])
        self.assertFalse((self.root / "out" / "site" / ".env").exists())

    def test_escapes_and_bad_names_are_refused(self):
        for name in ("../evil.txt", "/abs.txt", "C:/win.txt", "a/../../b.txt", "con.txt", "x/nul"):
            with self.subTest(name=name):
                z = make_zip(self.root / f"z{abs(hash(name))}.zip", {name: "x"})
                target = self.root / f"out{abs(hash(name))}"
                with self.assertRaises(ArchiveError):
                    extract_zip(z, target)
        self.assertFalse((self.root / "evil.txt").exists())

    def test_links_are_skipped_never_created(self):
        import stat as stat_module
        path = self.root / "links.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("data/real.csv", "a,b")
            link = zipfile.ZipInfo("data/styles.csv")
            link.external_attr = (stat_module.S_IFLNK | 0o777) << 16
            bundle.writestr(link, "../../../etc/passwd")
        out = extract_zip(path, self.root / "out-links")
        self.assertEqual((out["files"], out["skipped_links"]), (["data/real.csv"], ["data/styles.csv"]))
        self.assertFalse((self.root / "out-links" / "data" / "styles.csv").exists())

    def test_zip_bomb_and_non_zip_are_refused(self):
        bomb = make_zip(self.root / "bomb.zip", {"big.txt": "0" * (5 * 1024 * 1024)})
        with self.assertRaises(ArchiveError):
            extract_zip(bomb, self.root / "b")
        (self.root / "fake.zip").write_text("not a zip")
        with self.assertRaises(ArchiveError):
            extract_zip(self.root / "fake.zip", self.root / "c")

    def test_target_must_be_empty(self):
        (self.root / "full").mkdir()
        (self.root / "full" / "x").write_text("x")
        z = make_zip(self.root / "a.zip", {"a.txt": "a"})
        with self.assertRaises(ArchiveError):
            extract_zip(z, self.root / "full")


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "index.html").write_text("<h1>Kafe</h1>", encoding="utf-8")
        (self.root / "css").mkdir()
        (self.root / "css" / "s.css").write_text("body{}", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=1")
        (self.root / ".git").mkdir()
        (self.root / ".git" / "config").write_text("x")
        (self.root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
        self.servers = PreviewServers()

    def tearDown(self):
        self.servers.stop_all()
        self.tmp.cleanup()

    def get(self, url):
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as exc:
            return exc.code, b""

    def test_server_serves_the_site_and_nothing_else(self):
        url = self.servers.url_for(self.root)
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        self.assertEqual(self.servers.url_for(self.root), url)  # one server per folder
        self.assertEqual(self.get(url), (200, b"<h1>Kafe</h1>"))
        self.assertEqual(self.get(url + "css/s.css")[0], 200)
        for path in (".env", ".git/config", "../" + self.root.name + "/index.html", "%2e%2e/x", "css/"):
            with self.subTest(path=path):
                self.assertEqual(self.get(url + path)[0], 404)
        request = urllib.request.Request(url + "index.html", data=b"x", method="POST")
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5)

    def test_reader_is_root_bound_and_bounded(self):
        self.assertEqual(read_for_panel(self.root, "index.html")["kind"], "text")
        self.assertEqual(read_for_panel(self.root, "logo.png")["kind"], "image")
        for bad in (".env", ".git/config", "../x", "nope.txt"):
            with self.subTest(bad=bad), self.assertRaises((PreviewError, OSError)):
                read_for_panel(self.root, bad)
        with self.assertRaises(PreviewError):
            resolve_inside(self.root, "css/../../etc")

    def test_best_file_prefers_a_page(self):
        self.assertEqual(best_preview_file(["src/app.py", "README.md", "web/index.html"]), "web/index.html")
        self.assertEqual(best_preview_file(["a.py", "docs/guide.md"]), "docs/guide.md")
        self.assertIsNone(best_preview_file([]))


class CardTests(unittest.TestCase):
    def test_block_becomes_safe_cards(self):
        cards = [{"title": "React geliştirici", "description": "Kafe sitesi, 1 hafta.", "url": "https://ornek.com/is/1",
                  "source": "Bionluk", "tags": ["React", "Uzaktan", "Kısa", "fazla"]},
                 {"title": "Kötü link", "url": "javascript:alert(1)"},
                 {"description": "başlıksız"}]
        text = "İşte bulduklarım.\n```spes-kartlar\n" + json.dumps(cards, ensure_ascii=False) + "\n```"
        clean, got = extract_cards(text)
        self.assertEqual(clean, "İşte bulduklarım.")
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["tags"], ["React", "Uzaktan", "Kısa"])
        self.assertNotIn("url", got[1])

    def test_malformed_or_streaming_block_shows_nothing(self):
        self.assertEqual(extract_cards("a\n```spes-kartlar\n[{bozuk\n```"), ("a", []))
        self.assertEqual(hide_open_block('Bakıyorum\n```spes-kartlar\n[{"title": "ya'), "Bakıyorum")

    def test_list_requests_are_recognised(self):
        for text in ("İnternette kriterlerime uyan freelance işleri araştırın ve liste halinde getirin",
                     "En uygun 5 kütüphaneyi bul", "Bana birkaç seçenek öner"):
            self.assertTrue(wants_cards(text), text)
        for text in ("Selam beyler", "Bu kod çalışıyor mu?"):
            self.assertFalse(wants_cards(text), text)


if __name__ == "__main__":
    unittest.main()
