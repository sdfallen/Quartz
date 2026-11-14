"""The skill shelf: agents install a GitHub skill, /skill uses it (14 Nov 2026)."""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.skill_shelf import SkillError, SkillShelf, install_request, invocation, prompt_block, verdict
from tests.test_team_turn import TeamRun, make_chat

SKILL_MD = "---\nname: pdf-ozet\ndescription: PDF dosyalarını özetler\n---\n# PDF özeti\nAdımlar: ...\n"


def repo_zip(entries, top="skills-0123456789abcdef0123456789abcdef01234567"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, data in entries.items():
            bundle.writestr(f"{top}/{name}", data)
    return buffer.getvalue()


class FakeOpener:
    def __init__(self, payload):
        self.payload, self.requests = payload, []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        return io.BytesIO(self.payload)


class ParsingTests(unittest.TestCase):
    def test_install_request(self):
        req = install_request("Şu skill'i kur: https://github.com/anthropics/skills/tree/main/skills/pdf")
        self.assertEqual((req["owner"], req["repo"], req["ref"], req["subpath"]), ("anthropics", "skills", "main", "skills/pdf"))
        self.assertEqual(install_request("Bu skill'i yükle https://github.com/a/b.git")["repo"], "b")
        self.assertIsNone(install_request("https://github.com/a/b deposuna bak"))  # not an install request
        self.assertIsNone(install_request("Skill kur ama link yok"))

    def test_invocation_and_verdict(self):
        self.assertEqual(invocation("/skill pdf-ozet şu dosyayı özetle"), ("pdf-ozet", "şu dosyayı özetle"))
        self.assertEqual(invocation("/skill"), ("", ""))
        self.assertIsNone(invocation("skill nedir"))
        self.assertEqual(verdict("Güvenli görünüyor.\nKARAR: UYGUN"), "UYGUN")
        self.assertEqual(verdict("KARAR: UYGUN DEĞİL"), "UYGUN DEĞİL")
        self.assertIsNone(verdict("Bence iyi."))
        self.assertIsNone(verdict("KARAR: UYGUN ... KARAR: UYGUN DEĞİL"))  # contradictory = unclear


class ShelfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fetch_pins_the_sha_and_register_copies_only_the_skill(self):
        opener = FakeOpener(repo_zip({"skills/pdf/SKILL.md": SKILL_MD, "skills/pdf/run.py": "print(1)",
                                      "skills/pdf/.env": "K=1", "README.md": "x"}))
        shelf = SkillShelf(self.root, opener=opener)
        fetched = shelf.fetch(install_request("skill kur https://github.com/anthropics/skills/tree/main/skills/pdf"))
        request = opener.requests[0]
        self.assertEqual(request.full_url, "https://codeload.github.com/anthropics/skills/zip/main")
        self.assertNotIn("Authorization", request.headers)
        self.assertTrue(fetched["sha"].startswith("0123456789ab"))
        self.assertEqual([s["name"] for s in fetched["skills"]], ["pdf-ozet"])
        entry = shelf.register(fetched["skills"][0], source="https://github.com/anthropics/skills", sha=fetched["sha"],
                               reviewers={"Fides": "UYGUN"})
        shelf.discard(fetched["staging"])
        self.assertEqual([s["name"] for s in shelf.list()], ["pdf-ozet"])
        loaded = shelf.load("pdf-ozet")
        self.assertIn("PDF özeti", loaded["text"])
        self.assertFalse((self.root / "shelf" / "pdf-ozet" / ".env").exists())
        self.assertFalse(Path(fetched["staging"]).exists())
        block = prompt_block(loaded)
        self.assertIn("İzinleri", block)
        self.assertIn("SKILL SONU", block)
        self.assertTrue(shelf.remove("pdf-ozet"))
        self.assertEqual(shelf.list(), [])
        self.assertEqual(entry["sha"], fetched["sha"])

    def test_repo_without_skill_or_escape_is_refused(self):
        with self.assertRaises(SkillError):
            SkillShelf(self.root, opener=FakeOpener(repo_zip({"README.md": "x"}))).fetch(
                install_request("skill kur https://github.com/a/b"))
        with self.assertRaises(SkillError):
            SkillShelf(self.root, opener=FakeOpener(repo_zip({"a/SKILL.md": SKILL_MD}))).fetch(
                install_request("skill kur https://github.com/a/b/tree/main/../../x"))
        self.assertEqual(list((self.root / "staging").iterdir()), [])


class InstallTurnTests(unittest.TestCase):
    def run_install(self, directory, replies):
        chat = make_chat(directory)
        chat.skills = SkillShelf(Path(directory) / "skills",
                                 opener=FakeOpener(repo_zip({"skills/pdf/SKILL.md": SKILL_MD})))
        run = TeamRun(chat)
        original = run._record

        def record(agent, kwargs):
            original(agent, kwargs)
            return replies[agent]
        run._record = record
        cid = chat.new_conversation(agent="claude", space="work")["id"]
        run.run("Şu skill'i kur: https://github.com/anthropics/skills/tree/main/skills/pdf")
        messages = chat.store.get(cid)["messages"]
        chat._diagnostics.close()
        return chat, run, messages

    def test_all_three_approve_then_spes_installs(self):
        with tempfile.TemporaryDirectory() as directory:
            ok = "Risk görmedim.\nKARAR: UYGUN"
            chat, run, messages = self.run_install(directory, {"codex": ok, "antigravity": ok, "claude": ok})
            shelf = [s["name"] for s in chat.skills.list()]
        self.assertEqual(shelf, ["pdf-ozet"])
        self.assertEqual(sorted(c["agent"] for c in run.calls), ["antigravity", "claude", "codex"])
        self.assertTrue(all(not c["write"] and not c["web"] for c in run.calls))
        note = [m for m in messages if m.get("sender") == "quartz" and (m.get("metadata") or {}).get("skill_install")]
        self.assertIn("/skill pdf-ozet", note[0]["content"])

    def test_one_objection_or_an_unclear_verdict_installs_nothing(self):
        for replies in ({"codex": "KARAR: UYGUN", "antigravity": "Ağa veri gönderiyor.\nKARAR: UYGUN DEĞİL", "claude": "KARAR: UYGUN"},
                        {"codex": "KARAR: UYGUN", "antigravity": "KARAR: UYGUN", "claude": "Bence olur."}):
            with self.subTest(replies=replies), tempfile.TemporaryDirectory() as directory:
                chat, _, messages = self.run_install(directory, replies)
                self.assertEqual(chat.skills.list(), [])
                self.assertTrue(any("Skill kurulmadı" in m["content"] for m in messages))


class UseTests(unittest.TestCase):
    def test_skill_list_and_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = make_chat(directory)
            chat.skills = SkillShelf(Path(directory) / "skills",
                                     opener=FakeOpener(repo_zip({"skills/pdf/SKILL.md": SKILL_MD})))
            fetched = chat.skills.fetch(install_request("skill kur https://github.com/a/b"))
            chat.skills.register(fetched["skills"][0], source="https://github.com/a/b", sha=fetched["sha"], reviewers={})
            cid = chat.new_conversation(agent="claude", space="chat")["id"]
            listed = chat.send_message("/skill liste")
            self.assertEqual(listed["agent"], "quartz")
            self.assertIn("/skill pdf-ozet", listed["assistant_message"]["content"])
            unknown = chat.send_message("/skill yok-boyle")
            self.assertIn("rafta yok", unknown["assistant_message"]["content"])
            run = TeamRun(chat)
            run.run("/skill pdf-ozet bu notu özetle")
            user = [m for m in chat.store.get(cid)["messages"] if m["role"] == "user"][-1]
            prompt = chat._communication_prompt(cid, "X")
            chat._diagnostics.close()
        self.assertEqual((user["content"], user["metadata"]["skill"]), ("bu notu özetle", "pdf-ozet"))
        self.assertIn("SKILL: pdf-ozet", prompt)


if __name__ == "__main__":
    unittest.main()
