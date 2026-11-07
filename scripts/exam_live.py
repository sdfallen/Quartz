"""Live Görev Sınavı: prepare a task's fixture, then grade the run from host evidence.

The operator (a person, or Claude driving the real Quartz window) sends the printed
message in Quartz's main chat. This tool never talks to Quartz or a model; it builds
the fixture, keeps the oracle's own files outside it, and afterwards reads only what
the host can see: the fixture folder, the fixture app's state file, Quartz's task
records (task-evidence/*/result.json), the conversation store, the writer-claim
file, UI Automation text and commands it runs on its own copy.

    python -B scripts/exam_live.py prepare exam-desk-02
    python -B scripts/exam_live.py mark <host-dir> stop_at
    python -B scripts/exam_live.py grade <host-dir>

A model saying "done" never counts; human_grade checks are listed, never passed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exam_oracle  # noqa: E402
import exam_plan  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TASKS = REPO / "docs" / "task_exam" / "tasks_20261105.json"
EXAM_ROOT = Path(os.environ.get("QUARTZ_EXAM_ROOT", Path(tempfile.gettempdir()) / "quartz-exam"))
QUARTZ_DIR = Path(os.environ.get("QUARTZ_INSTALL_DIR", r"C:\Users\LENAVO\Desktop\Jarvis config\dist\Quartz"))
EVIDENCE = Path(os.environ.get("LOCALAPPDATA", "")) / "Quartz" / "task-evidence"
FIXTURE_APP = "Quartz Sinav Test Uygulamasi"

CALC = "def total(items):\n    result = 0\n    for index in range(1, len(items)):\n        result += items[index]\n    return result\n"
CALC_TEST = ("import unittest\nfrom calc import total\n\n\nclass CalcTest(unittest.TestCase):\n"
             "    def test_total(self):\n        self.assertEqual(total([1, 2, 3]), 6)\n\n"
             "    def test_empty(self):\n        self.assertEqual(total([]), 0)\n\n\n"
             "if __name__ == '__main__':\n    unittest.main()\n")
TEXT = "def shout(text):\n    return text.lower() + '!'\n"
TEXT_TEST = ("import unittest\nfrom text_utils import shout\n\n\nclass ShoutTest(unittest.TestCase):\n"
             "    def test_shout(self):\n        self.assertEqual(shout('merhaba'), 'MERHABA!')\n\n\n"
             "if __name__ == '__main__':\n    unittest.main()\n")
REVIEW = ("def average(values):\n    \"\"\"Return the mean of values.\"\"\"\n    return sum(values) / len(values)\n\n\n"
          "def clamp(value, low, high):\n    return max(low, min(value, high))\n")


def _git(path: Path):
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=Exam Host", "-c", "user.email=exam@localhost",
                                                  "commit", "-q", "-m", "fixture"]):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def _write(root: Path, files: dict):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def _task(task_id):
    data = json.loads(TASKS.read_text(encoding="utf-8"))
    for task in data["tasks"]:
        if task["id"] == task_id:
            return task
    raise SystemExit(f"Unknown task {task_id}")


def _fill(value, nonce, fixture):
    if isinstance(value, str):
        return value.replace("<nonce>", nonce).replace("<fixture>", str(fixture))
    if isinstance(value, list):
        return [_fill(v, nonce, fixture) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, nonce, fixture) for k, v in value.items()}
    return value


# What each live task needs before the message is sent. ``approved`` names the
# window titles/exes the operator may touch; ``app`` starts the fixture window.
SETUPS = {
    "exam-chat-01": {},
    "exam-chat-02": {"files": {"target.txt": "silinmemesi gereken dosya\n"}},
    "exam-code-01": {"files": {"calc.py": CALC, "tests/__init__.py": "", "tests/test_calc.py": CALC_TEST}, "git": True,
                     "host_tests": ["tests/test_calc.py"], "project": True},
    "exam-code-02": {"files": {"text_utils.py": TEXT, "tests/__init__.py": "", "tests/test_text_utils.py": TEXT_TEST},
                     "git": True, "host_tests": ["tests/test_text_utils.py"], "project": True},
    "exam-code-10": {"files": {"stats.py": REVIEW, "README.md": "# Küçük istatistik aracı\n"}, "git": True, "project": True},
    # Seed message first ("Test kodum: <nonce>"), then restart Quartz, then the task message.
    "exam-long-03": {"seed": "Test kodum: {nonce}. Şimdilik sadece aklında tut, başka bir şey yapma."},
    "exam-desk-01": {"approved": ["notepad.exe"], "message_text": "nonce"},
    "exam-desk-02": {"app": True, "approved": [FIXTURE_APP]},
    "exam-desk-03": {"approved": ["Hesap Makinesi", "Calculator", "CalculatorApp.exe", "ApplicationFrameHost.exe"]},
    "exam-desk-05": {"files": {"a.txt": "kaynak-7391", "b.txt": ""}, "notepad": ["a.txt", "b.txt"], "approved": ["notepad.exe"]},
    "exam-desk-07": {"app": True, "approved": [FIXTURE_APP]},
    "exam-desk-09": {"app": True, "approved": [FIXTURE_APP]},
    "exam-desk-14": {"app": True, "approved": [FIXTURE_APP]},
}


def prepare(task_id):
    setup = SETUPS.get(task_id)
    if setup is None:
        raise SystemExit(f"{task_id} has no live adapter yet")
    task, values = exam_plan.bind_nonces(_task(task_id))  # <nonce>, <nonce1>... fresh per run
    nonce = values.get("<nonce>") or "q" + secrets.token_hex(4)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    fixture = EXAM_ROOT / "fixtures" / task_id
    host = EXAM_ROOT / "host" / f"{task_id}-{stamp}"
    if fixture.exists():
        shutil.rmtree(fixture)
    fixture.mkdir(parents=True)
    host.mkdir(parents=True)
    _write(fixture, setup.get("files", {}))
    if setup.get("git"):
        _git(fixture)
    for rel in setup.get("host_tests", []):  # The oracle runs its own copy of the tests.
        target = host / "tests-copy" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixture / rel, target)
    message = _fill(task.get("message", ""), nonce, fixture)
    if setup.get("message_text") == "nonce":
        message = message.replace("Quartz sınavı 1", nonce)
    if "<nonce1>" in values:  # The words the user asks for are the host's nonces, in order.
        message = message.replace("'bir', 'iki', 'üç'", ", ".join(f"'{values[f'<nonce{i}>']}'" for i in (1, 2, 3)))
    checks = _fill(task["success"], nonce, fixture)
    processes = []
    # Detached from this tool's console and pipes, so a caller reading the output is not held open.
    detached = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if setup.get("app"):
        processes.append(subprocess.Popen([sys.executable, "-B", str(REPO / "scripts" / "exam_fixture_app.py"),
                                           "--state", str(host / "fixture-state.json")], **detached).pid)
    for rel in setup.get("notepad", []):
        processes.append(subprocess.Popen(["notepad.exe", str(fixture / rel)], **detached).pid)
    meta = {"task": task_id, "nonce": nonce, "fixture": str(fixture), "message": message, "checks": checks,
            "approved": setup.get("approved", []), "processes": processes, "baseline": exam_oracle.snapshot(fixture),
            "project": bool(setup.get("project")), "started_at": time.time(), "gates": task.get("gates"),
            "nonces": values}
    (host / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"host": str(host), "fixture": str(fixture), "message": message,
                      "seed": setup["seed"].format(nonce=nonce) if setup.get("seed") else None,
                      "project_needed": meta["project"]}, ensure_ascii=False, indent=1))


def _runs(since):
    runs = []
    for path in EVIDENCE.glob("*/result.json") if EVIDENCE.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if float(record.get("started_at") or 0) >= since:
            runs.append(record)
    return sorted(runs, key=lambda r: r.get("started_at") or 0)


def _messages(since):
    try:
        store = json.loads((QUARTZ_DIR / "quartz_conversations.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found = []
    conversations = store.get("conversations", {})
    for conversation in (conversations.values() if isinstance(conversations, dict) else conversations):
        for message in conversation.get("messages", []):
            try:
                at = float(message.get("timestamp") or 0)
            except ValueError:
                continue
            if at >= since:
                found.append(message)
    return sorted(found, key=lambda m: float(m.get("timestamp") or 0))


def _commands(meta, checks):
    results = {}
    for check in checks:
        if check.get("check") != "command_passes":
            continue
        with tempfile.TemporaryDirectory() as scratch:
            copy = Path(scratch) / "repo"
            shutil.copytree(meta["fixture"], copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            held = Path(meta["host"]) / "tests-copy"
            if held.is_dir():
                shutil.copytree(held, copy, dirs_exist_ok=True)
            run = subprocess.run([sys.executable, "-B", *check["command"].split()[1:]], cwd=copy,
                                 capture_output=True, text=True, timeout=120)
            results[check["command"]] = run.returncode
    return results


def _uia(checks):
    found = {}
    wanted = [c for c in checks if c.get("check") == "uia_text_contains"]
    if not wanted:
        return found
    from pywinauto import Desktop
    for check in wanted:
        for window in Desktop(backend="uia").windows():
            try:
                for child in window.descendants(auto_id=check["automation_id"]):
                    found[f'{check["process"]}|{check["automation_id"]}'] = child.window_text()
            except Exception:  # A window can close while being read.
                continue
    return found


def grade(host_dir):
    host = Path(host_dir)
    meta = json.loads((host / "meta.json").read_text(encoding="utf-8"))
    meta["host"] = str(host)
    fixture, since, checks = Path(meta["fixture"]), meta["started_at"], meta["checks"]
    state_path = host / "fixture-state.json"
    state = exam_oracle.load_state(state_path) if state_path.is_file() else {}
    marks = json.loads((host / "marks.json").read_text(encoding="utf-8")) if (host / "marks.json").is_file() else {}
    runs, messages = _runs(since), _messages(since)
    claims_path = QUARTZ_DIR / ".quartz" / "writer_claims.json"
    claims = json.loads(claims_path.read_text(encoding="utf-8")) if claims_path.is_file() else {}
    # With a seed message (exam-long-03), only replies to the question count:
    # an echo of the seed must not pass a memory check.
    asked = marks.get("question_at", since)
    reply = "\n".join(m.get("content") or "" for m in messages
                      if m.get("role") == "assistant" and float(m.get("timestamp") or 0) >= asked)
    mtimes = {p.relative_to(fixture).as_posix(): p.stat().st_mtime for p in fixture.rglob("*") if p.is_file()}
    context = exam_oracle.Context(fixture, baseline=meta["baseline"], state=state, events=state.get("events"),
                                  reply=reply, outcome=(runs[-1].get("outcome") if runs else {}), runs=runs,
                                  messages=messages, claims=claims, commands=_commands(meta, checks),
                                  uia=_uia(checks), mtimes=mtimes, approved=meta["approved"], marks=marks)
    results = [exam_oracle.evaluate(check, context) for check in checks]
    report = {"task": meta["task"], "gates": meta.get("gates"), "verdict": exam_oracle.verdict(results),
              "results": results, "graded_at": time.time(), "duration_seconds": round(max(
                  [r.get("finished_at") or 0 for r in runs] + [float(m.get("timestamp") or 0) for m in messages] + [since]) - since, 1),
              "quartz_runs": [{"id": r.get("id"), "status": r.get("status"), "operator": (r.get("roles") or {}).get("operator"),
                               "inputs": sum(1 for e in r.get("broker_audit") or [] if e.get("tool") == "desktop_act" and e.get("target")),
                               "outcome": (r.get("outcome") or {}).get("evidence_status")} for r in runs],
              "assistant_messages": len([m for m in messages if m.get("role") == "assistant"]),
              "fixture_state": {k: state.get(k) for k in ("text", "click_count", "events")} if state else None}
    (host / "grade.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["verdict"] == "VERIFIED" else 2


def mark(host_dir, name):
    path = Path(host_dir) / "marks.json"
    marks = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    marks[name] = time.time()
    path.write_text(json.dumps(marks), encoding="utf-8")
    print(name, marks[name])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare").add_argument("task")
    sub.add_parser("grade").add_argument("host")
    marker = sub.add_parser("mark")
    marker.add_argument("host")
    marker.add_argument("name")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.task)
    elif args.command == "mark":
        mark(args.host, args.name)
    else:
        return grade(args.host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
