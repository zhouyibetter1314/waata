"""Summarize existing local Discourse data; never access model or target site."""

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/discourse"
ACTIONS = {"browser.navigate", "browser.click", "browser.fill", "browser.select_option"}


def summarize(source, output):
    rows = []
    for path in source.glob("*/report.json"):
        raw = path.read_bytes()
        report = json.loads(raw)
        result = report.get("run") or {}
        recheck_path = LOCAL / "rechecks" / report["run_id"] / "verification.json"
        recheck = (
            json.loads(recheck_path.read_text(encoding="utf-8"))
            if recheck_path.exists()
            else None
        )
        completions = [
            event["payload"]
            for event in report["events"]
            if event["type"] == "tool.completed"
        ]
        actions = [item for item in completions if item.get("tool") in ACTIONS]
        rows.append(
            {
                "scene": report["scene"],
                "run_id": report["run_id"],
                "recorded_at": report["started_at"],
                "model": report["model"],
                "prepared_login": report["prepared_login"],
                "fixture_tag": report["fixture"]["tag"],
                "harness_version": report.get("harness_version", 1),
                "status": result.get("status"),
                "agent_verdict": result.get("verdict"),
                "independent_reported_passed": report["independent"]["passed"],
                "rechecked_passed": recheck["independent"]["passed"]
                if recheck
                else None,
                "local_recheck": recheck_path.relative_to(ROOT).as_posix()
                if recheck
                else None,
                "error_code": (result.get("error") or {}).get("code"),
                "seconds": report["seconds"],
                "completed_model_responses": report["requests"],
                "reported_tokens": report["paid_tokens"],
                "action_calls": len(actions),
                "failed_action_calls": sum(not item["success"] for item in actions),
                "artifacts": len(result.get("artifacts", [])),
                "screenshots": sum(
                    item["kind"] == "screenshot" for item in result.get("artifacts", [])
                ),
                "stage_count": len(report.get("stages", [])),
                "local_report": path.relative_to(ROOT).as_posix(),
                "report_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    rows.sort(key=lambda row: row["recorded_at"])
    totals = {
        "runs": len(rows),
        "statuses": dict(Counter(row["status"] for row in rows)),
        "agent_verdicts": dict(Counter(row["agent_verdict"] or "null" for row in rows)),
        "completed_model_responses": sum(
            row["completed_model_responses"] for row in rows
        ),
        "reported_tokens": sum(row["reported_tokens"] for row in rows),
        "sum_run_seconds": round(sum(row["seconds"] for row in rows), 2),
        "action_calls": sum(row["action_calls"] for row in rows),
        "failed_action_calls": sum(row["failed_action_calls"] for row in rows),
        "max_action_calls_per_run": max(
            (row["action_calls"] for row in rows), default=0
        ),
        "artifacts": sum(row["artifacts"] for row in rows),
        "screenshots": sum(row["screenshots"] for row in rows),
    }
    data = {
        "scope": "Existing Discourse reports only; no new test execution",
        "notes": [
            "Agent verdict is preserved, not endorsed as full scenario acceptance.",
            "Independent raw booleans include page-readiness failures; see integration report.",
            "Tokens exclude connection probes and responses absent from captured reports.",
            "Completed model responses exclude failed HTTP calls.",
            "Action calls include errors before dispatch; count is an upper bound.",
            "Run seconds overlap for parallel runs and are not wall-clock duration.",
            "Earliest two recorded timestamps were captured after execution.",
        ],
        "totals": totals,
        "runs": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "run-index.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if rows:
        with (output / "run-index.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
    # A file-by-file digest index stays local. Do not copy prompts/raw traces to Git.
    inventory = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(source.rglob("*"))
        if path.is_file()
    ]
    (LOCAL / "artifact-inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )
    db_path = LOCAL / "qa.sqlite"
    if db_path.exists():
        with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as db:
            ids = {row[0] for row in db.execute("SELECT run_id FROM runs")}
        if ids != {row["run_id"] for row in rows}:
            raise ValueError("SQLite and report directory contain different Run IDs")
        rechecks = [row for row in rows if row["local_recheck"]]
        if rechecks:
            # Keep additional verification separate from immutable Run reports.
            with sqlite3.connect(db_path) as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS verifications (run_id TEXT PRIMARY KEY, verification_json TEXT NOT NULL, report_path TEXT NOT NULL)"
                )
                for row in rechecks:
                    path = ROOT / row["local_recheck"]
                    db.execute(
                        "INSERT OR REPLACE INTO verifications VALUES (?, ?, ?)",
                        (
                            row["run_id"],
                            path.read_text(encoding="utf-8"),
                            row["local_recheck"],
                        ),
                    )
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=LOCAL / "runs")
    parser.add_argument("--output", type=Path, default=LOCAL / "summary")
    args = parser.parse_args()
    summarize(args.source, args.output)
