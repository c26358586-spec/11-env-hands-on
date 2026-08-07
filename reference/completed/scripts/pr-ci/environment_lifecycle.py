#!/usr/bin/env python3
# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

from __future__ import annotations

import argparse
import hashlib
import os
import json
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from pr_ci_common import (
    append_step_summary,
    common_evidence_manifest,
    relative_existing_files,
    repo_root,
    utc_timestamp,
    write_github_output,
    write_json,
)


EXPECTED_EVIDENCE = [
    "manifest.json",
    "environment-lifecycle-result.json",
    "summary.md",
    "logs/terraform-plan.log",
    "logs/terraform-apply.log",
    "logs/terraform-destroy.log",
    "logs/ansible.log",
    "logs/startup-connectivity-check.log",
    "logs/cleanup.log",
    "logs/residue-verification.log",
    "logs/docker-state-before-cleanup.txt",
    "logs/docker-state-after-cleanup.txt",
    "logs/nginx.log",
    "logs/go-app.log",
    "logs/infrastructure-test.log",
    "logs/api-test.log",
    "test-results/infrastructure-test-junit.xml",
    "test-results/api-test-junit.xml",
    "test-results/infrastructure-test-result.json",
    "test-results/api-test-result.json",
    "summaries/infrastructure-test-summary.md",
    "summaries/api-test-summary.md",
]

INFRASTRUCTURE_TEST_RESULT_FILES = [
    "test-results/infrastructure-test-junit.xml",
    "test-results/infrastructure-test-result.json",
    "summaries/infrastructure-test-summary.md",
]
API_TEST_RESULT_FILES = [
    "test-results/api-test-junit.xml",
    "test-results/api-test-result.json",
    "summaries/api-test-summary.md",
]
FORMAL_TEST_CASE_IDS = {
    "infrastructure": [f"INF-{index:03d}" for index in range(1, 10)],
    "api": [f"API-{index:03d}" for index in range(1, 5)],
}

MANAGED_BY = "github-actions-pr-ci"
ENVIRONMENT_PATTERN_ID = "UT"
APP_BINARY_PATH = "/opt/ms1-app/bin/ms1-app"
APP_PID_PATH = "/run/ms1-app/app.pid"
APP_PORT = 8080
NGINX_PORT = 80


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str


@dataclass
class LifecycleState:
    failure_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detected_missing_evidence: list[str] = field(default_factory=list)
    evidence_missing_reasons: list[str] = field(default_factory=list)
    prerequisites_met: bool = False
    upstream_ready: bool = False
    artifact_ready: bool = False
    environment_face_id: str = ""
    environment_creation_state: str = "NotStarted"
    readiness_check_execution_state: str = "NotStarted"
    readiness_check_result: str = "FailedBeforeCheck"
    test_execution_state: str = "NotStarted"
    overall_test_result: str = "FailedBeforeTest"
    infrastructure_test_execution_state: str = "NotStarted"
    infrastructure_test_result: str = "FailedBeforeTest"
    api_test_execution_state: str = "NotStarted"
    api_test_result: str = "FailedBeforeTest"
    cleanup_state: str = "NotAttempted"
    cleanup_warning: bool = False
    cleanup_target_count: int = 0
    remaining_resource_count: int = 0
    cleanup_targets: list[str] = field(default_factory=list)
    remaining_resource_identifiers: list[str] = field(default_factory=list)
    cleanup_started_at: str = ""
    cleanup_finished_at: str = ""
    cleanup_attempted: bool = False
    environment_resources_may_exist: bool = False
    residue_verification_result: str = "NotStarted"
    environment_lifecycle_result: str = "failure"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Lesson 5.5 disposable UT environment lifecycle."
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--build-artifact-dir", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-run-attempt", required=True)
    parser.add_argument("--job-name", default="environment-lifecycle")
    parser.add_argument("--test-run-id", required=True)
    parser.add_argument("--issue-number", required=True)
    parser.add_argument("--target-version", required=True)
    parser.add_argument("--required-final-stage", required=True)
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--pr-head-sha", required=True)
    parser.add_argument("--governance-job-result", required=True)
    parser.add_argument("--governance-result", required=True)
    parser.add_argument("--static-analysis-job-result", required=True)
    parser.add_argument("--static-analysis-result", required=True)
    parser.add_argument("--unit-test-job-result", required=True)
    parser.add_argument("--unit-test-result", required=True)
    parser.add_argument("--build-package-job-result", required=True)
    parser.add_argument("--build-package-result", required=True)
    parser.add_argument("--build-artifact-name", required=True)
    parser.add_argument("--build-artifact-id", required=True)
    parser.add_argument("--build-artifact-version", required=True)
    parser.add_argument("--build-artifact-checksum", required=True)
    parser.add_argument("--build-artifact-uploaded", required=True)
    parser.add_argument("--host-http-port", default="18080")
    parser.add_argument("--github-output")
    parser.add_argument("--github-step-summary")
    parser.add_argument("--created-at")
    return parser.parse_args(argv)


def normalize_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def sanitize_docker_name(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9_.-]+", "-", value.lower())
    sanitized = sanitized.strip(".-")
    return sanitized or "ut-environment"


def environment_face_id(issue_number: str, workflow_run_id: str, run_attempt: str) -> str:
    return f"UT-{issue_number}-{workflow_run_id}-A{run_attempt}"


