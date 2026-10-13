#!/usr/bin/env python3
"""Offline teaching Agent: no network, model API, arbitrary code, or shell execution.

The scripted policy already knows the repair. This lab demonstrates execution
mechanisms, not the ability of a language model to discover a solution.
"""

import argparse
import copy
import csv
import io
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


DEFAULT_CSV = "price,quantity\n3.50,2\n12.00,3\n"
VERIFICATION_CASES = [
    ("given_example", DEFAULT_CSV, "43.00"),
    ("zero_quantity", "price,quantity\n3.50,0\n12.00,3\n", "36.00"),
    ("empty_rows", "price,quantity\n", "0.00"),
    ("decimal_quantities", "price,quantity\n0.10,3\n0.20,2\n", "0.70"),
    ("unit_quantity", "price,quantity\n0.10,1\n0.20,1\n", "0.30"),
]
GOAL = "修复 CSV 总价漏乘 quantity，并用当前修订的测试结果验证。"
CONSTRAINTS = [
    "只能调用预定义工具，不执行任意代码、shell 或网络请求。",
    "set_mode 修改必须获得与工具及参数匹配的审批。",
    "完成必须依据当前工作区修订的测试结果，不能只依据修复动作。",
    "完成还要求所有已接纳调用结算，并通过固定的独立期望值验证集。",
]
TOOLS = {
    "inspect": {"type": "object", "properties": {}, "additionalProperties": False},
    "test_total": {"type": "object", "properties": {}, "additionalProperties": False},
    "set_mode": {
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["unit_only", "quantity"]}},
        "required": ["mode"],
        "additionalProperties": False,
    },
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def total(csv_text, mode):
    """Evaluate one of two predefined program modes; this never evaluates code."""
    amount = Decimal("0")
    for row in csv.DictReader(io.StringIO(csv_text)):
        price, quantity = Decimal(row["price"]), int(row["quantity"])
        if not price.is_finite() or quantity < 0:
            raise ValueError("finite prices and nonnegative integer quantities required")
        amount += price * (quantity if mode == "quantity" else 1)
    return format(amount, ".2f")


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    args: dict


class LabError(Exception):
    """An explicit execution boundary, rather than a hidden model decision."""


class ApprovalRequired(LabError):
    pass


class BudgetExceeded(LabError):
    pass


class InvalidCall(LabError):
    pass


class CallConflict(LabError):
    pass


class TransientFailure(LabError):
    pass


def validate_call(call):
    """A deliberately small schema validator, not a general JSON Schema engine."""
    if not isinstance(call.call_id, str) or not call.call_id:
        raise InvalidCall("call_id must be a nonempty string")
    if not isinstance(call.name, str) or call.name not in TOOLS or not isinstance(call.args, dict):
        raise InvalidCall("unknown tool or non-object arguments")
    schema = TOOLS[call.name]
    if set(call.args) - set(schema["properties"]):
        raise InvalidCall("additional arguments are forbidden")
    if set(schema.get("required", [])) - set(call.args):
        raise InvalidCall("missing required argument")
    for key, value in call.args.items():
        if not isinstance(value, str) or value not in schema["properties"][key]["enum"]:
            raise InvalidCall("argument outside the permitted enum")


def compact_context(context, keep=3):
    """Trim event history while preserving structured obligations verbatim.

    The small lab keeps all four tool results. This is not a general token-budget
    algorithm and does not establish that natural-language summaries are lossless.
    """
    if keep < 1:
        raise ValueError("keep must be positive")
    result = copy.deepcopy(context)
    omitted = max(0, len(result["recent_events"]) - keep)
    result["summary"] = f"省略 {omitted} 条旧事件；状态、约束和工具结果保留在结构化字段中。"
    result["recent_events"] = result["recent_events"][-keep:]
    return result


class ScriptedModel:
    """Deterministic fixture: the repair plan is supplied, not inferred."""

    PLAN = [
        ToolCall("inspect", "inspect", {}),
        ToolCall("test-before", "test_total", {}),
        ToolCall("repair", "set_mode", {"mode": "quantity"}),
        ToolCall("test-after", "test_total", {}),
    ]

    def next_call(self, context):
        completed = {item["call_id"] for item in context["tool_results"]}
        return next((call for call in self.PLAN if call.call_id not in completed), None)


