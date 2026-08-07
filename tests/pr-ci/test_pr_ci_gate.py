# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

import importlib.util
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "pr-ci"
sys.path.insert(0, str(SCRIPT_DIR))
MODULE_PATH = SCRIPT_DIR / "pr_ci_gate.py"
SPEC = importlib.util.spec_from_file_location("pr_ci_gate", MODULE_PATH)
pr_ci_gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = pr_ci_gate
SPEC.loader.exec_module(pr_ci_gate)


def success_env():
    return {
        "GOVERNANCE_JOB_RESULT": "success",
        "STATIC_ANALYSIS_JOB_RESULT": "success",
        "UNIT_TEST_JOB_RESULT": "success",
        "BUILD_PACKAGE_JOB_RESULT": "success",
        "ENVIRONMENT_LIFECYCLE_JOB_RESULT": "success",
        "TEST_RUN_ID": "TR-UT-ISSUE-7-100-A1",
        "ISSUE_NUMBER": "7",
        "TARGET_VERSION": "0.0.0",
        "REQUIRED_FINAL_STAGE": "UT",
        "GOVERNANCE_RESULT": "success",
        "STATIC_ANALYSIS_RESULT": "success",
        "UNIT_TEST_RESULT": "success",
        "BUILD_PACKAGE_RESULT": "success",
        "GOVERNANCE_EVIDENCE_ARTIFACT_UPLOADED": "true",
        "GOVERNANCE_EVIDENCE_ARTIFACT_NAME": "evidence-governance_TR-UT-ISSUE-7-100-A1",
        "GOVERNANCE_EVIDENCE_ARTIFACT_ID": "1",
        "STATIC_ANALYSIS_EVIDENCE_ARTIFACT_UPLOADED": "true",
        "STATIC_ANALYSIS_EVIDENCE_ARTIFACT_NAME": "evidence-static-analysis_TR-UT-ISSUE-7-100-A1",
        "STATIC_ANALYSIS_EVIDENCE_ARTIFACT_ID": "2",
        "UNIT_TEST_EVIDENCE_ARTIFACT_UPLOADED": "true",
        "UNIT_TEST_EVIDENCE_ARTIFACT_NAME": "evidence-unit-test_TR-UT-ISSUE-7-100-A1",
        "UNIT_TEST_EVIDENCE_ARTIFACT_ID": "3",
        "BUILD_PACKAGE_EVIDENCE_ARTIFACT_UPLOADED": "true",
        "BUILD_PACKAGE_EVIDENCE_ARTIFACT_NAME": "evidence-build-package_TR-UT-ISSUE-7-100-A1",
        "BUILD_PACKAGE_EVIDENCE_ARTIFACT_ID": "4",
        "BUILD_ARTIFACT_UPLOADED": "true",
        "BUILD_ARTIFACT_NAME": "build-go-app_TR-UT-ISSUE-7-100-A1",
        "BUILD_ARTIFACT_ID": "5",
        "BUILD_ARTIFACT_VERSION": "v0.0.0+b.1.a.1",
        "BUILD_ARTIFACT_CHECKSUM": "abc",
        "ENVIRONMENT_LIFECYCLE_RESULT": "success",
        "ENVIRONMENT_EVIDENCE_MANIFEST_FINALIZED": "true",
        "ENVIRONMENT_CREATION_STATE": "Completed",
        "READINESS_CHECK_EXECUTION_STATE": "Completed",
        "READINESS_CHECK_RESULT": "Passed",
        "INFRASTRUCTURE_TEST_EXECUTION_STATE": "Completed",
        "INFRASTRUCTURE_TEST_RESULT": "Passed",
        "API_TEST_EXECUTION_STATE": "Completed",
        "API_TEST_RESULT": "Passed",
        "OVERALL_TEST_RESULT": "Passed",
        "CLEANUP_STATE": "Completed",
        "REMAINING_RESOURCE_COUNT": "0",
        "MISSING_EVIDENCE_COUNT": "0",
        "ENVIRONMENT_EVIDENCE_COMPLETE": "true",
        "ENVIRONMENT_EVIDENCE_ARTIFACT_UPLOADED": "true",
        "ENVIRONMENT_EVIDENCE_ARTIFACT_NAME": "evidence-environment_TR-UT-ISSUE-7-100-A1",
        "ENVIRONMENT_EVIDENCE_ARTIFACT_ID": "6",
    }