def derive_overall_test_result(state: LifecycleState) -> str:
    if (
        state.readiness_check_result == "Passed"
        and state.infrastructure_test_result == "Passed"
        and state.api_test_result == "Passed"
    ):
        return "Passed"
    if (
        state.readiness_check_result == "FailedBeforeCheck"
        and state.infrastructure_test_result == "FailedBeforeTest"
        and state.api_test_result == "FailedBeforeTest"
    ):
        return "FailedBeforeTest"
    return "Failed"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as binary_file:
        for chunk in iter(lambda: binary_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(message)
        if not message.endswith("\n"):
            log_file.write("\n")


def write_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(message if message.endswith("\n") else message + "\n", encoding="utf-8")


def record_missing_evidence(state: LifecycleState, relative_path: str, reason: str) -> None:
    if relative_path not in state.detected_missing_evidence:
        state.detected_missing_evidence.append(relative_path)
    state.evidence_missing_reasons.append(f"{relative_path}: {reason}")


def write_junit_placeholder(
    path: Path,
    *,
    suite_name: str,
    case_name: str,
    result: str,
    message: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    failures = "1" if result == "Failed" else "0"
    skipped = "1" if result in ("Skipped", "FailedBeforeTest") else "0"
    suite = ET.Element(
        "testsuite",
        {
            "name": suite_name,
            "tests": "1",
            "failures": failures,
            "errors": "0",
            "skipped": skipped,
        },
    )
    case = ET.SubElement(
        suite,
        "testcase",
        {
            "classname": suite_name,
            "name": case_name,
        },
    )
    if result == "Failed":
        failure = ET.SubElement(case, "failure", {"message": message})
        failure.text = message
    elif result in ("Skipped", "FailedBeforeTest"):
        skipped_element = ET.SubElement(case, "skipped", {"message": message})
        skipped_element.text = message
    tree = ET.ElementTree(suite)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def empty_formal_test_analysis(expected_case_ids: list[str]) -> dict[str, Any]:
    return {
        "counts": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
        },
        "expected_case_ids": expected_case_ids,
        "collected_case_ids": [],
        "missing_case_ids": expected_case_ids,
        "unexpected_case_ids": [],
        "duplicate_case_ids": [],
        "property_missing_cases": [],
        "test_cases": [],
    }


def short_junit_message(element: ET.Element | None) -> str:
    if element is None:
        return ""
    message = element.attrib.get("message", "").strip()
    if not message:
        message = (element.text or "").strip().splitlines()[0] if (element.text or "").strip() else ""
    return message[:240]


def parse_junit_results(junit_path: Path, expected_case_ids: list[str]) -> dict[str, Any]:
    root = ET.parse(junit_path).getroot()
    test_cases: list[dict[str, Any]] = []
    collected_case_ids: list[str] = []
    property_missing_cases: list[str] = []
    counts = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}

    for case in (element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "testcase"):
        counts["total"] += 1
        classname = case.attrib.get("classname", "")
        name = case.attrib.get("name", "")
        case_label = f"{classname}::{name}" if classname else name
        test_case_id = ""
        for prop in (element for element in case.iter() if element.tag.rsplit("}", 1)[-1] == "property"):
            if prop.attrib.get("name") == "test_case_id":
                test_case_id = prop.attrib.get("value", "").strip()
                break
        if test_case_id:
            collected_case_ids.append(test_case_id)
        else:
            property_missing_cases.append(case_label)

        failure = next(
            (child for child in case if child.tag.rsplit("}", 1)[-1] == "failure"),
            None,
        )
        error = next(
            (child for child in case if child.tag.rsplit("}", 1)[-1] == "error"),
            None,
        )
        skipped = next(
            (child for child in case if child.tag.rsplit("}", 1)[-1] == "skipped"),
            None,
        )
        if failure is not None:
            result = "Failed"
            counts["failed"] += 1
            message = short_junit_message(failure)
        elif error is not None:
            result = "Error"
            counts["errors"] += 1
            message = short_junit_message(error)
        elif skipped is not None:
            result = "Skipped"
            counts["skipped"] += 1
            message = short_junit_message(skipped)
        else:
            result = "Passed"
            counts["passed"] += 1
            message = ""
        try:
            duration = float(case.attrib.get("time", "0") or 0)
        except ValueError:
            duration = 0.0
        test_cases.append(
            {
                "test_case_id": test_case_id,
                "name": name,
                "result": result,
                "duration_seconds": duration,
                "message": message,
            }
        )

    seen: set[str] = set()
    duplicate_case_ids: list[str] = []
    for case_id in collected_case_ids:
        if case_id in seen and case_id not in duplicate_case_ids:
            duplicate_case_ids.append(case_id)
        seen.add(case_id)
    expected_set = set(expected_case_ids)
    collected_set = set(collected_case_ids)
    return {
        "counts": counts,
        "expected_case_ids": expected_case_ids,
        "collected_case_ids": collected_case_ids,
        "missing_case_ids": [case_id for case_id in expected_case_ids if case_id not in collected_set],
        "unexpected_case_ids": list(dict.fromkeys(
            case_id for case_id in collected_case_ids if case_id not in expected_set
        )),
        "duplicate_case_ids": duplicate_case_ids,
        "property_missing_cases": property_missing_cases,
        "test_cases": test_cases,
    }


