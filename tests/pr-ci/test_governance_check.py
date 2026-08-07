# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

import importlib.util
from pathlib import Path


# GitHub Actions workflow run IDs are positive; "0" cannot resolve to a real run.
FIXTURE_WORKFLOW_RUN_ID = "0"

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "pr-ci" / "governance_check.py"
SPEC = importlib.util.spec_from_file_location("governance_check", MODULE_PATH)
governance_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(governance_check)


def evaluate(body, branch="feature/issue-123-change"):
    return governance_check.evaluate_governance(
        pr_body=body,
        pr_head_ref=branch,
        repository="RanamicusTechnology/11-env-hands-on",
        workflow_name="PR CI",
        workflow_run_id=FIXTURE_WORKFLOW_RUN_ID,
        workflow_run_attempt="1",
        job_name="governance-check",
        pr_number="10",
        pr_head_sha="abc123",
        created_at="2026-07-03T00:00:00Z",
        check_issue_state=False,
    )


def result(payload):
    return payload["governance_result"]


def test_success_when_pr_body_issue_and_metadata_are_valid():
    payload = evaluate(
        "\n".join(
            [
                "Closes #123",
                "target_version: 0.1.0",
                "required_final_stage: UT",
            ]
        )
    )

    assert result(payload)["governance_result"] == "success"
    assert payload["manifest"]["issue_number"] == "123"
    assert payload["manifest"]["test_run_id"] == "TR-UT-ISSUE-123-0-A1"
    assert payload["manifest"]["artifact_name"] == "evidence-governance_TR-UT-ISSUE-123-0-A1"


def test_success_when_only_branch_issue_is_available():
    payload = evaluate(
        "\n".join(
            [
                "target_version: 0.1.0",
                "required_final_stage: UT",
            ]
        ),
        branch="fix/123-bug",
    )

    assert result(payload)["governance_result"] == "success"
    assert payload["manifest"]["issue_number"] == "123"


def test_failure_when_issue_is_unlinked_but_test_run_id_is_generated():
    payload = evaluate(
        "\n".join(
            [
                "target_version: 0.1.0",
                "required_final_stage: UT",
            ]
        ),
        branch="topic/no-issue",
    )

    assert result(payload)["governance_result"] == "failure"
    assert payload["manifest"]["issue_number"] == "UNLINKED"
    assert payload["manifest"]["test_run_id"] == "TR-UT-UNLINKED-0-A1"
    assert result(payload)["failure_reasons"]


def test_failure_when_target_version_is_missing():
    payload = evaluate(
        "\n".join(
            [
                "Closes #123",
                "required_final_stage: UT",
            ]
        )
    )

    assert result(payload)["governance_result"] == "failure"
    assert any("target_version" in reason for reason in result(payload)["failure_reasons"])


def test_failure_when_required_final_stage_is_missing():
    payload = evaluate(
        "\n".join(
            [
                "Closes #123",
                "target_version: 0.1.0",
            ]
        )
    )

    assert result(payload)["governance_result"] == "failure"
    assert any("required_final_stage" in reason for reason in result(payload)["failure_reasons"])


def test_failure_when_required_final_stage_is_not_ut():
    payload = evaluate(
        "\n".join(
            [
                "Closes #123",
                "target_version: 0.1.0",
                "required_final_stage: ST",
            ]
        )
    )

    assert result(payload)["governance_result"] == "failure"
    assert any("UT" in reason for reason in result(payload)["failure_reasons"])


def test_failure_when_pr_body_and_branch_issue_do_not_match():
    payload = evaluate(
        "\n".join(
            [
                "Closes #123",
                "target_version: 0.1.0",
                "required_final_stage: UT",
            ]
        ),
        branch="feature/issue-456-change",
    )

    assert result(payload)["governance_result"] == "failure"
    assert any("一致しません" in reason for reason in result(payload)["failure_reasons"])


def test_failure_when_multiple_issue_candidates_exist():
    payload = evaluate(
        "\n".join(
            [
                "Closes #123",
                "Related: #456",
                "target_version: 0.1.0",
                "required_final_stage: UT",
            ]
        ),
        branch="feature/issue-123-change",
    )

    assert result(payload)["governance_result"] == "failure"
    assert any("複数" in reason for reason in result(payload)["failure_reasons"])


def test_repeated_same_issue_candidate_is_not_ambiguous():
    payload = evaluate(
        "\n".join(
            [
                "Closes #123",
                "Issue: #123",
                "target_version: 0.1.0",
                "required_final_stage: UT",
            ]
        ),
        branch="feature/123-change",
    )

    assert result(payload)["governance_result"] == "success"