def test_gate_success_when_environment_evidence_and_cleanup_completed():
    result = pr_ci_gate.evaluate_gate(success_env())

    assert result["gate_result"] == "success"
    assert result["failure_reasons"] == []


def test_gate_fails_when_cleanup_was_not_attempted():
    env = success_env()
    env["CLEANUP_STATE"] = "NotAttempted"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any("NotAttempted" in reason for reason in result["failure_reasons"])


def test_gate_fails_when_environment_lifecycle_job_failed():
    env = success_env()
    env["ENVIRONMENT_LIFECYCLE_JOB_RESULT"] = "failure"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any("environment-lifecycle job result is failure" in reason for reason in result["failure_reasons"])


def test_gate_fails_when_environment_creation_is_not_completed():
    env = success_env()
    env["ENVIRONMENT_CREATION_STATE"] = "Failed"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any(
        "environment_creation_state is Failed" in reason
        for reason in result["failure_reasons"]
    )


def test_gate_allows_cleanup_warning_state():
    env = success_env()
    env["CLEANUP_STATE"] = "CompletedWithWarning"
    env["CLEANUP_WARNING"] = "true"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "success"


def test_gate_fails_when_infrastructure_test_failed():
    env = success_env()
    env["INFRASTRUCTURE_TEST_RESULT"] = "Failed"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any("infrastructure_test_result is Failed" in reason for reason in result["failure_reasons"])


def test_gate_fails_when_readiness_check_failed():
    env = success_env()
    env["READINESS_CHECK_EXECUTION_STATE"] = "Failed"
    env["READINESS_CHECK_RESULT"] = "Failed"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any(
        "readiness_check_execution_state is Failed" in reason
        for reason in result["failure_reasons"]
    )
    assert any(
        "readiness_check_result is Failed" in reason
        for reason in result["failure_reasons"]
    )


def test_gate_fails_when_api_test_was_skipped():
    env = success_env()
    env["API_TEST_EXECUTION_STATE"] = "Skipped"
    env["API_TEST_RESULT"] = "Skipped"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any("api_test_result is Skipped" in reason for reason in result["failure_reasons"])


def test_gate_fails_when_overall_test_result_failed():
    env = success_env()
    env["OVERALL_TEST_RESULT"] = "Failed"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any(
        "overall_test_result is Failed" in reason
        for reason in result["failure_reasons"]
    )


def test_gate_fails_when_resources_remain_after_cleanup():
    env = success_env()
    env["REMAINING_RESOURCE_COUNT"] = "1"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any("remaining_resource_count is 1" in reason for reason in result["failure_reasons"])


def test_gate_fails_when_environment_evidence_is_missing():
    env = success_env()
    env["MISSING_EVIDENCE_COUNT"] = "1"
    env["ENVIRONMENT_EVIDENCE_COMPLETE"] = "false"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any("missing_evidence_count is 1" in reason for reason in result["failure_reasons"])
    assert any("environment evidence is not complete" in reason for reason in result["failure_reasons"])


def test_gate_fails_when_missing_evidence_count_output_is_missing():
    env = success_env()
    del env["MISSING_EVIDENCE_COUNT"]

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any("required value missing_evidence_count is missing" in reason for reason in result["failure_reasons"])


def test_gate_fails_when_missing_evidence_count_is_not_integer():
    env = success_env()
    env["MISSING_EVIDENCE_COUNT"] = "not-an-integer"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any("missing_evidence_count is not an integer" in reason for reason in result["failure_reasons"])


def test_gate_fails_when_environment_evidence_complete_is_false():
    env = success_env()
    env["ENVIRONMENT_EVIDENCE_COMPLETE"] = "false"

    result = pr_ci_gate.evaluate_gate(env)

    assert result["gate_result"] == "failure"
    assert any("environment evidence is not complete" in reason for reason in result["failure_reasons"])


def test_gate_failure_reason_uses_visible_missing_marker():
    env = success_env()
    del env["API_TEST_RESULT"]

    result = pr_ci_gate.evaluate_gate(env)

    assert "api_test_result is (missing)" in result["failure_reasons"]
    assert all("<missing>" not in reason for reason in result["failure_reasons"])


def test_gate_summary_does_not_hide_missing_values_in_markdown():
    env = success_env()
    del env["API_TEST_RESULT"]
    result = pr_ci_gate.evaluate_gate(env)

    summary = pr_ci_gate.build_summary(env, result)
    failure_section = summary.split("## Gate failure reasons", 1)[1]

    assert "- api_test_result is (missing)" in failure_section
    assert "<missing>" not in failure_section