def junit_integrity_reasons(analysis: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if analysis["missing_case_ids"]:
        reasons.append("expected test case IDs are missing: " + ", ".join(analysis["missing_case_ids"]))
    if analysis["unexpected_case_ids"]:
        reasons.append("unexpected test case IDs were collected: " + ", ".join(analysis["unexpected_case_ids"]))
    if analysis["duplicate_case_ids"]:
        reasons.append("duplicate test case IDs were collected: " + ", ".join(analysis["duplicate_case_ids"]))
    if analysis["property_missing_cases"]:
        reasons.append(
            "test_case_id property is missing for: "
            + ", ".join(analysis["property_missing_cases"])
        )
    return reasons


def write_test_result_artifacts(
    *,
    output_dir: Path,
    test_key: str,
    title: str,
    execution_state: str,
    result: str,
    command: list[str],
    returncode: int | None,
    log_path: str,
    junit_path: str,
    result_path: str,
    summary_path: str,
    failure_reasons: list[str],
    junit_analysis: dict[str, Any],
    execution_mode: str,
    skipped_reason: str = "",
) -> dict[str, Any]:
    payload = {
        "execution_state": execution_state,
        "result": result,
        "command": command,
        "returncode": returncode,
        "log_path": log_path,
        "junit_xml": junit_path if (output_dir / junit_path).exists() else "<missing>",
        "summary": summary_path,
        "failure_reasons": failure_reasons,
        "skipped_reason": skipped_reason,
        "execution_mode": execution_mode,
        **junit_analysis,
    }
    write_json(output_dir / result_path, payload)

    reasons = failure_reasons or ([skipped_reason] if skipped_reason else ["なし"])
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    case_rows = [
        "| Test case ID | Result | Name | Duration (s) | Message |",
        "|---|---|---|---:|---|",
    ]
    for case in junit_analysis["test_cases"]:
        message = case["message"].replace("|", "\\|")
        case_rows.append(
            f"| `{case['test_case_id'] or '<missing>'}` | `{case['result']}` | "
            f"`{case['name']}` | `{case['duration_seconds']}` | {message or '-'} |"
        )
    if not junit_analysis["test_cases"]:
        case_rows.append("| `<not-run>` | `<not-run>` | `<not-run>` | `0` | Formal test was not executed. |")
    counts = junit_analysis["counts"]
    summary = "\n".join(
        [
            f"# {title} Summary",
            "",
            "| Item | Value |",
            "|---|---|",
            f"| Execution state | `{execution_state}` |",
            f"| Result | `{result}` |",
            f"| Return code | `{returncode if returncode is not None else '<not-run>'}` |",
            f"| Execution mode | `{execution_mode}` |",
            f"| Expected case count | `{len(junit_analysis['expected_case_ids'])}` |",
            f"| Collected case count | `{len(junit_analysis['collected_case_ids'])}` |",
            f"| Passed | `{counts['passed']}` |",
            f"| Failed | `{counts['failed']}` |",
            f"| Errors | `{counts['errors']}` |",
            f"| Skipped | `{counts['skipped']}` |",
            f"| Log | `{log_path}` |",
            f"| JUnit XML | `{payload['junit_xml']}` |",
            "",
            "## Case results",
            "",
            *case_rows,
            "",
            "## Reasons",
            "",
            reason_lines,
            "",
        ]
    )
    (output_dir / summary_path).parent.mkdir(parents=True, exist_ok=True)
    (output_dir / summary_path).write_text(summary, encoding="utf-8")
    return payload


def write_skipped_test_artifacts(
    *,
    output_dir: Path,
    test_key: str,
    title: str,
    result: str,
    reason: str,
) -> dict[str, Any]:
    junit_path = f"test-results/{test_key}-test-junit.xml"
    result_path = f"test-results/{test_key}-test-result.json"
    summary_path = f"summaries/{test_key}-test-summary.md"
    log_path = f"logs/{test_key}-test.log"
    write_log(output_dir / log_path, reason)
    write_junit_placeholder(
        output_dir / junit_path,
        suite_name=f"{test_key}-test",
        case_name=f"{test_key}_test_not_run",
        result=result,
        message=reason,
    )
    return write_test_result_artifacts(
        output_dir=output_dir,
        test_key=test_key,
        title=title,
        execution_state="Skipped",
        result=result,
        command=[],
        returncode=None,
        log_path=log_path,
        junit_path=junit_path,
        result_path=result_path,
        summary_path=summary_path,
        failure_reasons=[],
        junit_analysis=empty_formal_test_analysis(FORMAL_TEST_CASE_IDS[test_key]),
        execution_mode="not_run_placeholder",
        skipped_reason=reason,
    )


def ensure_unstarted_test_artifacts(output_dir: Path, state: LifecycleState) -> None:
    reason = "Formal tests did not start because environment lifecycle failed before test execution."
    if state.readiness_check_execution_state == "NotStarted":
        state.readiness_check_execution_state = "Skipped"
        state.readiness_check_result = "FailedBeforeCheck"
    if state.infrastructure_test_execution_state == "NotStarted":
        write_skipped_test_artifacts(
            output_dir=output_dir,
            test_key="infrastructure",
            title="infrastructure-test",
            result="FailedBeforeTest",
            reason=reason,
        )
        state.infrastructure_test_execution_state = "Skipped"
        state.infrastructure_test_result = "FailedBeforeTest"
    if state.api_test_execution_state == "NotStarted":
        write_skipped_test_artifacts(
            output_dir=output_dir,
            test_key="api",
            title="api-test",
            result="FailedBeforeTest",
            reason=reason,
        )
        state.api_test_execution_state = "Skipped"
        state.api_test_result = "FailedBeforeTest"
    state.overall_test_result = derive_overall_test_result(state)


def run_command(
    args: list[str],
    *,
    cwd: Path,
    log_path: Path,
    append: bool = False,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            check=False,
        )
        result = CommandResult(args, completed.returncode, completed.stdout or "")
    except OSError as exc:
        result = CommandResult(args, 127, f"ERROR: failed to execute {args[0]}: {exc}\n")

    serialized = f"$ {' '.join(args)}\n{result.stdout}"
    if append:
        append_log(log_path, serialized)
    else:
        write_log(log_path, serialized)

    if check and result.returncode != 0:
        raise RuntimeError(f"{args[0]} exited with rc={result.returncode}")
    return result


def docker_available(root: Path, log_path: Path) -> bool:
    result = run_command(["docker", "version"], cwd=root, log_path=log_path, append=True)
    return result.returncode == 0


def docker_ids(label_filter: str, resource_type: str, root: Path, log_path: Path) -> list[str]:
    if resource_type == "container":
        args = ["docker", "ps", "-aq", "--filter", label_filter]
    elif resource_type == "network":
        args = ["docker", "network", "ls", "-q", "--filter", label_filter]
    else:
        raise ValueError(resource_type)
    result = run_command(args, cwd=root, log_path=log_path, append=True)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def docker_names(label_filter: str, root: Path, log_path: Path) -> list[str]:
    result = run_command(
        ["docker", "ps", "-a", "--filter", label_filter, "--format", "{{.Names}}"],
        cwd=root,
        log_path=log_path,
        append=True,
    )
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    result = run_command(
        ["docker", "network", "ls", "--filter", label_filter, "--format", "{{.Name}}"],
        cwd=root,
        log_path=log_path,
        append=True,
    )
    names.extend(line.strip() for line in result.stdout.splitlines() if line.strip())
    return names


def evaluate_prerequisites(args: argparse.Namespace, state: LifecycleState) -> None:
    upstream_checks = [
        ("governance-check job", args.governance_job_result),
        ("governance_result", args.governance_result),
        ("static-analysis job", args.static_analysis_job_result),
        ("static_analysis_result", args.static_analysis_result),
        ("unit-test job", args.unit_test_job_result),
        ("unit_test_result", args.unit_test_result),
        ("build-package job", args.build_package_job_result),
        ("build_package_result", args.build_package_result),
    ]
    for label, value in upstream_checks:
        if value != "success":
            state.failure_reasons.append(f"{label} is {value or '<missing>'}")

    if args.issue_number in ("", "UNLINKED"):
        state.failure_reasons.append("Issue number is not linked; environment face ID will not be generated")

    required_build_values = {
        "build_artifact_name": args.build_artifact_name,
        "build_artifact_id": args.build_artifact_id,
        "build_artifact_version": args.build_artifact_version,
        "build_artifact_checksum": args.build_artifact_checksum,
    }
    for label, value in required_build_values.items():
        if not value:
            state.failure_reasons.append(f"{label} is missing")

    if not normalize_bool(args.build_artifact_uploaded):
        state.failure_reasons.append("Build Artifact upload did not succeed")

    state.upstream_ready = not state.failure_reasons
    if not state.upstream_ready:
        return

    build_artifact_dir = Path(args.build_artifact_dir)
    binary_path = build_artifact_dir / "go-app-linux-amd64"
    manifest_path = build_artifact_dir / "manifest.json"
    checksum_path = build_artifact_dir / "go-app-linux-amd64.sha256"

    if not binary_path.exists():
        state.failure_reasons.append("Downloaded Build Artifact does not contain go-app-linux-amd64")
    if not manifest_path.exists():
        state.failure_reasons.append("Downloaded Build Artifact does not contain manifest.json")
    if not checksum_path.exists():
        state.failure_reasons.append("Downloaded Build Artifact does not contain go-app-linux-amd64.sha256")

    if binary_path.exists():
        actual_checksum = sha256_file(binary_path)
        if actual_checksum != args.build_artifact_checksum:
            state.failure_reasons.append(
                "Downloaded Build Artifact checksum mismatch. "
                f"expected={args.build_artifact_checksum} actual={actual_checksum}"
            )
        try:
            binary_path.chmod(
                binary_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
        except OSError as exc:
            state.failure_reasons.append(f"Failed to set execute bit on downloaded binary: {exc}")

    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            state.failure_reasons.append(f"Build Artifact manifest is invalid JSON: {exc}")
        else:
            version = str(manifest.get("build_artifact_version") or "")
            if version != args.build_artifact_version:
                state.failure_reasons.append(
                    "Build Artifact manifest version mismatch. "
                    f"expected={args.build_artifact_version} actual={version or '<missing>'}"
                )

    state.artifact_ready = not state.failure_reasons
    state.prerequisites_met = state.artifact_ready


def run_terraform_apply(
    args: argparse.Namespace,
    state: LifecycleState,
    *,
    root: Path,
    output_dir: Path,
    logs_dir: Path,
    image_name: str,
    label_filter: str,
) -> dict[str, str]:
    tf_dir = root / "terraform" / "environments" / "ut"
    state.environment_creation_state = "InProgress"
    fmt = run_command(["terraform", "fmt", "-check"], cwd=tf_dir, log_path=logs_dir / "terraform-plan.log", append=True)
    if fmt.returncode != 0:
        state.failure_reasons.append("terraform fmt -check failed")
        state.environment_creation_state = "Failed"
        return {}

    init = run_command(["terraform", "init", "-input=false"], cwd=tf_dir, log_path=logs_dir / "terraform-plan.log", append=True)
    if init.returncode != 0:
        state.failure_reasons.append("terraform init failed")
        state.environment_creation_state = "Failed"
        return {}

    validate = run_command(["terraform", "validate"], cwd=tf_dir, log_path=logs_dir / "terraform-plan.log", append=True)
    if validate.returncode != 0:
        state.failure_reasons.append("terraform validate failed")
        state.environment_creation_state = "Failed"
        return {}

    vars_args = [
        "-var",
        f"environment_face_id={state.environment_face_id}",
        "-var",
        f"target_image_name={image_name}",
        "-var",
        f"host_http_port={args.host_http_port}",
        "-var",
        f"test_run_id={args.test_run_id}",
        "-var",
        f"issue_number={args.issue_number}",
        "-var",
        f"workflow_run_id={args.workflow_run_id}",
        "-var",
        f"workflow_run_attempt={args.workflow_run_attempt}",
        "-var",
        f"repository={args.repository}",
    ]
    plan = run_command(
        ["terraform", "plan", "-input=false", "-out=tfplan", *vars_args],
        cwd=tf_dir,
        log_path=logs_dir / "terraform-plan.log",
        append=True,
    )
    if plan.returncode != 0:
        state.failure_reasons.append("terraform plan failed")
        state.environment_creation_state = "Failed"
        return {}

    state.environment_resources_may_exist = True
    apply = run_command(
        ["terraform", "apply", "-auto-approve", "-input=false", "tfplan"],
        cwd=tf_dir,
        log_path=logs_dir / "terraform-apply.log",
    )
    if apply.returncode != 0:
        state.failure_reasons.append("terraform apply failed")
        state.environment_creation_state = "Failed"
        return {}

    outputs: dict[str, str] = {}
    for name in ("ansible_inventory", "container_name", "network_name", "host_http_url"):
        result = run_command(["terraform", "output", "-raw", name], cwd=tf_dir, log_path=logs_dir / "terraform-apply.log", append=True)
        if result.returncode != 0:
            state.failure_reasons.append(f"terraform output {name} failed")
            continue
        outputs[name] = result.stdout.strip()

    if "ansible_inventory" in outputs:
        (output_dir / "inventory.yml").write_text(outputs["ansible_inventory"], encoding="utf-8")
    if "container_name" in outputs:
        (output_dir / "container_name.txt").write_text(outputs["container_name"], encoding="utf-8")
    if "host_http_url" in outputs:
        (output_dir / "host_http_url.txt").write_text(outputs["host_http_url"], encoding="utf-8")
    (output_dir / "managed_label_filter.txt").write_text(label_filter, encoding="utf-8")
    return outputs


def run_ansible_and_checks(
    args: argparse.Namespace,
    state: LifecycleState,
    *,
    root: Path,
    output_dir: Path,
    logs_dir: Path,
    outputs: dict[str, str],
) -> bool:
    inventory = output_dir / "inventory.yml"
    if not inventory.exists():
        state.failure_reasons.append("Ansible inventory was not created")
        state.environment_creation_state = "Failed"
        state.readiness_check_execution_state = "Skipped"
        state.readiness_check_result = "FailedBeforeCheck"
        state.test_execution_state = "Failed"
        return False

    ansible_log = logs_dir / "ansible.log"
    infra = run_command(
        ["ansible-playbook", "-i", str(inventory), "ansible/infra/site.yml"],
        cwd=root,
        log_path=ansible_log,
        append=True,
    )
    if infra.returncode != 0:
        state.failure_reasons.append("Ansible infra configuration failed")
        state.environment_creation_state = "Failed"
        state.readiness_check_execution_state = "Skipped"
        state.readiness_check_result = "FailedBeforeCheck"
        state.test_execution_state = "Failed"
        return False

    binary_path = Path(args.build_artifact_dir) / "go-app-linux-amd64"
    deploy = run_command(
        [
            "ansible-playbook",
            "-i",
            str(inventory),
            "ansible/deploy/site.yml",
            "-e",
            f"app_artifact_path={binary_path}",
            "-e",
            f"app_version={args.build_artifact_version}",
        ],
        cwd=root,
        log_path=ansible_log,
        append=True,
    )
    if deploy.returncode != 0:
        state.failure_reasons.append("Ansible app deploy failed")
        state.environment_creation_state = "Failed"
        state.readiness_check_execution_state = "Skipped"
        state.readiness_check_result = "FailedBeforeCheck"
        state.test_execution_state = "Failed"
        return False

    state.environment_creation_state = "Completed"
    state.readiness_check_execution_state = "InProgress"

    container_name = outputs.get("container_name", "")
    if not container_name:
        state.failure_reasons.append("container_name output is missing")
        state.readiness_check_execution_state = "Failed"
        state.readiness_check_result = "Failed"
        state.test_execution_state = "Failed"
        return False

    check_log = logs_dir / "startup-connectivity-check.log"
    checks = [
        (
            "binary exists and is executable",
            ["docker", "exec", container_name, "sh", "-lc", f"test -x {APP_BINARY_PATH}"],
        ),
        (
            "pid file references a live process",
            ["docker", "exec", container_name, "sh", "-lc", f"test -s {APP_PID_PATH} && kill -0 $(cat {APP_PID_PATH})"],
        ),
        (
            "app port is listening",
            ["docker", "exec", container_name, "sh", "-lc", f"ss -ltn | grep -E ':{APP_PORT}[[:space:]]'"],
        ),
        (
            "direct health returns expected version",
            [
                "docker",
                "exec",
                container_name,
                "python3",
                "-c",
                (
                    "import json,sys,urllib.request;"
                    f"data=json.load(urllib.request.urlopen('http://127.0.0.1:{APP_PORT}/health', timeout=5));"
                    f"assert data.get('status')=='ok', data;"
                    f"assert data.get('version')=='{args.build_artifact_version}', data"
                ),
            ],
        ),
        (
            "nginx proxied health returns expected version",
            [
                "docker",
                "exec",
                container_name,
                "python3",
                "-c",
                (
                    "import json,sys,urllib.request;"
                    f"data=json.load(urllib.request.urlopen('http://127.0.0.1:{NGINX_PORT}/health', timeout=5));"
                    f"assert data.get('status')=='ok', data;"
                    f"assert data.get('version')=='{args.build_artifact_version}', data"
                ),
            ],
        ),
    ]

    failed = False
    for label, command in checks:
        append_log(check_log, f"## {label}")
        result = run_command(command, cwd=root, log_path=check_log, append=True)
        if result.returncode != 0:
            state.failure_reasons.append(f"startup/connectivity check failed: {label}")
            failed = True

    host_url = outputs.get("host_http_url", "")
    if host_url:
        try:
            with urlopen(f"{host_url}/health", timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            append_log(check_log, f"host nginx health response: {data}")
            if response.status != 200 or data.get("version") != args.build_artifact_version:
                state.failure_reasons.append("host nginx health response did not match expected version")
                failed = True
        except Exception as exc:  # noqa: BLE001 - evidence capture should keep running.
            append_log(check_log, f"ERROR: host nginx health request failed: {exc}")
            state.failure_reasons.append("host nginx health request failed")
            failed = True

    if failed:
        state.readiness_check_execution_state = "Failed"
        state.readiness_check_result = "Failed"
        state.test_execution_state = "Failed"
        return False
    state.readiness_check_execution_state = "Completed"
    state.readiness_check_result = "Passed"
    return True


def run_pytest_suite(
    *,
    state: LifecycleState,
    test_key: str,
    title: str,
    command: list[str],
    env: dict[str, str],
    root: Path,
    output_dir: Path,
) -> tuple[str, str]:
    log_path = f"logs/{test_key}-test.log"
    junit_path = f"test-results/{test_key}-test-junit.xml"
    result_path = f"test-results/{test_key}-test-result.json"
    summary_path = f"summaries/{test_key}-test-summary.md"
    result = run_command(
        command,
        cwd=root,
        log_path=output_dir / log_path,
        env=env,
    )
    failure_reasons: list[str] = []
    if result.returncode != 0:
        failure_reasons.append(f"{title} exited with rc={result.returncode}")
    junit_exists = (output_dir / junit_path).exists()
    if not junit_exists:
        reason = f"JUnit XML was not created at {junit_path}"
        record_missing_evidence(state, junit_path, reason)
        failure_reasons.append(reason)
        write_junit_placeholder(
            output_dir / junit_path,
            suite_name=f"{test_key}-test",
            case_name=f"{test_key}_test_junit_missing",
            result="Failed",
            message=reason,
        )

    if junit_exists:
        try:
            junit_analysis = parse_junit_results(
                output_dir / junit_path,
                FORMAL_TEST_CASE_IDS[test_key],
            )
        except (ET.ParseError, OSError, ValueError) as exc:
            reason = f"JUnit XML could not be parsed: {exc}"
            failure_reasons.append(reason)
            record_missing_evidence(state, junit_path, reason)
            junit_analysis = empty_formal_test_analysis(FORMAL_TEST_CASE_IDS[test_key])
        else:
            failure_reasons.extend(junit_integrity_reasons(junit_analysis))
            counts = junit_analysis["counts"]
            if counts["failed"] or counts["errors"] or counts["skipped"]:
                failure_reasons.append(
                    "formal test case results are incomplete: "
                    f"failed={counts['failed']} errors={counts['errors']} skipped={counts['skipped']}"
                )
    else:
        junit_analysis = empty_formal_test_analysis(FORMAL_TEST_CASE_IDS[test_key])

    execution_state = "Failed" if failure_reasons else "Completed"
    test_result = "Failed" if failure_reasons else "Passed"
    write_test_result_artifacts(
        output_dir=output_dir,
        test_key=test_key,
        title=title,
        execution_state=execution_state,
        result=test_result,
        command=result.command,
        returncode=result.returncode,
        log_path=log_path,
        junit_path=junit_path,
        result_path=result_path,
        summary_path=summary_path,
        failure_reasons=failure_reasons,
        junit_analysis=junit_analysis,
        execution_mode="pytest",
    )
    return execution_state, test_result


def run_formal_tests(
    args: argparse.Namespace,
    state: LifecycleState,
    *,
    root: Path,
    output_dir: Path,
    outputs: dict[str, str],
) -> None:
    container_name = outputs.get("container_name", "")
    network_name = outputs.get("network_name", "")
    host_http_url = outputs.get("host_http_url", "")
    if not container_name or not network_name or not host_http_url:
        reason = "Terraform outputs required for formal tests are incomplete."
        state.failure_reasons.append(reason)
        write_skipped_test_artifacts(
            output_dir=output_dir,
            test_key="infrastructure",
            title="infrastructure-test",
            result="FailedBeforeTest",
            reason=reason,
        )
        write_skipped_test_artifacts(
            output_dir=output_dir,
            test_key="api",
            title="api-test",
            result="FailedBeforeTest",
            reason=reason,
        )
        state.infrastructure_test_execution_state = "Skipped"
        state.infrastructure_test_result = "FailedBeforeTest"
        state.api_test_execution_state = "Skipped"
        state.api_test_result = "FailedBeforeTest"
        state.test_execution_state = "Failed"
        state.overall_test_result = derive_overall_test_result(state)
        return

    test_env = os.environ.copy()
    test_env.update(
        {
            "TARGET_CONTAINER_NAME": container_name,
            "TARGET_NETWORK_NAME": network_name,
            "EXPECTED_ENVIRONMENT_FACE_ID": state.environment_face_id,
            "EXPECTED_TEST_RUN_ID": args.test_run_id,
            "EXPECTED_ISSUE_NUMBER": args.issue_number,
            "EXPECTED_APP_VERSION": args.build_artifact_version,
            "APP_VERSION": args.build_artifact_version,
            "HOST_HTTP_URL": host_http_url,
            "API_BASE_URL": host_http_url,
            "EXPECTED_MANAGED_BY": MANAGED_BY,
        }
    )

    infra_command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--junitxml",
        str(output_dir / "test-results" / "infrastructure-test-junit.xml"),
        f"--hosts=docker://{container_name}",
        "tests/infrastructure",
    ]
    infra_state, infra_result = run_pytest_suite(
        state=state,
        test_key="infrastructure",
        title="infrastructure-test",
        command=infra_command,
        env=test_env,
        root=root,
        output_dir=output_dir,
    )
    state.infrastructure_test_execution_state = infra_state
    state.infrastructure_test_result = infra_result
    if infra_result != "Passed":
        state.failure_reasons.append("infrastructure-test failed")
        reason = "API test was skipped because infrastructure-test did not pass."
        write_skipped_test_artifacts(
            output_dir=output_dir,
            test_key="api",
            title="api-test",
            result="Skipped",
            reason=reason,
        )
        state.api_test_execution_state = "Skipped"
        state.api_test_result = "Skipped"
        state.test_execution_state = "Failed"
        state.overall_test_result = derive_overall_test_result(state)
        return

    api_command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--junitxml",
        str(output_dir / "test-results" / "api-test-junit.xml"),
        "tests/api",
    ]
    api_state, api_result = run_pytest_suite(
        state=state,
        test_key="api",
        title="api-test",
        command=api_command,
        env=test_env,
        root=root,
        output_dir=output_dir,
    )
    state.api_test_execution_state = api_state
    state.api_test_result = api_result
    if api_result != "Passed":
        state.failure_reasons.append("api-test failed")
        state.test_execution_state = "Failed"
        state.overall_test_result = derive_overall_test_result(state)
        return

    state.test_execution_state = "Completed"
    state.overall_test_result = derive_overall_test_result(state)


def collect_logs(root: Path, logs_dir: Path, container_name: str) -> None:
    docker_state_before = logs_dir / "docker-state-before-cleanup.txt"
    run_command(["docker", "ps", "-a"], cwd=root, log_path=docker_state_before, append=True)
    run_command(["docker", "network", "ls"], cwd=root, log_path=docker_state_before, append=True)
    if not container_name:
        write_log(logs_dir / "nginx.log", "No container name is available; Nginx logs were not collected.")
        write_log(logs_dir / "go-app.log", "No container name is available; Go app logs were not collected.")
        return
    run_command(["docker", "inspect", container_name], cwd=root, log_path=docker_state_before, append=True)
    run_command(["docker", "exec", container_name, "sh", "-lc", "ps auxww"], cwd=root, log_path=docker_state_before, append=True)
    run_command(["docker", "exec", container_name, "sh", "-lc", "ss -ltnp"], cwd=root, log_path=docker_state_before, append=True)
    nginx = run_command(
        ["docker", "exec", container_name, "sh", "-lc", "cat /var/log/nginx/*.log 2>/dev/null || true"],
        cwd=root,
        log_path=logs_dir / "nginx.log",
    )
    if not nginx.stdout.strip():
        append_log(logs_dir / "nginx.log", "No Nginx log content was available.")
    app = run_command(
        ["docker", "exec", container_name, "sh", "-lc", "cat /var/log/ms1-app/*.log 2>/dev/null || true"],
        cwd=root,
        log_path=logs_dir / "go-app.log",
    )
    if not app.stdout.strip():
        append_log(logs_dir / "go-app.log", "No Go app log content was available.")


def cleanup(
    args: argparse.Namespace,
    state: LifecycleState,
    *,
    root: Path,
    logs_dir: Path,
    label_filter: str,
    image_name: str,
) -> None:
    cleanup_log = logs_dir / "cleanup.log"
    state.cleanup_started_at = utc_timestamp()
    append_log(cleanup_log, f"cleanup started at {state.cleanup_started_at}")

    destroy_log = logs_dir / "terraform-destroy.log"
    if not state.prerequisites_met or not state.environment_resources_may_exist:
        state.cleanup_attempted = True
        state.cleanup_targets = []
        state.cleanup_target_count = 0
        state.cleanup_state = "Completed"
        if state.prerequisites_met:
            append_log(cleanup_log, "Terraform apply was not started; cleanup target count is 0.")
            write_log(destroy_log, "Terraform destroy was not required because Terraform apply was not started.")
        else:
            append_log(cleanup_log, "Environment was not created; cleanup target count is 0.")
            write_log(destroy_log, "Terraform destroy was not required because no environment was created.")
    else:
        if not docker_available(root, cleanup_log):
            state.cleanup_state = "NotAttempted"
            state.failure_reasons.append("docker is unavailable; cleanup could not be attempted")
            state.cleanup_finished_at = utc_timestamp()
            return
        state.cleanup_attempted = True
        state.cleanup_targets = docker_names(label_filter, root, cleanup_log)
        state.cleanup_target_count = len(state.cleanup_targets)

        tf_dir = root / "terraform" / "environments" / "ut"
        destroy = run_command(
            [
                "terraform",
                "destroy",
                "-auto-approve",
                "-input=false",
                "-var",
                f"environment_face_id={state.environment_face_id}",
                "-var",
                f"target_image_name={image_name}",
                "-var",
                f"host_http_port={args.host_http_port}",
                "-var",
                f"test_run_id={args.test_run_id}",
                "-var",
                f"issue_number={args.issue_number}",
                "-var",
                f"workflow_run_id={args.workflow_run_id}",
                "-var",
                f"workflow_run_attempt={args.workflow_run_attempt}",
                "-var",
                f"repository={args.repository}",
            ],
            cwd=tf_dir,
            log_path=destroy_log,
        )
        if destroy.returncode != 0:
            state.warnings.append("terraform destroy failed; Docker label cleanup fallback was attempted")

        containers = docker_ids(label_filter, "container", root, cleanup_log)
        if containers:
            run_command(["docker", "rm", "-f", *containers], cwd=root, log_path=cleanup_log, append=True)
        networks = docker_ids(label_filter, "network", root, cleanup_log)
        if networks:
            run_command(["docker", "network", "rm", *networks], cwd=root, log_path=cleanup_log, append=True)

    state.cleanup_finished_at = utc_timestamp()
    append_log(cleanup_log, f"cleanup finished at {state.cleanup_finished_at}")


def verify_residue(
    state: LifecycleState,
    *,
    root: Path,
    logs_dir: Path,
    label_filter: str,
) -> None:
    residue_log = logs_dir / "residue-verification.log"
    docker_state_after = logs_dir / "docker-state-after-cleanup.txt"
    if state.cleanup_state == "NotAttempted" and not state.cleanup_attempted:
        state.residue_verification_result = "NotAttempted"
        write_log(residue_log, "Cleanup was not attempted. Residue verification is not reliable.")
        write_log(docker_state_after, "Cleanup was not attempted. Docker state after cleanup was not collected.")
        return

    if not state.prerequisites_met or not state.environment_resources_may_exist:
        state.remaining_resource_count = 0
        state.remaining_resource_identifiers = []
        state.residue_verification_result = "Passed"
        state.cleanup_warning = bool(state.warnings)
        state.cleanup_state = "CompletedWithWarning" if state.cleanup_warning else "Completed"
        if state.prerequisites_met:
            write_log(residue_log, "Terraform apply was not started. Residue verification passed with remaining_resource_count=0.")
            write_log(docker_state_after, "Terraform apply was not started. No Docker resources are expected.")
        else:
            write_log(residue_log, "No environment was created. Residue verification passed with remaining_resource_count=0.")
            write_log(docker_state_after, "No environment was created. No Docker resources are expected.")
        return

    run_command(["docker", "ps", "-a"], cwd=root, log_path=docker_state_after, append=True)
    run_command(["docker", "network", "ls"], cwd=root, log_path=docker_state_after, append=True)
    remaining = docker_names(label_filter, root, residue_log)
    state.remaining_resource_identifiers = remaining
    state.remaining_resource_count = len(remaining)
    if remaining:
        state.residue_verification_result = "Failed"
        state.warnings.append("managed Docker resources remain after cleanup")
    else:
        state.residue_verification_result = "Passed"

    state.cleanup_warning = bool(state.warnings)
    state.cleanup_state = "CompletedWithWarning" if state.cleanup_warning else "Completed"
    append_log(residue_log, f"remaining_resource_count={state.remaining_resource_count}")
    for identifier in remaining:
        append_log(residue_log, f"remaining={identifier}")


def ensure_placeholder_logs(logs_dir: Path) -> None:
    for relative_path in EXPECTED_EVIDENCE:
        if not relative_path.startswith("logs/"):
            continue
        path = logs_dir.parent / relative_path
        if not path.exists():
            write_log(path, f"{relative_path} was not produced before finalization.")


def build_summary(manifest: dict[str, Any], result_payload: dict[str, Any]) -> str:
    reasons = result_payload["failure_reasons"] or ["なし"]
    warnings = result_payload["warnings"] or ["なし"]
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    warning_lines = "\n".join(f"- {warning}" for warning in warnings)
    return "\n".join(
        [
            "# environment-lifecycle Summary",
            "",
            "| Item | Value |",
            "|---|---|",
            f"| Result | `{result_payload['environment_lifecycle_result']}` |",
            f"| Test run ID | `{manifest['test_run_id']}` |",
            f"| Pull Request | `#{manifest['pull_request_number']}` |",
            f"| Head SHA | `{manifest['pr_head_sha']}` |",
            f"| Issue | `{manifest['issue_number_or_UNLINKED']}` |",
            f"| Environment face ID | `{manifest['environment_face_id_or_not_created']}` |",
            f"| Environment creation state | `{manifest['environment_creation_state']}` |",
            f"| Readiness check | `{manifest['readiness_check_execution_state']} / {manifest['readiness_check_result']}` |",
            f"| Infrastructure test | `{manifest['infrastructure_test_execution_state']} / {manifest['infrastructure_test_result']}` |",
            f"| API test | `{manifest['api_test_execution_state']} / {manifest['api_test_result']}` |",
            f"| Overall test result | `{manifest['overall_test_result']}` |",
            f"| Cleanup state | `{manifest['cleanup_state']}` |",
            f"| Remaining resource count | `{manifest['remaining_resource_count']}` |",
            f"| Environment lifecycle result | `{result_payload['environment_lifecycle_result']}` |",
            f"| Test execution state (compatibility) | `{manifest['test_execution_state']}` |",
            f"| Cleanup target count | `{manifest['cleanup_target_count']}` |",
            f"| Cleanup warning | `{str(manifest['cleanup_warning']).lower()}` |",
            f"| Missing evidence count | `{manifest['missing_evidence_count']}` |",
            f"| Environment evidence complete | `{str(manifest['environment_evidence_complete']).lower()}` |",
            f"| Evidence Artifact | `{manifest['artifact_name']}` |",
            "",
            "## Failure reasons",
            "",
            reason_lines,
            "",
            "## Cleanup warnings",
            "",
            warning_lines,
            "",
        ]
    )


def finalize_result(args: argparse.Namespace, state: LifecycleState, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    artifact_name = f"evidence-environment_{args.test_run_id}"
    if not args.test_run_id:
        artifact_name = f"evidence-environment_missing-{args.workflow_run_id}-A{args.workflow_run_attempt}"

    if state.cleanup_state == "NotAttempted":
        state.environment_lifecycle_result = "failure"
    elif not state.upstream_ready:
        state.environment_lifecycle_result = "skipped_prerequisites"
    elif state.overall_test_result == "Passed":
        state.environment_lifecycle_result = "success"
    else:
        state.environment_lifecycle_result = "failure"

    collected = relative_existing_files(output_dir, EXPECTED_EVIDENCE)
    for generated_file in ("manifest.json", "environment-lifecycle-result.json", "summary.md"):
        if generated_file not in collected:
            collected.append(generated_file)

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
        generated_timestamp=utc_timestamp(args.created_at),
        expected_evidence=EXPECTED_EVIDENCE,
        collected_evidence=collected,
        result=state.environment_lifecycle_result,
        target_version=args.target_version,
        required_final_stage=args.required_final_stage,
    )
    merged_missing = sorted(
        set(manifest.get("missing_evidence", [])) | set(state.detected_missing_evidence)
    )
    manifest["missing_evidence"] = merged_missing
    manifest["missing_evidence_count"] = len(merged_missing)
    manifest["environment_evidence_complete"] = manifest["missing_evidence_count"] == 0
    manifest.update(
        {
            "environment_face_id_or_not_created": state.environment_face_id or "NOT_CREATED",
            "environment_creation_state": state.environment_creation_state,
            "readiness_check_execution_state": state.readiness_check_execution_state,
            "readiness_check_result": state.readiness_check_result,
            "test_execution_state": state.test_execution_state,
            "overall_test_result": state.overall_test_result,
            "test_result": state.overall_test_result,
            "test_result_alias_of": "overall_test_result",
            "infrastructure_test_execution_state": state.infrastructure_test_execution_state,
            "infrastructure_test_result": state.infrastructure_test_result,
            "infrastructure_test_result_files": INFRASTRUCTURE_TEST_RESULT_FILES,
            "api_test_execution_state": state.api_test_execution_state,
            "api_test_result": state.api_test_result,
            "api_test_result_files": API_TEST_RESULT_FILES,
            "cleanup_state": state.cleanup_state,
            "cleanup_target_count": state.cleanup_target_count,
            "remaining_resource_count": state.remaining_resource_count,
            "cleanup_warning": state.cleanup_warning,
            "cleanup_targets": state.cleanup_targets,
            "cleanup_started_at": state.cleanup_started_at,
            "cleanup_finished_at": state.cleanup_finished_at,
            "residue_verification_result": state.residue_verification_result,
            "remaining_resource_identifiers": state.remaining_resource_identifiers,
        }
    )

    result_payload = {
        "environment_lifecycle_result": state.environment_lifecycle_result,
        "prerequisites_met": state.prerequisites_met,
        "upstream_ready": state.upstream_ready,
        "artifact_ready": state.artifact_ready,
        "failure_reasons": state.failure_reasons,
        "warnings": state.warnings,
        "evidence": {
            "missing_evidence": manifest["missing_evidence"],
            "missing_evidence_count": manifest["missing_evidence_count"],
            "environment_evidence_complete": manifest["environment_evidence_complete"],
            "evidence_missing_reasons": state.evidence_missing_reasons,
        },
        "build_artifact": {
            "name": args.build_artifact_name,
            "id": args.build_artifact_id,
            "version": args.build_artifact_version,
            "checksum": args.build_artifact_checksum,
        },
        "environment": {
            "environment_face_id": state.environment_face_id,
            "environment_creation_state": state.environment_creation_state,
            "readiness_check_execution_state": state.readiness_check_execution_state,
            "readiness_check_result": state.readiness_check_result,
            "test_execution_state": state.test_execution_state,
            "overall_test_result": state.overall_test_result,
            "test_result": state.overall_test_result,
            "test_result_alias_of": "overall_test_result",
        },
        "tests": {
            "infrastructure": {
                "execution_state": state.infrastructure_test_execution_state,
                "result": state.infrastructure_test_result,
                "result_files": INFRASTRUCTURE_TEST_RESULT_FILES,
            },
            "api": {
                "execution_state": state.api_test_execution_state,
                "result": state.api_test_result,
                "result_files": API_TEST_RESULT_FILES,
            },
        },
        "cleanup": {
            "cleanup_state": state.cleanup_state,
            "cleanup_warning": state.cleanup_warning,
            "cleanup_target_count": state.cleanup_target_count,
            "remaining_resource_count": state.remaining_resource_count,
            "residue_verification_result": state.residue_verification_result,
            "cleanup_attempted": state.cleanup_attempted,
            "environment_resources_may_exist": state.environment_resources_may_exist,
        },
    }
    summary = build_summary(manifest, result_payload)
    return manifest, result_payload, summary


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = repo_root()
    output_dir = Path(args.output_dir)
    logs_dir = output_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not args.test_run_id:
        args.test_run_id = f"TR-UT-UNLINKED-{args.workflow_run_id}-A{args.workflow_run_attempt}"

    state = LifecycleState()
    evaluate_prerequisites(args, state)

    if state.prerequisites_met:
        state.environment_face_id = environment_face_id(
            args.issue_number,
            args.workflow_run_id,
            args.workflow_run_attempt,
        )

    label_filter = f"label=test_run_id={args.test_run_id}"
    image_name = f"{sanitize_docker_name(state.environment_face_id or args.test_run_id)}-target:local"
    outputs: dict[str, str] = {}

    try:
        if state.prerequisites_met:
            build_image = run_command(
                ["docker", "build", "-t", image_name, "images/target"],
                cwd=root,
                log_path=logs_dir / "terraform-apply.log",
                append=True,
            )
            if build_image.returncode != 0:
                state.failure_reasons.append("target image build failed")
                state.environment_creation_state = "Failed"
                state.readiness_check_execution_state = "Skipped"
                state.readiness_check_result = "FailedBeforeCheck"
            else:
                outputs = run_terraform_apply(
                    args,
                    state,
                    root=root,
                    output_dir=output_dir,
                    logs_dir=logs_dir,
                    image_name=image_name,
                    label_filter=label_filter,
                )

            if state.environment_creation_state == "InProgress":
                startup_ready = run_ansible_and_checks(
                    args,
                    state,
                    root=root,
                    output_dir=output_dir,
                    logs_dir=logs_dir,
                    outputs=outputs,
                )
                if startup_ready:
                    run_formal_tests(
                        args,
                        state,
                        root=root,
                        output_dir=output_dir,
                        outputs=outputs,
                    )
        else:
            write_log(logs_dir / "terraform-plan.log", "Upstream prerequisites were not met; Terraform plan was skipped.")
            write_log(logs_dir / "terraform-apply.log", "Upstream prerequisites were not met; Terraform apply was skipped.")
            write_log(logs_dir / "ansible.log", "Upstream prerequisites were not met; Ansible was skipped.")
            write_log(logs_dir / "startup-connectivity-check.log", "Upstream prerequisites were not met; startup checks were skipped.")
    finally:
        collect_logs(root, logs_dir, outputs.get("container_name", "") if outputs else "")
        cleanup(args, state, root=root, logs_dir=logs_dir, label_filter=label_filter, image_name=image_name)
        verify_residue(state, root=root, logs_dir=logs_dir, label_filter=label_filter)
        ensure_unstarted_test_artifacts(output_dir, state)
        state.overall_test_result = derive_overall_test_result(state)
        ensure_placeholder_logs(logs_dir)

    manifest, result_payload, summary = finalize_result(args, state, output_dir)
    write_json(output_dir / "manifest.json", manifest)
    write_json(output_dir / "environment-lifecycle-result.json", result_payload)
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")

    write_github_output(
        args.github_output,
        {
            "environment_lifecycle_result": state.environment_lifecycle_result,
            "environment_evidence_manifest_finalized": True,
            "evidence_artifact_name": manifest["artifact_name"],
            "environment_face_id": state.environment_face_id,
            "environment_creation_state": state.environment_creation_state,
            "readiness_check_execution_state": state.readiness_check_execution_state,
            "readiness_check_result": state.readiness_check_result,
            "test_execution_state": state.test_execution_state,
            "overall_test_result": state.overall_test_result,
            "test_result": state.overall_test_result,
            "test_result_alias_of": "overall_test_result",
            "infrastructure_test_execution_state": state.infrastructure_test_execution_state,
            "infrastructure_test_result": state.infrastructure_test_result,
            "api_test_execution_state": state.api_test_execution_state,
            "api_test_result": state.api_test_result,
            "cleanup_state": state.cleanup_state,
            "cleanup_warning": state.cleanup_warning,
            "cleanup_target_count": state.cleanup_target_count,
            "remaining_resource_count": state.remaining_resource_count,
            "missing_evidence_count": manifest["missing_evidence_count"],
            "environment_evidence_complete": manifest["environment_evidence_complete"],
            "residue_verification_result": state.residue_verification_result,
            "failure_reason_count": len(state.failure_reasons),
        },
    )
    append_step_summary(args.github_step_summary, summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
