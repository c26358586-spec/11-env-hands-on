#!/usr/bin/env python3
# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from pr_ci_common import append_step_summary


MISSING_FAILURE_VALUE = "(missing)"


def env_value(name: str, env: dict[str, str]) -> str:
    return env.get(name, "").strip()


def is_true(value: str) -> bool:
    return value.strip().lower() == "true"


def require_value(reasons: list[str], label: str, value: str) -> None:
    if not value:
        reasons.append(f"required value {label} is missing")


def failure_value(value: str) -> str:
    return value or MISSING_FAILURE_VALUE


def require_success_job(reasons: list[str], job_name: str, result: str) -> None:
    if result != "success":
        reasons.append(f"{job_name} job result is {failure_value(result)}")


def require_logical_success(reasons: list[str], label: str, result: str) -> None:
    if result != "success":
        reasons.append(f"{label} is {failure_value(result)}")


def require_uploaded_artifact(
    reasons: list[str],
    label: str,
    uploaded: str,
    name: str,
    artifact_id: str,
) -> None:
    require_value(reasons, f"{label} Artifact name", name)
    require_value(reasons, f"{label} Artifact ID", artifact_id)
    if not is_true(uploaded):
        reasons.append(f"{label} Artifact upload did not succeed")


def require_int_value(reasons: list[str], label: str, value: str, expected: int) -> None:
    require_value(reasons, label, value)
    if not value:
        return
    try:
        actual = int(value)
    except ValueError:
        reasons.append(f"{label} is not an integer. actual={value}")
        return
    if actual != expected:
        reasons.append(f"{label} is {actual}; expected={expected}")


