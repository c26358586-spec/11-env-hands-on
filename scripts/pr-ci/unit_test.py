#!/usr/bin/env python3
# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pr_ci_common import (
    append_step_summary,
    bool_to_result,
    common_evidence_manifest,
    relative_existing_files,
    repo_root,
    run_command,
    utc_timestamp,
    write_github_output,
    write_json,
)


def build_summary(*, manifest: dict[str, Any], result_payload: dict[str, Any]) -> str:
    reasons = result_payload["failure_reasons"] or ["なし"]
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    return "\n".join(
        [
            "# unit-test Summary",
            "",
            "| Item | Value |",
            "|---|---|",
            f"| Result | `{result_payload['unit_test_result']}` |",
            f"| Test run ID | `{manifest['test_run_id']}` |",
            f"| Pull Request | `#{manifest['pull_request_number']}` |",
            f"| Head SHA | `{manifest['pr_head_sha']}` |",
            f"| Issue | `{manifest['issue_number_or_UNLINKED']}` |",
            f"| target_version | `{manifest['target_version'] or '<missing>'}` |",
            f"| required_final_stage | `{manifest['required_final_stage'] or '<missing>'}` |",
            f"| Evidence Artifact | `{manifest['artifact_name']}` |",
            f"| JUnit XML | `{result_payload['junit_xml']}` |",
            "",
            "## Failure reasons",
            "",
            reason_lines,
            "",
        ]
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Lesson 5.3 Go unit tests.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-run-attempt", required=True)
    parser.add_argument("--job-name", default="unit-test")
    parser.add_argument("--test-run-id", required=True)
    parser.add_argument("--issue-number", required=True)
    parser.add_argument("--target-version", required=True)
    parser.add_argument("--required-final-stage", required=True)
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--pr-head-sha", required=True)
    parser.add_argument("--github-output")
    parser.add_argument("--github-step-summary")
    parser.add_argument("--created-at")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = repo_root()
    app_dir = root / "app"
    output_dir = Path(args.output_dir)
    junit_dir = output_dir / "junit"
    logs_dir = output_dir / "logs"
    junit_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    junit_path = junit_dir / "go-unit.xml"
    created_at = utc_timestamp(args.created_at)
    artifact_name = f"evidence-unit-test_{args.test_run_id}"

    command_result = run_command(
        [
            "gotestsum",
            "--junitfile",
            str(junit_path),
            "--format",
            "standard-verbose",
            "--",
            "./...",
        ],
        cwd=app_dir,
        log_path=logs_dir / "go-test.log",
    )

    failure_reasons: list[str] = []
    if command_result["returncode"] != 0:
        failure_reasons.append(f"gotestsum exited with rc={command_result['returncode']}")
    if not junit_path.exists():
        failure_reasons.append("JUnit XML was not created at junit/go-unit.xml")

    unit_test_result = bool_to_result(not failure_reasons)
    result_payload = {
        "unit_test_result": unit_test_result,
        "failure_reasons": failure_reasons,
        "command": command_result["command"],
        "returncode": command_result["returncode"],
        "log_path": "logs/go-test.log",
        "junit_xml": "junit/go-unit.xml" if junit_path.exists() else "<missing>",
    }

    expected_evidence = [
        "manifest.json",
        "summary.md",
        "unit-test-result.json",
        "logs/go-test.log",
        "junit/go-unit.xml",
    ]
    write_json(output_dir / "unit-test-result.json", result_payload)
    collected_evidence = relative_existing_files(output_dir, expected_evidence)
    for generated_file in ("manifest.json", "summary.md"):
        if generated_file not in collected_evidence:
            collected_evidence.append(generated_file)
    manifest = common_evidence_manifest(
        test_run_id=args.test_run_id,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
        job_name=args.job_name,
        pr_number=args.pr_number,
        issue_number=args.issue_number,
        pr_head_sha=args.pr_head_sha,
        repository=args.repository,
        artifact_name=artifact_name,
        generated_timestamp=created_at,
        expected_evidence=expected_evidence,
        collected_evidence=collected_evidence,
        result=unit_test_result,
        target_version=args.target_version,
        required_final_stage=args.required_final_stage,
    )
    write_json(output_dir / "manifest.json", manifest)
    summary = build_summary(manifest=manifest, result_payload=result_payload)
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")

    write_github_output(
        args.github_output,
        {
            "unit_test_result": unit_test_result,
            "evidence_artifact_name": artifact_name,
            "failure_reason_count": len(failure_reasons),
        },
    )
    append_step_summary(args.github_step_summary, summary)
    print(summary)
    return 0 if unit_test_result == "success" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
