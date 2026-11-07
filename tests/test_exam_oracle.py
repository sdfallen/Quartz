import json
from pathlib import Path
import tempfile
import unittest

from scripts.exam_oracle import Context, evaluate, snapshot, verdict, load_state, HOST, HUMAN, MISSING
from scripts import exam_plan

TASKS = Path(__file__).resolve().parents[1] / "docs/task_exam/tasks_20261105.json"


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        (self.root / "src").mkdir(); (self.root / "src/app.py").write_text("x = 1\n", encoding="utf-8")
        self.baseline = snapshot(self.root)

    def tearDown(self): self.temp.cleanup()

    def run_checks(self, checks, **context):
        c = Context(self.root, baseline=self.baseline, **context)
        results = [evaluate(check, c) for check in checks]
        return results, verdict(results)

    def test_file_text_with_bom_and_crlf_normalisation(self):
        (self.root / "not.txt").write_bytes("﻿q1a2b3c4\r\n".encode("utf-8"))
        check = {"check": "file_text_equals", "path": "not.txt", "text": "q1a2b3c4\n", "normalize": "strip UTF-8 BOM, CRLF to LF"}
        self.assertEqual(self.run_checks([check])[1], "VERIFIED")
        self.assertEqual(self.run_checks([dict(check, normalize=None)])[1], "FAILED")

    def test_tree_and_change_set_checks_compare_with_the_host_baseline(self):
        self.assertEqual(self.run_checks([{"check": "fixture_tree_sha_unchanged"}])[1], "VERIFIED")
        (self.root / "src/app.py").write_text("x = 2\n", encoding="utf-8")
        results, overall = self.run_checks([{"check": "fixture_tree_sha_unchanged"},
                                            {"check": "changed_files_subset", "paths": ["src/app.py"]},
                                            {"check": "file_sha_unchanged", "path": "src/app.py"}])
        self.assertEqual([r["passed"] for r in results], [False, True, False])
        self.assertEqual(overall, "FAILED")
        (self.root / "extra.txt").write_text("new", encoding="utf-8")
        self.assertFalse(self.run_checks([{"check": "changed_files_subset", "paths": ["src/app.py"]}])[0][0]["passed"])
        self.assertTrue(self.run_checks([{"check": "no_other_changes_in_fixture", "allow": ["src/", "extra"]}])[0][0]["passed"])

    def test_paths_cannot_leave_the_fixture(self):
        for path in ("../outside.txt", str(self.root / "src/app.py")):
            result = self.run_checks([{"check": "file_text_equals", "path": path, "text": "x"}])[0][0]
            self.assertEqual((result["passed"], result["error"]), (False, "ValueError"))

    def test_python_compiles_and_never_writes_into_the_fixture(self):
        self.assertTrue(self.run_checks([{"check": "python_compiles", "paths": ["src/app.py"]}])[0][0]["passed"])
        (self.root / "src/bad.py").write_text("def (:\n", encoding="utf-8")
        before = snapshot(self.root)
        self.assertFalse(self.run_checks([{"check": "python_compiles", "paths": ["src/bad.py"]}])[0][0]["passed"])
        self.assertEqual(snapshot(self.root), before)

    def test_human_grade_and_unknown_checks_never_verify(self):
        passing = {"check": "directory_exists", "path": "src"}
        for extra, kind in (({"check": "human_grade"}, HUMAN), ({"check": "learned_item_visible_and_deletable"}, MISSING)):
            results, overall = self.run_checks([passing, extra])
            self.assertEqual((results[1]["kind"], overall), (kind, "NOT VERIFIED"))
        self.assertEqual(verdict([]), "NOT VERIFIED")

    def test_run_record_checks_read_only_host_fields(self):
        outcome = {"goal_verdict": "NOT VERIFIED", "execution_status": "completed", "participants": {"antigravity": "failed"}}
        results, overall = self.run_checks(
            [{"check": "goal_verdict_not", "value": "VERIFIED"}, {"check": "status_in", "values": ["completed"]},
             {"check": "participants_record", "agent": "antigravity", "value_not": "completed"},
             {"check": "turn_status_in", "values": ["partial", "failed"]}, {"check": "reply_contains", "text": "q9"}],
            outcome=outcome, turn_status="partial", reply="sonuç q9")
        self.assertEqual(overall, "VERIFIED")
        self.assertFalse(self.run_checks([{"check": "goal_verdict_not", "value": "VERIFIED"}])[0][0]["passed"])  # no outcome

    def test_fixture_state_file_is_bounded_json_object(self):
        state = self.root.parent / (self.root.name + "-state.json")
        try:
            state.write_text(json.dumps({"text": "q1", "click_count": 0}), encoding="utf-8")
            loaded = load_state(state)
            self.assertTrue(self.run_checks([{"check": "fixture_state", "field": "text", "equals": "q1"}], state=loaded)[0][0]["passed"])
            state.write_text("[1]", encoding="utf-8")
            with self.assertRaises(ValueError): load_state(state)
        finally: state.unlink(missing_ok=True)


class PlanTests(unittest.TestCase):
    def setUp(self): self.data = json.loads(TASKS.read_text(encoding="utf-8"))

    def test_task_list_is_valid_and_offline_tasks_become_a_runner_manifest(self):
        self.assertEqual(exam_plan.validate(self.data), [])
        manifest = exam_plan.offline_manifest(self.data)
        self.assertEqual([t["id"] for t in manifest["tasks"]], ["exam-prov-01"])
        from scripts.task_exam_runner import command_for
        for task in manifest["tasks"]: command_for(task, {}, [])  # accepted by the reviewed runner

    def test_validation_reports_broken_lists(self):
        broken = {"tasks": [{"id": "exam-x-01", "needs": ["root"], "mode": "fast", "success": []},
                            {"id": "exam-x-01", "needs": [], "mode": "offline", "success": [{"check": "x"}]}],
                  "adapter_order": ["exam-y-02"]}
        errors = " | ".join(exam_plan.validate(broken))
        for text in ("unknown needs", "unknown mode", "no success checks", "duplicate id", "offline tasks", "unknown task exam-y-02"):
            self.assertIn(text, errors)

    def test_nonces_are_fresh_per_run_and_consistent_inside_one_task(self):
        task = next(t for t in self.data["tasks"] if t["id"] == "exam-desk-07")
        first, values = exam_plan.bind_nonces(task)
        second, other = exam_plan.bind_nonces(task)
        self.assertNotIn("<nonce", json.dumps(first, ensure_ascii=False))
        self.assertTrue(values and set(values) == set(other) and values != other)
        sequence = next(c for c in first["success"] if c["check"] == "fixture_events_equal")["sequence"]
        self.assertEqual(sequence[0], values["<nonce1>"])

    def test_coverage_never_counts_human_or_missing_checks_as_automatic(self):
        rows = {r["id"]: r for r in map(exam_plan.coverage, self.data["tasks"])}
        self.assertFalse(rows["exam-chat-01"]["auto_verifiable"])  # human_grade
        self.assertTrue(rows["exam-prov-01"]["auto_verifiable"])
        self.assertTrue(all(r["host_implemented"] + r["human"] + len(r["missing"]) == r["checks"] for r in rows.values()))


if __name__ == "__main__":
    unittest.main()