def evaluate_gate(env: dict[str, str]) -> dict[str, Any]:
    reasons: list[str] = []

    require_success_job(reasons, "governance-check", env_value("GOVERNANCE_JOB_RESULT", env))
    require_success_job(reasons, "static-analysis", env_value("STATIC_ANALYSIS_JOB_RESULT", env))
    require_success_job(reasons, "unit-test", env_value("UNIT_TEST_JOB_RESULT", env))
    require_success_job(reasons, "build-package", env_value("BUILD_PACKAGE_JOB_RESULT", env))
    require_success_job(reasons, "environment-lifecycle", env_value("ENVIRONMENT_LIFECYCLE_JOB_RESULT", env))

    for required_name in (
        "TEST_RUN_ID",
        "ISSUE_NUMBER",
        "TARGET_VERSION",
        "REQUIRED_FINAL_STAGE",
    ):
        require_value(reasons, required_name, env_value(required_name, env))

    require_logical_success(reasons, "governance_result", env_value("GOVERNANCE_RESULT", env))
    require_logical_success(reasons, "static_analysis_result", env_value("STATIC_ANALYSIS_RESULT", env))
    require_logical_success(reasons, "unit_test_result", env_value("UNIT_TEST_RESULT", env))
    require_logical_success(reasons, "build_package_result", env_value("BUILD_PACKAGE_RESULT", env))

    require_uploaded_artifact(
        reasons,
        "governance evidence",
        env_value("GOVERNANCE_EVIDENCE_ARTIFACT_UPLOADED", env),
        env_value("GOVERNANCE_EVIDENCE_ARTIFACT_NAME", env),
        env_value("GOVERNANCE_EVIDENCE_ARTIFACT_ID", env),
    )
    require_uploaded_artifact(
        reasons,
        "static-analysis evidence",
        env_value("STATIC_ANALYSIS_EVIDENCE_ARTIFACT_UPLOADED", env),
        env_value("STATIC_ANALYSIS_EVIDENCE_ARTIFACT_NAME", env),
        env_value("STATIC_ANALYSIS_EVIDENCE_ARTIFACT_ID", env),
    )
    require_uploaded_artifact(
        reasons,
        "unit-test evidence",
        env_value("UNIT_TEST_EVIDENCE_ARTIFACT_UPLOADED", env),
        env_value("UNIT_TEST_EVIDENCE_ARTIFACT_NAME", env),
        env_value("UNIT_TEST_EVIDENCE_ARTIFACT_ID", env),
    )
    require_uploaded_artifact(
        reasons,
        "build-package evidence",
        env_value("BUILD_PACKAGE_EVIDENCE_ARTIFACT_UPLOADED", env),
        env_value("BUILD_PACKAGE_EVIDENCE_ARTIFACT_NAME", env),
        env_value("BUILD_PACKAGE_EVIDENCE_ARTIFACT_ID", env),
    )
    require_uploaded_artifact(
        reasons,
        "Build",
        env_value("BUILD_ARTIFACT_UPLOADED", env),
        env_value("BUILD_ARTIFACT_NAME", env),
        env_value("BUILD_ARTIFACT_ID", env),
    )
    require_value(reasons, "Build Artifact version", env_value("BUILD_ARTIFACT_VERSION", env))
    require_value(reasons, "Build Artifact checksum", env_value("BUILD_ARTIFACT_CHECKSUM", env))

    environment_result = env_value("ENVIRONMENT_LIFECYCLE_RESULT", env)
    if environment_result != "success":
        reasons.append(f"environment_lifecycle_result is {failure_value(environment_result)}")

    environment_creation_state = env_value("ENVIRONMENT_CREATION_STATE", env)
    if environment_creation_state != "Completed":
        reasons.append(
            "environment_creation_state is "
            f"{failure_value(environment_creation_state)}"
        )

    if not is_true(env_value("ENVIRONMENT_EVIDENCE_MANIFEST_FINALIZED", env)):
        reasons.append("environment evidence manifest was not finalized")
    require_uploaded_artifact(
        reasons,
        "environment evidence",
        env_value("ENVIRONMENT_EVIDENCE_ARTIFACT_UPLOADED", env),
        env_value("ENVIRONMENT_EVIDENCE_ARTIFACT_NAME", env),
        env_value("ENVIRONMENT_EVIDENCE_ARTIFACT_ID", env),
    )

    cleanup_state = env_value("CLEANUP_STATE", env)
    if cleanup_state not in ("Completed", "CompletedWithWarning"):
        reasons.append(f"cleanup_state is {failure_value(cleanup_state)}")
    if cleanup_state == "NotAttempted":
        reasons.append("cleanup_state NotAttempted is not an acceptable cleanup warning")

    readiness_execution_state = env_value("READINESS_CHECK_EXECUTION_STATE", env)
    if readiness_execution_state != "Completed":
        reasons.append(
            "readiness_check_execution_state is "
            f"{failure_value(readiness_execution_state)}"
        )

    readiness_result = env_value("READINESS_CHECK_RESULT", env)
    if readiness_result != "Passed":
        reasons.append(f"readiness_check_result is {failure_value(readiness_result)}")

    infrastructure_execution_state = env_value("INFRASTRUCTURE_TEST_EXECUTION_STATE", env)
    if infrastructure_execution_state != "Completed":
        reasons.append(
            "infrastructure_test_execution_state is "
            f"{failure_value(infrastructure_execution_state)}"
        )

    infrastructure_result = env_value("INFRASTRUCTURE_TEST_RESULT", env)
    if infrastructure_result != "Passed":
        reasons.append(
            f"infrastructure_test_result is {failure_value(infrastructure_result)}"
        )

    api_execution_state = env_value("API_TEST_EXECUTION_STATE", env)
    if api_execution_state != "Completed":
        reasons.append(f"api_test_execution_state is {failure_value(api_execution_state)}")

    api_result = env_value("API_TEST_RESULT", env)
    if api_result != "Passed":
        reasons.append(f"api_test_result is {failure_value(api_result)}")

    overall_test_result = env_value("OVERALL_TEST_RESULT", env)
    if overall_test_result != "Passed":
        reasons.append(
            f"overall_test_result is {failure_value(overall_test_result)}"
        )

    require_int_value(
        reasons,
        "remaining_resource_count",
        env_value("REMAINING_RESOURCE_COUNT", env),
        0,
    )
    require_int_value(
        reasons,
        "missing_evidence_count",
        env_value("MISSING_EVIDENCE_COUNT", env),
        0,
    )
    if not is_true(env_value("ENVIRONMENT_EVIDENCE_COMPLETE", env)):
        reasons.append("environment evidence is not complete")

    gate_result = "success" if not reasons else "failure"
    return {
        "gate_result": gate_result,
        "failure_reasons": reasons,
    }


