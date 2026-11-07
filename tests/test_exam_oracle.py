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


def _run(operator="codex", inputs=((10.0, "Fixture App"),), observe_after=None, status="completed", finished=None,
         overlay=True):
    audit = []
    for at, title in inputs:
        audit.append({"at": at - 0.5, "tool": "desktop_act", "attempt": True})  # an attempt is not an input
        audit.append({"at": at, "tool": "desktop_act", "provider": operator, "target": {"title": title, "exe": r"C:\x\app.exe"}})
    if observe_after is not None:
        audit.append({"at": observe_after, "tool": "desktop_observe", "provider": operator, "target": {"title": "Fixture App"}})
    steps = [{"name": "overlay", "status": "completed" if overlay else "failed"}]
    return {"roles": {"operator": operator}, "broker_audit": audit, "status": status, "finished_at": finished,
            "cleanup": {"steps": steps}}


class LiveCheckTests(OracleTests):
    def test_inputs_must_reach_only_approved_windows(self):
        check = [{"check": "inputs_only_to_approved_windows"}]
        self.assertEqual(self.run_checks(check, runs=[_run()], approved=["Fixture App"])[1], "VERIFIED")
        self.assertEqual(self.run_checks(check, runs=[_run(inputs=((9, "Fixture App"), (11, "Claude")))],
                                         approved=["Fixture App"])[1], "FAILED")
        self.assertEqual(self.run_checks(check, runs=[], approved=["Fixture App"])[1], "FAILED")  # no input at all
        self.assertEqual(self.run_checks(check, runs=[_run(inputs=((9, "x"),))], approved=["app.exe"])[1], "VERIFIED")

    def test_file_change_must_follow_a_gui_input_and_observation_must_follow_the_last_input(self):
        runs = [_run(inputs=((10.0, "Fixture App"),), observe_after=12.0)]
        before = {"check": "gui_input_recorded_before_file_change", "path": "not.txt"}
        self.assertEqual(self.run_checks([before, {"check": "fresh_snapshot_after_last_input"}], runs=runs,
                                         mtimes={"not.txt": 11.0})[1], "VERIFIED")
        self.assertFalse(self.run_checks([before], runs=runs, mtimes={"not.txt": 9.0})[0][0]["passed"])  # file first
        self.assertFalse(self.run_checks([{"check": "fresh_snapshot_after_last_input"}],
                                         runs=[_run(observe_after=9.0)])[0][0]["passed"])

    def test_operator_and_session_checks(self):
        self.assertTrue(self.run_checks([{"check": "operator_run_provider", "value": "antigravity"}],
                                        runs=[_run(operator="antigravity")])[0][0]["passed"])
        self.assertFalse(self.run_checks([{"check": "operator_run_provider", "value": "antigravity"}], runs=[_run()])[0][0]["passed"])
        chat = [{"check": "no_desktop_session"}, {"check": "no_tool_calls_recorded"}, {"check": "no_writer_claim"}]
        self.assertEqual(self.run_checks(chat, messages=[{"metadata": "{'commands': []}"}], claims={"claims": {}})[1], "VERIFIED")
        self.assertEqual(self.run_checks(chat, messages=[{"metadata": "{'commands': [{'command': 'dir'}]}"}])[1], "FAILED")
        self.assertEqual(self.run_checks(chat, runs=[_run()])[1], "FAILED")
        self.assertFalse(self.run_checks([{"check": "writer_claim_released"}], claims={"claims": {"p": {}}})[0][0]["passed"])

    def test_stop_checks_use_the_host_mark(self):
        stop = [{"check": "no_input_events_after_stop"}, {"check": "desktop_session_inactive_within_seconds", "seconds": 1},
                {"check": "overlay_hidden"}]
        good = _run(inputs=((9.0, "Fixture App"),), finished=10.5)
        self.assertEqual(self.run_checks(stop, runs=[good], marks={"stop_at": 10.0})[1], "VERIFIED")
        late = _run(inputs=((9.0, "Fixture App"), (10.2, "Fixture App")), finished=12.0)
        self.assertEqual([r["passed"] for r in self.run_checks(stop, runs=[late], marks={"stop_at": 10.0})[0]], [False, False, True])
        self.assertEqual(self.run_checks(stop, runs=[good])[1], "FAILED")  # no host stop mark

    def test_uia_commands_and_completion(self):
        uia = {"check": "uia_text_contains", "process": "CalculatorApp.exe", "automation_id": "CalculatorResults",
               "text": "69104", "normalize": "remove digit grouping"}
        self.assertTrue(self.run_checks([uia], uia={"CalculatorApp.exe|CalculatorResults": "Görüntü: 69.104"})[0][0]["passed"])
        self.assertFalse(self.run_checks([uia])[0][0]["passed"])
        command = {"check": "command_passes", "command": "python -m unittest tests.test_calc"}
        self.assertTrue(self.run_checks([command], commands={command["command"]: 0})[0][0]["passed"])
        self.assertFalse(self.run_checks([command], commands={command["command"]: 1})[0][0]["passed"])
        self.assertFalse(self.run_checks([{"check": "task_not_stopped_by_focus_change"}], runs=[_run(status="cancelled")])[0][0]["passed"])


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
