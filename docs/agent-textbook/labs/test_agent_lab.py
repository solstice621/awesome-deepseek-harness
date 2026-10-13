"""Mechanism tests using fresh local SQLite databases and controlled child Python processes."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent_lab import (AgentLab, ApprovalRequired, CallConflict, CONSTRAINTS,
                       GOAL, InvalidCall, ScriptedModel, ToolCall,
                       TransientFailure, compact_context, evaluate)


class NoMoreCalls:
    def next_call(self, context):
        return None


class RepeatingModel:
    def next_call(self, context):
        return ToolCall("repeat", "inspect", {})


class AlwaysFailTestTool(AgentLab):
    def execute(self, call, approve_edit=False, fail_once=None, crash_before=None, crash_after=None):
        return super().execute(call, approve_edit, {"test_total"}, crash_before, crash_after)


class AgentLabTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="agent-lab-test-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "run.sqlite3"

    def open_lab(self, **kwargs):
        lab = AgentLab(self.path, **kwargs)
        self.addCleanup(lab.close)
        return lab

    def test_success_reproduces_bug_repairs_and_verifies_current_revision(self):
        lab = self.open_lab()
        result = lab.run(approve_edit=True)
        self.assertEqual(result, {"status": "completed", "spent": 4, "max_attempts": 8,
                                  "decisions": 5, "max_decisions": 16,
                                  "mode": "quantity", "revision": 1, "total": "43.00", "effects": 1})
        calls = lab.build_context()["tool_results"]
        self.assertEqual([row["call_id"] for row in calls], [call.call_id for call in ScriptedModel.PLAN])
        self.assertEqual(calls[1]["result"]["actual"], "15.50")
        self.assertFalse(calls[1]["result"]["passed"])
        self.assertTrue(calls[3]["result"]["passed"])
        self.assertEqual(calls[3]["result"]["revision"], result["revision"])

    def test_zero_budget_starts_no_tools(self):
        lab = self.open_lab(max_attempts=0)
        result = lab.run(approve_edit=True)
        self.assertEqual((result["status"], result["spent"], result["effects"]), ("budget_exhausted", 0, 0))
        self.assertEqual(lab.build_context()["tool_results"], [])

    def test_three_attempts_can_repair_but_cannot_claim_verified_success(self):
        lab = self.open_lab(max_attempts=3)
        result = lab.run(approve_edit=True)
        self.assertEqual((result["status"], result["total"], result["spent"]), ("budget_exhausted", "43.00", 3))
        # Opening again with a different constructor value cannot reset the budget.
        resumed = self.open_lab(max_attempts=99)
        self.assertEqual(resumed.run(approve_edit=True)["max_attempts"], 3)
        self.assertEqual(resumed.snapshot()["spent"], 3)

    def test_four_attempt_budget_finishes_exactly(self):
        self.assertEqual(self.open_lab(max_attempts=4).run(approve_edit=True)["status"], "completed")

    def test_zero_decision_budget_does_not_call_model(self):
        lab = self.open_lab(max_decisions=0)
        result = lab.run(model=RepeatingModel())
        self.assertEqual((result["status"], result["decisions"], result["spent"]),
                         ("decision_budget_exhausted", 0, 0))

    def test_cached_replay_consumes_persistent_decision_budget(self):
        lab = self.open_lab(max_decisions=4)
        result = lab.run(model=RepeatingModel())
        self.assertEqual((result["status"], result["decisions"], result["spent"]),
                         ("decision_budget_exhausted", 4, 1))
        resumed = self.open_lab(max_decisions=100)
        again = resumed.run(model=RepeatingModel())
        self.assertEqual((again["max_decisions"], again["decisions"], again["spent"]), (4, 4, 1))

    def test_completed_run_is_stable_when_reopened_at_its_decision_limit(self):
        lab = self.open_lab(max_decisions=5)
        result = lab.run(approve_edit=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.open_lab().run(approve_edit=True), result)

    def test_approval_pause_resume_does_not_edit_or_charge_denied_attempt(self):
        lab = self.open_lab()
        paused = lab.run()
        self.assertEqual((paused["status"], paused["spent"], paused["effects"]), ("waiting_approval", 2, 0))
        self.assertEqual(paused["mode"], "unit_only")
        resumed = self.open_lab().run(approve_edit=True)
        self.assertEqual((resumed["status"], resumed["spent"], resumed["effects"]), ("completed", 4, 1))

    def test_approval_is_bound_to_exact_edit_arguments(self):
        lab = self.open_lab()
        with self.assertRaises(ApprovalRequired):
            lab.execute(ToolCall("unapproved-edit", "set_mode", {"mode": "unit_only"}), approve_edit=True)
        self.assertEqual((lab.snapshot()["spent"], lab.snapshot()["effects"]), (0, 0))

    def test_schema_rejects_unknown_tools_extra_fields_and_invalid_modes(self):
        lab = self.open_lab()
        rejected = [ToolCall("shell", "shell", {"command": "anything"}),
                    ToolCall("path", "inspect", {"path": "../../other"}),
                    ToolCall("missing", "set_mode", {}),
                    ToolCall("code", "set_mode", {"mode": "arbitrary code"}),
                    ToolCall("wrong-type", "set_mode", {"mode": True})]
        for call in rejected:
            with self.subTest(call=call.call_id), self.assertRaises(InvalidCall):
                lab.execute(call, approve_edit=True)
        self.assertEqual((lab.snapshot()["spent"], lab.snapshot()["effects"]), (0, 0))

    def test_transient_failure_retries_pending_id_and_consumes_budget(self):
        lab = self.open_lab()
        result = lab.run(approve_edit=True, fail_once={"test_total"})
        self.assertEqual((result["status"], result["spent"]), ("completed", 5))
        self.assertEqual(sum(event["kind"] == "tool_error" for event in lab.events()), 1)
        self.assertEqual(len(lab.build_context()["tool_results"]), 4)

    def test_repeated_transient_failure_stops_at_budget(self):
        with AlwaysFailTestTool(self.path, max_attempts=3) as lab:
            result = lab.run(approve_edit=True)
            self.assertEqual((result["status"], result["spent"], result["effects"]), ("budget_exhausted", 3, 0))
            self.assertEqual(lab.build_context()["pending"], ["test-before"])

    def test_same_id_same_arguments_replay_receipt_without_new_effect_or_budget(self):
        lab = self.open_lab(max_attempts=1)
        call = ToolCall("repair", "set_mode", {"mode": "quantity"})
        original = lab.execute(call, approve_edit=True)
        self.assertEqual(lab.execute(call), original)  # Receipt replay performs no new edit.
        self.assertEqual(lab.execute(call), original)
        self.assertEqual((lab.snapshot()["spent"], lab.snapshot()["effects"]), (1, 1))

    def test_same_id_different_arguments_or_tool_conflicts(self):
        lab = self.open_lab()
        lab.execute(ToolCall("repair", "set_mode", {"mode": "quantity"}), approve_edit=True)
        for call in [ToolCall("repair", "set_mode", {"mode": "unit_only"}), ToolCall("repair", "inspect", {})]:
            with self.subTest(tool=call.name), self.assertRaises(CallConflict):
                lab.execute(call, approve_edit=True)
        self.assertEqual((lab.snapshot()["mode"], lab.snapshot()["revision"], lab.snapshot()["effects"]),
                         ("quantity", 1, 1))

    def test_new_id_is_a_new_action_not_semantic_deduplication(self):
        lab = self.open_lab()
        for call_id in ("repair-1", "repair-2"):
            lab.execute(ToolCall(call_id, "set_mode", {"mode": "quantity"}), approve_edit=True)
        self.assertEqual((lab.snapshot()["spent"], lab.snapshot()["effects"], lab.snapshot()["revision"]), (2, 2, 2))

    def test_stale_passing_verification_cannot_finish_new_revision(self):
        lab = self.open_lab()
        lab.execute(ToolCall("repair-1", "set_mode", {"mode": "quantity"}), approve_edit=True)
        self.assertTrue(lab.execute(ToolCall("verify-old", "test_total", {}))["passed"])
        lab.execute(ToolCall("repair-2", "set_mode", {"mode": "quantity"}), approve_edit=True)
        self.assertEqual(lab.run(model=NoMoreCalls())["status"], "failed_verification")

    def test_pending_action_prevents_completion_even_after_a_passing_test(self):
        lab = self.open_lab()
        lab.execute(ToolCall("repair-1", "set_mode", {"mode": "quantity"}), approve_edit=True)
        lab.execute(ToolCall("verify", "test_total", {}))
        with self.assertRaises(TransientFailure):
            lab.execute(ToolCall("unfinished", "set_mode", {"mode": "quantity"}),
                        approve_edit=True, fail_once={"set_mode"})
        self.assertEqual(lab.run(model=NoMoreCalls())["status"], "failed_verification")
        self.assertEqual(lab.build_context()["pending"], ["unfinished"])

    def test_current_sample_cannot_hide_bug_from_independent_fixed_oracle(self):
        lab = self.open_lab(csv_text="price,quantity\n3.50,1\n12.00,1\n")
        self.assertTrue(lab.execute(ToolCall("verify", "test_total", {}))["passed"])
        result = lab.run(model=NoMoreCalls())
        self.assertEqual((result["mode"], result["status"]), ("unit_only", "failed_verification"))
        self.assertEqual(lab.events()[-1]["oracle_passed"], 2)

    def test_verification_uses_completion_order_not_first_attempt_order(self):
        lab = self.open_lab()
        early_test = ToolCall("early-test", "test_total", {})
        with self.assertRaises(TransientFailure):
            lab.execute(early_test, fail_once={"test_total"})
        lab.execute(ToolCall("repair-1", "set_mode", {"mode": "quantity"}), approve_edit=True)
        lab.execute(ToolCall("later-test", "test_total", {}))
        lab.execute(ToolCall("repair-2", "set_mode", {"mode": "quantity"}), approve_edit=True)
        self.assertEqual(lab.execute(early_test)["revision"], 2)
        self.assertEqual(lab.build_context()["tool_results"][-1]["call_id"], "early-test")
        self.assertEqual(lab.run(model=NoMoreCalls())["status"], "completed")

    def crash_child(self, phase):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("agent_lab.py")),
                                 "demo", "--db", str(self.path), "--approve-edit", f"--crash-{phase}", "repair"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 86, result.stderr)

    def test_process_crash_before_commit_rolls_back_effect_and_receipt(self):
        self.crash_child("before")
        lab = self.open_lab()
        before = lab.snapshot()
        self.assertEqual((before["mode"], before["revision"], before["effects"], before["spent"]),
                         ("unit_only", 0, 0, 3))
        self.assertEqual(lab.build_context()["pending"], ["repair"])
        self.assertFalse(any(event["kind"] == "tool_result" and event["call_id"] == "repair"
                             for event in lab.events()))
        resumed = lab.run(approve_edit=True)
        self.assertEqual((resumed["status"], resumed["spent"], resumed["effects"]), ("completed", 5, 1))

    def test_process_crash_after_commit_replays_without_duplicate_effect(self):
        self.crash_child("after")
        lab = self.open_lab()
        before = lab.snapshot()
        self.assertEqual((before["mode"], before["revision"], before["effects"], before["spent"]),
                         ("quantity", 1, 1, 3))
        lab.execute(ToolCall("repair", "set_mode", {"mode": "quantity"}))
        self.assertEqual((lab.snapshot()["spent"], lab.snapshot()["effects"]), (3, 1))
        resumed = lab.run(approve_edit=True)
        self.assertEqual((resumed["status"], resumed["spent"], resumed["effects"]), ("completed", 4, 1))

    def test_compression_keeps_goal_constraints_pending_and_structured_evidence(self):
        lab = self.open_lab()
        lab.execute(ToolCall("inspect", "inspect", {}))
        with self.assertRaises(TransientFailure):
            lab.execute(ToolCall("pending-test", "test_total", {}), fail_once={"test_total"})
        context = lab.build_context()
        compacted = compact_context(context, keep=1)
        self.assertGreater(len(context["recent_events"]), len(compacted["recent_events"]))
        self.assertEqual(len(compacted["recent_events"]), 1)
        for field in ("goal", "constraints", "pending", "tool_results", "state"):
            self.assertEqual(compacted[field], context[field])
        self.assertEqual(compacted["goal"], GOAL)
        self.assertEqual(compacted["constraints"], CONSTRAINTS)
        self.assertEqual(compacted["pending"], ["pending-test"])

    def test_fixture_evaluation_has_explicit_denominator_and_independent_expected_values(self):
        report = evaluate()
        self.assertEqual((report["cases"], report["baseline_passed"], report["workflow_passed"]), (5, 2, 5))
        self.assertTrue(all(row["attempts"] == 4 for row in report["results"]))


if __name__ == "__main__":
    unittest.main()