def build_summary(env: dict[str, str], result: dict[str, Any]) -> str:
    reasons = result["failure_reasons"] or ["なし"]
    reason_lines = "\n".join(f"- {reason}" for reason in reasons)
    rows = [
        ("Gate result", result["gate_result"]),
        ("Pull Request", f"#{env_value('PR_NUMBER', env) or '<missing>'}"),
        ("Branch", env_value("PR_HEAD_REF", env) or "<missing>"),
        ("Head SHA", env_value("PR_HEAD_SHA", env) or "<missing>"),
        ("Test run ID", env_value("TEST_RUN_ID", env) or "<missing>"),
        ("Issue", env_value("ISSUE_NUMBER", env) or "<missing>"),
        ("target_version", env_value("TARGET_VERSION", env) or "<missing>"),
        ("required_final_stage", env_value("REQUIRED_FINAL_STAGE", env) or "<missing>"),
        ("Workflow run ID", env_value("WORKFLOW_RUN_ID", env) or "<missing>"),
        ("Run attempt", f"A{env_value('WORKFLOW_RUN_ATTEMPT', env) or '<missing>'}"),
        ("governance-check job result", env_value("GOVERNANCE_JOB_RESULT", env) or "<missing>"),
        ("static-analysis job result", env_value("STATIC_ANALYSIS_JOB_RESULT", env) or "<missing>"),
        ("unit-test job result", env_value("UNIT_TEST_JOB_RESULT", env) or "<missing>"),
        ("build-package job result", env_value("BUILD_PACKAGE_JOB_RESULT", env) or "<missing>"),
        ("environment-lifecycle job result", env_value("ENVIRONMENT_LIFECYCLE_JOB_RESULT", env) or "<missing>"),
        ("Environment creation state", env_value("ENVIRONMENT_CREATION_STATE", env) or "<missing>"),
        (
            "Readiness check",
            (
                f"{env_value('READINESS_CHECK_EXECUTION_STATE', env) or '<missing>'} / "
                f"{env_value('READINESS_CHECK_RESULT', env) or '<missing>'}"
            ),
        ),
        (
            "Infrastructure test",
            (
                f"{env_value('INFRASTRUCTURE_TEST_EXECUTION_STATE', env) or '<missing>'} / "
                f"{env_value('INFRASTRUCTURE_TEST_RESULT', env) or '<missing>'}"
            ),
        ),
        (
            "API test",
            (
                f"{env_value('API_TEST_EXECUTION_STATE', env) or '<missing>'} / "
                f"{env_value('API_TEST_RESULT', env) or '<missing>'}"
            ),
        ),
        ("Overall test result", env_value("OVERALL_TEST_RESULT", env) or "<missing>"),
        ("Cleanup state", env_value("CLEANUP_STATE", env) or "<missing>"),
        ("Cleanup warning", env_value("CLEANUP_WARNING", env) or "<missing>"),
        ("Remaining resource count", env_value("REMAINING_RESOURCE_COUNT", env) or "<missing>"),
        ("Environment lifecycle result", env_value("ENVIRONMENT_LIFECYCLE_RESULT", env) or "<missing>"),
        ("Missing evidence count", env_value("MISSING_EVIDENCE_COUNT", env) or "<missing>"),
        ("Environment evidence complete", env_value("ENVIRONMENT_EVIDENCE_COMPLETE", env) or "<missing>"),
        ("Build Artifact", env_value("BUILD_ARTIFACT_NAME", env) or "<missing>"),
        ("Build Artifact ID", env_value("BUILD_ARTIFACT_ID", env) or "<missing>"),
        ("Build Artifact version", env_value("BUILD_ARTIFACT_VERSION", env) or "<missing>"),
        ("Build Artifact checksum", env_value("BUILD_ARTIFACT_CHECKSUM", env) or "<missing>"),
        ("Environment evidence Artifact", env_value("ENVIRONMENT_EVIDENCE_ARTIFACT_NAME", env) or "<missing>"),
    ]
    table = "\n".join(f"| {label} | `{value}` |" for label, value in rows)
    return "\n".join(
        [
            "# pr-ci-gate Summary",
            "",
            "| Item | Value |",
            "|---|---|",
            table,
            "",
            "## Gate failure reasons",
            "",
            reason_lines,
            "",
        ]
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the Lesson 5.5 PR CI gate.")
    parser.add_argument("--github-step-summary")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    env = dict(os.environ)
    result = evaluate_gate(env)
    summary = build_summary(env, result)
    append_step_summary(args.github_step_summary, summary)
    print(summary)
    if result["gate_result"] != "success":
        print("ERROR: pr-ci-gate failed:", file=sys.stderr)
        for reason in result["failure_reasons"]:
            print(f" - {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
