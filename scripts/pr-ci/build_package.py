#!/usr/bin/env python3
# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

from pr_ci_common import (
    append_step_summary,
    bool_to_result,
    common_evidence_manifest,
    env_with,
    relative_existing_files,
    repo_root,
    run_command,
    utc_timestamp,
    write_github_output,
    write_json,
)


BINARY_NAME = "go-app-linux-amd64"
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def normalize_target_version(target_version: str) -> str:
    normalized = target_version.strip()
    while normalized.lower().startswith("v"):
        normalized = normalized[1:]
    return normalized


def build_artifact_version(target_version: str, run_number: str, run_attempt: str) -> str:
    normalized = normalize_target_version(target_version)
    if not normalized:
        return ""
    return f"v{normalized}+b.{run_number}.a.{run_attempt}"


def read_version_file(root: Path) -> str:
    version_path = root / "VERSION"
    if not version_path.exists():
        return ""
    return version_path.read_text(encoding="utf-8").strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as binary_file:
        for chunk in iter(lambda: binary_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_summary(
    *,
    evidence_manifest: dict[str, Any],
    result_payload: dict[str, Any],
) -> str:
    reasons = result_payload["failure_reasons"] or ["なし"]
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    return "\n".join(
        [
            "# build-package Summary",
            "",
            "| Item | Value |",
            "|---|---|",
            f"| Result | `{result_payload['build_package_result']}` |",
            f"| Test run ID | `{evidence_manifest['test_run_id']}` |",
            f"| Pull Request | `#{evidence_manifest['pull_request_number']}` |",
            f"| Head SHA | `{evidence_manifest['pr_head_sha']}` |",
            f"| Issue | `{evidence_manifest['issue_number_or_UNLINKED']}` |",
            f"| target_version | `{evidence_manifest['target_version'] or '<missing>'}` |",
            f"| VERSION | `{result_payload['version_file'] or '<missing>'}` |",
            f"| required_final_stage | `{evidence_manifest['required_final_stage'] or '<missing>'}` |",
            f"| Evidence Artifact | `{evidence_manifest['artifact_name']}` |",
            f"| Build Artifact | `{result_payload['build_artifact_name']}` |",
            f"| Build Artifact version | `{result_payload['build_artifact_version'] or '<missing>'}` |",
            f"| Binary checksum | `{result_payload['binary_sha256'] or '<missing>'}` |",
            "",
            "## Failure reasons",
            "",
            reason_lines,
            "",
        ]
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Lesson 5.3 temporary Go app artifact.")
    parser.add_argument("--build-output-dir", required=True)
    parser.add_argument("--evidence-output-dir", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-run-number", required=True)
    parser.add_argument("--workflow-run-attempt", required=True)
    parser.add_argument("--job-name", default="build-package")
    parser.add_argument("--test-run-id", required=True)
    parser.add_argument("--issue-number", required=True)
    parser.add_argument("--target-version", required=True)
    parser.add_argument("--required-final-stage", required=True)
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--pr-head-ref", required=True)
    parser.add_argument("--pr-head-sha", required=True)
    parser.add_argument("--github-output")
    parser.add_argument("--github-step-summary")
    parser.add_argument("--created-at")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = repo_root()
    app_dir = root / "app"
    build_dir = Path(args.build_output_dir)
    evidence_dir = Path(args.evidence_output_dir)
    logs_dir = evidence_dir / "logs"
    build_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    created_at = utc_timestamp(args.created_at)
    evidence_artifact_name = f"evidence-build-package_{args.test_run_id}"
    build_artifact_name = f"build-go-app_{args.test_run_id}"
    version = build_artifact_version(
        args.target_version,
        args.workflow_run_number,
        args.workflow_run_attempt,
    )
    normalized_target_version = normalize_target_version(args.target_version)
    version_file_value = read_version_file(root)

    failure_reasons: list[str] = []
    if not version:
        failure_reasons.append("target_version is missing; build_artifact_version cannot be generated")
    if not version_file_value:
        failure_reasons.append("VERSION file is missing or empty")
    elif not SEMVER_PATTERN.match(version_file_value):
        failure_reasons.append(f"VERSION must be X.Y.Z. actual={version_file_value}")
    elif version_file_value != normalized_target_version:
        failure_reasons.append(
            "VERSION does not match target_version. "
            f"VERSION={version_file_value} target_version={args.target_version}"
        )

    go_version_result = run_command(["go", "version"], cwd=app_dir, log_path=logs_dir / "go-version.log")
    go_version = go_version_result["stdout"].strip()
    if go_version_result["returncode"] != 0:
        failure_reasons.append(f"go version exited with rc={go_version_result['returncode']}")

    binary_path = build_dir / BINARY_NAME
    build_result: dict[str, Any] = {
        "command": [],
        "returncode": 1,
        "log_path": "logs/go-build.log",
    }
    if not failure_reasons:
        build_result = run_command(
            [
                "go",
                "build",
                "-trimpath",
                "-ldflags",
                f"-s -w -X main.version={version}",
                "-o",
                str(binary_path),
                ".",
            ],
            cwd=app_dir,
            log_path=logs_dir / "go-build.log",
            env=env_with({"CGO_ENABLED": "0", "GOOS": "linux", "GOARCH": "amd64"}),
        )
        if build_result["returncode"] != 0:
            failure_reasons.append(f"go build exited with rc={build_result['returncode']}")
    else:
        (logs_dir / "go-build.log").write_text(
            "go build was not executed because build prerequisites were not met.\n",
            encoding="utf-8",
        )

    binary_sha256 = ""
    if binary_path.exists():
        try:
            binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass
        binary_sha256 = sha256_file(binary_path)
        (build_dir / f"{BINARY_NAME}.sha256").write_text(
            f"{binary_sha256}  {BINARY_NAME}\n",
            encoding="utf-8",
        )
    elif not any("go build exited" in reason for reason in failure_reasons):
        failure_reasons.append(f"{BINARY_NAME} was not created")

    build_package_result = bool_to_result(not failure_reasons)
    build_manifest = {
        "test_run_id": args.test_run_id,
        "issue_number": args.issue_number,
        "target_version": args.target_version,
        "version_file": version_file_value,
        "required_final_stage": args.required_final_stage,
        "build_artifact_version": version,
        "repository": args.repository,
        "pr_number": args.pr_number,
        "head_ref": args.pr_head_ref,
        "head_sha": args.pr_head_sha,
        "workflow_run_id": args.workflow_run_id,
        "workflow_run_attempt": args.workflow_run_attempt,
        "go_version": go_version,
        "binary_name": BINARY_NAME,
        "binary_sha256": binary_sha256,
        "created_at": created_at,
        "artifact_name": build_artifact_name,
        "artifact_scope": "ms3_temporary_pr_ci",
        "version_check": {
            "normalized_target_version": normalized_target_version,
            "version_file": version_file_value,
            "result": "success"
            if version_file_value
            and SEMVER_PATTERN.match(version_file_value)
            and version_file_value == normalized_target_version
            else "failure",
        },
    }
    write_json(build_dir / "manifest.json", build_manifest)

    result_payload = {
        "build_package_result": build_package_result,
        "failure_reasons": failure_reasons,
        "go_version": go_version,
        "build_command": build_result["command"],
        "build_returncode": build_result["returncode"],
        "build_log_path": "logs/go-build.log",
        "build_artifact_name": build_artifact_name,
        "build_artifact_version": version,
        "version_file": version_file_value,
        "normalized_target_version": normalized_target_version,
        "binary_name": BINARY_NAME,
        "binary_sha256": binary_sha256,
        "build_manifest": "build-artifact/manifest.json",
    }

    expected_evidence = [
        "manifest.json",
        "summary.md",
        "build-package-result.json",
        "logs/go-version.log",
        "logs/go-build.log",
    ]
    write_json(evidence_dir / "build-package-result.json", result_payload)
    collected_evidence = relative_existing_files(evidence_dir, expected_evidence)
    for generated_file in ("manifest.json", "summary.md"):
        if generated_file not in collected_evidence:
            collected_evidence.append(generated_file)
    evidence_manifest = common_evidence_manifest(
        test_run_id=args.test_run_id,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
        job_name=args.job_name,
        pr_number=args.pr_number,
        issue_number=args.issue_number,
        pr_head_sha=args.pr_head_sha,
        repository=args.repository,
        artifact_name=evidence_artifact_name,
        generated_timestamp=created_at,
        expected_evidence=expected_evidence,
        collected_evidence=collected_evidence,
        result=build_package_result,
        target_version=args.target_version,
        required_final_stage=args.required_final_stage,
    )
    write_json(evidence_dir / "manifest.json", evidence_manifest)
    summary = build_summary(evidence_manifest=evidence_manifest, result_payload=result_payload)
    (evidence_dir / "summary.md").write_text(summary, encoding="utf-8")

    write_github_output(
        args.github_output,
        {
            "build_package_result": build_package_result,
            "build_artifact_name": build_artifact_name,
            "build_artifact_version": version,
            "build_artifact_checksum": binary_sha256,
            "evidence_artifact_name": evidence_artifact_name,
            "failure_reason_count": len(failure_reasons),
        },
    )
    append_step_summary(args.github_step_summary, summary)
    print(summary)
    return 0 if build_package_result == "success" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
