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


def classify_gofmt(returncode: int, stdout: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    unformatted = (
        [line.strip() for line in stdout.splitlines() if line.strip()]
        if returncode == 0
        else []
    )
    if returncode != 0:
        reasons.append(f"gofmt -l exited with rc={returncode}")
    if unformatted:
        reasons.append("gofmt is required for: " + ", ".join(unformatted))
    return bool_to_result(not reasons), reasons


def classify_returncode(tool_name: str, returncode: int) -> tuple[str, list[str]]:
    if returncode == 0:
        return "success", []
    return "failure", [f"{tool_name} exited with rc={returncode}"]


def build_summary(
    *,
    manifest: dict[str, Any],
    result_payload: dict[str, Any],
) -> str:
    reasons = result_payload["failure_reasons"] or ["なし"]
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    return "\n".join(
        [
            "# static-analysis Summary",
            "",
            "| Item | Value |",
            "|---|---|",
            f"| Result | `{result_payload['static_analysis_result']}` |",
            f"| Test run ID | `{manifest['test_run_id']}` |",
            f"| Pull Request | `#{manifest['pull_request_number']}` |",
            f"| Head SHA | `{manifest['pr_head_sha']}` |",
            f"| Issue | `{manifest['issue_number_or_UNLINKED']}` |",
            f"| target_version | `{manifest['target_version'] or '<missing>'}` |",
            f"| required_final_stage | `{manifest['required_final_stage'] or '<missing>'}` |",
            f"| Evidence Artifact | `{manifest['artifact_name']}` |",
            f"| gofmt | `{result_payload['checks']['gofmt']['result']}` |",
            f"| go vet | `{result_payload['checks']['go_vet']['result']}` |",
            "",
            "## Failure reasons",
            "",
            reason_lines,
            "",
        ]
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Lesson 5.3 Go app static analysis.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-run-attempt", required=True)
    parser.add_argument("--job-name", default="static-analysis")
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
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = output_dir / "logs"
    created_at = utc_timestamp(args.created_at)
    artifact_name = f"evidence-static-analysis_{args.test_run_id}"

    gofmt = run_command(["gofmt", "-l", "."], cwd=app_dir, log_path=logs_dir / "gofmt.log")
    gofmt_result, gofmt_reasons = classify_gofmt(gofmt["returncode"], gofmt["stdout"])
    unformatted_files = (
        [line.strip() for line in gofmt["stdout"].splitlines() if line.strip()]
        if gofmt["returncode"] == 0
        else []
    )
    gofmt_diff = None
    if unformatted_files:
        gofmt_diff = run_command(
            ["gofmt", "-d", "."],
            cwd=app_dir,
            log_path=logs_dir / "gofmt.log",
            append=True,
        )

    go_vet = run_command(["go", "vet", "./..."], cwd=app_dir, log_path=logs_dir / "go-vet.log")
    go_vet_result, go_vet_reasons = classify_returncode("go vet ./...", go_vet["returncode"])

    failure_reasons = [*gofmt_reasons, *go_vet_reasons]
    static_analysis_result = bool_to_result(not failure_reasons)

    result_payload = {
        "static_analysis_result": static_analysis_result,
        "failure_reasons": failure_reasons,
        "checks": {
            "gofmt": {
                "result": gofmt_result,
                "returncode": gofmt["returncode"],
                "log_path": "logs/gofmt.log",
                "unformatted_files": unformatted_files,
                "diff_generated": gofmt_diff is not None,
                "diff_returncode": gofmt_diff["returncode"] if gofmt_diff else None,
            },
            "go_vet": {
                "result": go_vet_result,
                "returncode": go_vet["returncode"],
                "log_path": "logs/go-vet.log",
            },
        },
    }

    expected_evidence = [
        "manifest.json",
        "summary.md",
        "static-analysis-result.json",
        "logs/gofmt.log",
        "logs/go-vet.log",
    ]
    write_json(output_dir / "static-analysis-result.json", result_payload)
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
        result=static_analysis_result,
        target_version=args.target_version,
        required_final_stage=args.required_final_stage,
    )
    write_json(output_dir / "manifest.json", manifest)
    summary = build_summary(manifest=manifest, result_payload=result_payload)
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")

    write_github_output(
        args.github_output,
        {
            "static_analysis_result": static_analysis_result,
            "evidence_artifact_name": artifact_name,
            "failure_reason_count": len(failure_reasons),
        },
    )
    append_step_summary(args.github_step_summary, summary)
    print(summary)
    return 0 if static_analysis_result == "success" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