class AgentLab:
    """A single-worker runtime backed by one local SQLite database.

    Workspace changes, effect receipts and successful tool results commit together.
    An attempt is charged in an earlier transaction: crashes cannot refund budget.
    This atomicity does not extend to an external filesystem, API or subprocess.
    """

    def __init__(self, db_path, max_attempts=8, csv_text=DEFAULT_CSV, max_decisions=16):
        if max_attempts < 0 or max_decisions < 0:
            raise ValueError("budgets cannot be negative")
        self.db = sqlite3.connect(str(db_path), isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS run (
                id INTEGER PRIMARY KEY CHECK(id=1), status TEXT NOT NULL,
                max_attempts INTEGER NOT NULL, spent INTEGER NOT NULL,
                max_decisions INTEGER NOT NULL, decisions INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS workspace (
                id INTEGER PRIMARY KEY CHECK(id=1), csv_text TEXT NOT NULL,
                mode TEXT NOT NULL, revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS calls (
                position INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                args TEXT NOT NULL, result TEXT, completed_seq INTEGER);
            CREATE TABLE IF NOT EXISTS effects (
                call_id TEXT PRIMARY KEY, before_revision INTEGER,
                after_revision INTEGER);
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL, payload TEXT NOT NULL);
        """)
        with self.atomic():
            self.db.execute("INSERT OR IGNORE INTO run VALUES (1, 'ready', ?, 0, ?, 0)",
                            (max_attempts, max_decisions))
            self.db.execute("INSERT OR IGNORE INTO workspace VALUES (1, ?, 'unit_only', 0)",
                            (csv_text,))
        # Existing databases retain their CSV and budget, even if defaults differ.

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @contextmanager
    def atomic(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def event(self, kind, **payload):
        return self.db.execute("INSERT INTO events(kind,payload) VALUES (?,?)",
                               (kind, encoded(payload))).lastrowid

    def status(self, value):
        self.db.execute("UPDATE run SET status=? WHERE id=1", (value,))

    def events(self):
        return [dict(seq=row["seq"], kind=row["kind"], **json.loads(row["payload"]))
                for row in self.db.execute("SELECT * FROM events ORDER BY seq")]

    def snapshot(self):
        run = dict(self.db.execute("SELECT * FROM run WHERE id=1").fetchone())
        workspace = dict(self.db.execute("SELECT * FROM workspace WHERE id=1").fetchone())
        return {key: run[key] for key in ("status", "spent", "max_attempts", "decisions", "max_decisions")} | {
            "mode": workspace["mode"], "revision": workspace["revision"],
            "total": total(workspace["csv_text"], workspace["mode"]),
            "effects": self.db.execute("SELECT COUNT(*) FROM effects").fetchone()[0],
        }

    def build_context(self):
        results = [{"call_id": row["call_id"], "name": row["name"],
                    "result": json.loads(row["result"])}
                   for row in self.db.execute("SELECT * FROM calls WHERE result IS NOT NULL ORDER BY completed_seq")]
        pending = [row[0] for row in self.db.execute("SELECT call_id FROM calls WHERE result IS NULL")]
        return {"goal": GOAL, "constraints": list(CONSTRAINTS), "tool_results": results,
                "pending": pending, "state": self.snapshot(), "recent_events": self.events()}

    def execute(self, call, approve_edit=False, fail_once=None, crash_before=None, crash_after=None):
        validate_call(call)
        args = encoded(call.args)
        existing = self.db.execute("SELECT * FROM calls WHERE call_id=?", (call.call_id,)).fetchone()
        if existing:
            if (existing["name"], existing["args"]) != (call.name, args):
                raise CallConflict("a call_id cannot be reused with different tool/arguments")
            if existing["result"] is not None:
                self.event("cache_hit", call_id=call.call_id)
                return json.loads(existing["result"])
        # Approval is deliberately scoped to this exact edit, not arbitrary tools.
        if call.name == "set_mode" and not (approve_edit and call.args == {"mode": "quantity"}):
            with self.atomic():
                self.status("waiting_approval")
                self.event("approval_required", call_id=call.call_id, name=call.name, args=call.args)
            raise ApprovalRequired("explicit approval for set_mode(mode='quantity') required")

        with self.atomic():
            run = self.db.execute("SELECT * FROM run WHERE id=1").fetchone()
            exhausted = run["spent"] >= run["max_attempts"]
            if exhausted:
                self.status("budget_exhausted")
                self.event("budget_exhausted", call_id=call.call_id)
            else:
                self.db.execute("UPDATE run SET spent=spent+1, status='running' WHERE id=1")
                self.db.execute("INSERT OR IGNORE INTO calls(call_id,name,args) VALUES (?,?,?)",
                                (call.call_id, call.name, args))
                self.event("tool_started", call_id=call.call_id, name=call.name)
        if exhausted:
            raise BudgetExceeded("no tool-attempt budget remains")

        if fail_once is not None and call.name in fail_once:
            fail_once.remove(call.name)
            self.event("tool_error", call_id=call.call_id, error="injected transient failure")
            raise TransientFailure("injected before any workspace effect")

        with self.atomic():
            workspace = self.db.execute("SELECT * FROM workspace WHERE id=1").fetchone()
            revision = workspace["revision"]
            if call.name == "inspect":
                result = {"mode": workspace["mode"], "csv": workspace["csv_text"], "revision": revision}
            elif call.name == "test_total":
                actual = total(workspace["csv_text"], workspace["mode"])
                expected = total(workspace["csv_text"], "quantity")
                result = {"actual": actual, "expected": expected, "passed": actual == expected,
                          "revision": revision}
            else:
                self.db.execute("UPDATE workspace SET mode=?, revision=revision+1 WHERE id=1",
                                (call.args["mode"],))
                self.db.execute("INSERT INTO effects VALUES (?,?,?)", (call.call_id, revision, revision + 1))
                result = {"mode": call.args["mode"], "revision": revision + 1}
            completed_seq = self.event("tool_result", call_id=call.call_id, result=result)
            self.db.execute("UPDATE calls SET result=?, completed_seq=? WHERE call_id=?",
                            (encoded(result), completed_seq, call.call_id))
            if crash_before == call.call_id:
                os._exit(86)  # Deliberate process death with an open SQLite transaction.
        if crash_after == call.call_id:
            os._exit(86)  # Result committed, but its caller never receives the return value.
        return result

    def run(self, model=None, approve_edit=False, fail_once=None, crash_before=None, crash_after=None):
        if self.snapshot()["status"] == "completed":
            return self.snapshot()
        model = model or ScriptedModel()
        while True:
            # Cache replays use no new tool attempt, but still consume a decision.
            # Persist before invoking the model so a restart cannot refund a turn.
            with self.atomic():
                run = self.db.execute("SELECT * FROM run WHERE id=1").fetchone()
                if run["decisions"] >= run["max_decisions"]:
                    self.status("decision_budget_exhausted")
                    self.event("decision_budget_exhausted")
                    return self.snapshot()
                self.db.execute("UPDATE run SET decisions=decisions+1 WHERE id=1")
            context = compact_context(self.build_context())
            call = model.next_call(context)
            if call is None:
                tests = [entry["result"] for entry in context["tool_results"] if entry["name"] == "test_total"]
                state = self.snapshot()
                oracle_passed = sum(total(csv_text, state["mode"]) == expected
                                    for _, csv_text, expected in VERIFICATION_CASES)
                verified = bool(not context["pending"] and tests and tests[-1]["passed"] and
                                tests[-1]["revision"] == state["revision"] and
                                oracle_passed == len(VERIFICATION_CASES))
                with self.atomic():
                    self.status("completed" if verified else "failed_verification")
                    self.event("finished", verified=verified, oracle_passed=oracle_passed,
                               oracle_cases=len(VERIFICATION_CASES), pending=context["pending"])
                return self.snapshot()
            try:
                self.execute(call, approve_edit, fail_once, crash_before, crash_after)
            except TransientFailure:
                # A pending call is retried; every real attempt consumes budget.
                continue
            except (ApprovalRequired, BudgetExceeded):
                return self.snapshot()
            except (InvalidCall, CallConflict) as error:
                with self.atomic():
                    self.status("invalid_call")
                    self.event("rejected", error=str(error))
                return self.snapshot()


def evaluate():
    """Small fixture suite, not an LLM benchmark or a general correctness proof."""
    rows = []
    with tempfile.TemporaryDirectory(prefix="agent-lab-eval-") as directory:
        for name, csv_text, expected in VERIFICATION_CASES:
            with AgentLab(Path(directory) / f"{name}.sqlite3", csv_text=csv_text) as lab:
                baseline = lab.snapshot()["total"]
                outcome = lab.run(approve_edit=True)
                rows.append({"case": name, "expected": expected, "baseline": baseline,
                             "actual": outcome["total"], "status": outcome["status"],
                             "passed": outcome["status"] == "completed" and outcome["total"] == expected,
                             "attempts": outcome["spent"]})
    return {"kind": "scripted_workflow_fixture_suite", "cases": len(rows),
            "baseline_passed": sum(row["baseline"] == row["expected"] for row in rows),
            "workflow_passed": sum(row["passed"] for row in rows), "results": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("evaluate")
    demo = sub.add_parser("demo")
    demo.add_argument("--db", help="persistent database; omitted means a fresh, temporary database")
    demo.add_argument("--approve-edit", action="store_true")
    demo.add_argument("--max-attempts", type=int, default=8, help="used only when creating a database")
    demo.add_argument("--max-decisions", type=int, default=16, help="used only when creating a database")
    demo.add_argument("--fail-once", choices=TOOLS)
    demo.add_argument("--crash-before", choices=[call.call_id for call in ScriptedModel.PLAN])
    demo.add_argument("--crash-after", choices=[call.call_id for call in ScriptedModel.PLAN])
    demo.add_argument("--events", action="store_true")
    args = parser.parse_args()
    if args.command == "evaluate":
        print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
        return
    with tempfile.TemporaryDirectory(prefix="agent-lab-demo-") as directory:
        with AgentLab(args.db or Path(directory) / "demo.sqlite3", args.max_attempts,
                      max_decisions=args.max_decisions) as lab:
            outcome = lab.run(approve_edit=args.approve_edit,
                              fail_once={args.fail_once} if args.fail_once else set(),
                              crash_before=args.crash_before, crash_after=args.crash_after)
            print(json.dumps(outcome, ensure_ascii=False, indent=2))
            if args.events:
                for event in lab.events():
                    print(encoded(event))


if __name__ == "__main__":
    main()
