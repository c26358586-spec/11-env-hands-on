# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

import importlib.util
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "pr-ci"
sys.path.insert(0, str(SCRIPT_DIR))
import pr_ci_common

MODULE_PATH = SCRIPT_DIR / "environment_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("environment_lifecycle", MODULE_PATH)
environment_lifecycle = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = environment_lifecycle
SPEC.loader.exec_module(environment_lifecycle)


@pytest.fixture(autouse=True)
def stub_git_metadata(monkeypatch):
    monkeypatch.setattr(pr_ci_common, "git_value", lambda args, *, cwd: "test-git-value")


def write_build_artifact(build_dir, version="v0.0.0+b.1.a.1"):
    build_dir.mkdir()
    binary = build_dir / "go-app-linux-amd64"
    binary.write_bytes(b"fake-linux-amd64-binary")
    checksum = hashlib.sha256(binary.read_bytes()).hexdigest()
    (build_dir / "go-app-linux-amd64.sha256").write_text(
        f"{checksum}  go-app-linux-amd64\n",
        encoding="utf-8",
    )
    (build_dir / "manifest.json").write_text(
        json.dumps({"build_artifact_version": version}),
        encoding="utf-8",
    )
    return checksum


def write_formal_junit(path, test_key):
    expected_ids = environment_lifecycle.FORMAL_TEST_CASE_IDS[test_key]
    suite = ET.Element(
        "testsuite",
        {
            "name": f"{test_key}-test",
            "tests": str(len(expected_ids)),
            "failures": "0",
            "errors": "0",
            "skipped": "0",
        },
    )
    for index, test_case_id in enumerate(expected_ids, start=1):
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": f"tests.{test_key}",
                "name": f"test_formal_case_{index}",
                "time": "0.01",
            },
        )
        properties = ET.SubElement(case, "properties")
        ET.SubElement(
            properties,
            "property",
            {"name": "test_case_id", "value": test_case_id},
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


FORMAL_TEST_CASE_RESULT_KEYS = {
    "test_case_id",
    "name",
    "result",
    "duration_seconds",
    "message",
}


def assert_formal_test_case_schema(case):
    assert set(case) == FORMAL_TEST_CASE_RESULT_KEYS
    assert "id" not in case
    assert "duration" not in case
    assert isinstance(case["duration_seconds"], float)


def test_environment_face_id_uses_issue_run_and_attempt():
    assert environment_lifecycle.environment_face_id("7", "123456", "2") == "UT-7-123456-A2"


def test_parse_junit_detects_id_integrity_and_case_results(tmp_path):
    junit_path = tmp_path / "junit.xml"
    junit_path.write_text(
        """<?xml version='1.0' encoding='utf-8'?>
<testsuites>
  <testsuite tests='4' failures='1' errors='1' skipped='1'>
    <testcase classname='infra' name='passed' time='0.1'><properties><property name='test_case_id' value='INF-001' /></properties></testcase>
    <testcase classname='infra' name='failed' time='0.2'><properties><property name='test_case_id' value='INF-001' /></properties><failure message='assertion failed'>details</failure></testcase>
    <testcase classname='infra' name='errored'><properties><property name='test_case_id' value='INF-999' /></properties><error message='fixture failed' /></testcase>
    <testcase classname='infra' name='skipped'><skipped message='not available' /></testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    analysis = environment_lifecycle.parse_junit_results(
        junit_path,
        ["INF-001", "INF-002"],
    )

    assert analysis["counts"] == {
        "total": 4,
        "passed": 1,
        "failed": 1,
        "errors": 1,
        "skipped": 1,
    }
    assert analysis["collected_case_ids"] == ["INF-001", "INF-001", "INF-999"]
    assert analysis["missing_case_ids"] == ["INF-002"]
    assert analysis["unexpected_case_ids"] == ["INF-999"]
    assert analysis["duplicate_case_ids"] == ["INF-001"]
    assert analysis["property_missing_cases"] == ["infra::skipped"]
    assert [case["result"] for case in analysis["test_cases"]] == [
        "Passed",
        "Failed",
        "Error",
        "Skipped",
    ]
    assert [case["test_case_id"] for case in analysis["test_cases"]] == [
        "INF-001",
        "INF-001",
        "INF-999",
        "",
    ]
    assert [case["duration_seconds"] for case in analysis["test_cases"]] == [
        0.1,
        0.2,
        0.0,
        0.0,
    ]
    assert [case["message"] for case in analysis["test_cases"]] == [
        "",
        "assertion failed",
        "fixture failed",
        "not available",
    ]
    for case in analysis["test_cases"]:
        assert_formal_test_case_schema(case)
    reasons = environment_lifecycle.junit_integrity_reasons(analysis)
    assert len(reasons) == 4


def test_pytest_suite_writes_failure_placeholder_when_junit_is_missing(tmp_path):
    output_dir = tmp_path / "evidence"
    state = environment_lifecycle.LifecycleState()
    original_run_command = environment_lifecycle.run_command

    def fake_run_command(args, *, cwd, log_path, append=False, check=False, env=None):
        environment_lifecycle.write_log(log_path, "$ pytest\npytest crashed before junit\n")
        return environment_lifecycle.CommandResult(args, 2, "pytest crashed before junit\n")

    environment_lifecycle.run_command = fake_run_command
    try:
        execution_state, result = environment_lifecycle.run_pytest_suite(
            state=state,
            test_key="infrastructure",
            title="infrastructure-test",
            command=[
                "pytest",
                "--junitxml",
                str(output_dir / "test-results" / "infrastructure-test-junit.xml"),
            ],
            env={},
            root=tmp_path,
            output_dir=output_dir,
        )
    finally:
        environment_lifecycle.run_command = original_run_command

    assert execution_state == "Failed"
    assert result == "Failed"
    assert state.detected_missing_evidence == ["test-results/infrastructure-test-junit.xml"]
    assert state.evidence_missing_reasons == [
        "test-results/infrastructure-test-junit.xml: "
        "JUnit XML was not created at test-results/infrastructure-test-junit.xml"
    ]
    junit_path = output_dir / "test-results" / "infrastructure-test-junit.xml"
    payload = json.loads(
        (output_dir / "test-results" / "infrastructure-test-result.json").read_text(encoding="utf-8")
    )
    assert payload["junit_xml"] == "test-results/infrastructure-test-junit.xml"
    assert payload["test_cases"] == []
    suite = ET.parse(junit_path).getroot()
    assert suite.attrib["failures"] == "1"
    assert suite.find("testcase/failure") is not None

    for relative_path in environment_lifecycle.EXPECTED_EVIDENCE:
        path = output_dir / relative_path
        if not path.exists():
            environment_lifecycle.write_log(path, "synthetic evidence\n")

    args = environment_lifecycle.argparse.Namespace(
        test_run_id="TR-UT-ISSUE-7-100-A1",
        workflow_run_id="100",
        workflow_run_attempt="1",
        job_name="environment-lifecycle",
        pr_number="8",
        issue_number="7",
        pr_head_sha="abc123",
        repository="RanamicusTechnology/11-env-hands-on",
        created_at="2026-07-05T00:00:00Z",
        target_version="0.0.0",
        required_final_stage="UT",
        build_artifact_name="build-go-app_TR-UT-ISSUE-7-100-A1",
        build_artifact_id="5",
        build_artifact_version="v0.0.0+b.1.a.1",
        build_artifact_checksum="abc",
    )
    manifest, result_payload, _summary = environment_lifecycle.finalize_result(
        args,
        state,
        output_dir,
    )
    assert manifest["missing_evidence"] == ["test-results/infrastructure-test-junit.xml"]
    assert manifest["missing_evidence_count"] == 1
    assert manifest["environment_evidence_complete"] is False
    assert result_payload["evidence"]["missing_evidence_count"] == 1
    assert result_payload["evidence"]["environment_evidence_complete"] is False


def test_early_failure_finalizes_environment_evidence_without_docker(tmp_path):
    output_dir = tmp_path / "evidence"
    missing_build_dir = tmp_path / "missing-build-artifact"

    rc = environment_lifecycle.main(
        [
            "--output-dir",
            str(output_dir),
            "--build-artifact-dir",
            str(missing_build_dir),
            "--repository",
            "RanamicusTechnology/11-env-hands-on",
            "--workflow-run-id",
            "100",
            "--workflow-run-attempt",
            "1",
            "--test-run-id",
            "TR-UT-ISSUE-7-100-A1",
            "--issue-number",
            "7",
            "--target-version",
            "0.0.0",
            "--required-final-stage",
            "UT",
            "--pr-number",
            "8",
            "--pr-head-sha",
            "abc123",
            "--governance-job-result",
            "failure",
            "--governance-result",
            "failure",
            "--static-analysis-job-result",
            "skipped",
            "--static-analysis-result",
            "",
            "--unit-test-job-result",
            "skipped",
            "--unit-test-result",
            "",
            "--build-package-job-result",
            "skipped",
            "--build-package-result",
            "",
            "--build-artifact-name",
            "",
            "--build-artifact-id",
            "",
            "--build-artifact-version",
            "",
            "--build-artifact-checksum",
            "",
            "--build-artifact-uploaded",
            "false",
            "--created-at",
            "2026-07-05T00:00:00Z",
        ]
    )

    assert rc == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads(
        (output_dir / "environment-lifecycle-result.json").read_text(encoding="utf-8")
    )
    assert result["environment_lifecycle_result"] == "skipped_prerequisites"
    assert manifest["environment_face_id_or_not_created"] == "NOT_CREATED"
    assert manifest["environment_creation_state"] == "NotStarted"
    assert manifest["readiness_check_execution_state"] == "Skipped"
    assert manifest["readiness_check_result"] == "FailedBeforeCheck"
    assert manifest["overall_test_result"] == "FailedBeforeTest"
    assert manifest["test_result"] == "FailedBeforeTest"
    assert manifest["infrastructure_test_execution_state"] == "Skipped"
    assert manifest["infrastructure_test_result"] == "FailedBeforeTest"
    assert manifest["api_test_execution_state"] == "Skipped"
    assert manifest["api_test_result"] == "FailedBeforeTest"
    assert manifest["cleanup_state"] == "Completed"
    assert manifest["cleanup_target_count"] == 0
    assert manifest["remaining_resource_count"] == 0
    assert "NotRequired" not in json.dumps(manifest)
    assert (output_dir / "test-results" / "infrastructure-test-junit.xml").exists()
    assert (output_dir / "test-results" / "api-test-result.json").exists()
    assert result["tests"]["infrastructure"]["result"] == "FailedBeforeTest"
    assert result["tests"]["api"]["result"] == "FailedBeforeTest"


def test_residue_verification_preserves_cleanup_not_attempted(tmp_path):
    state = environment_lifecycle.LifecycleState(
        prerequisites_met=True,
        cleanup_state="NotAttempted",
    )
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    environment_lifecycle.verify_residue(
        state,
        root=tmp_path,
        logs_dir=logs_dir,
        label_filter="label=test_run_id=TR-UT-ISSUE-7-100-A1",
    )

    assert state.cleanup_state == "NotAttempted"
    assert state.residue_verification_result == "NotAttempted"


def test_terraform_fmt_failure_before_apply_records_completed_cleanup(tmp_path):
    output_dir = tmp_path / "evidence"
    build_dir = tmp_path / "build-artifact"
    version = "v0.0.0+b.1.a.1"
    checksum = write_build_artifact(build_dir, version)
    original_run_command = environment_lifecycle.run_command

    def fake_run_command(args, *, cwd, log_path, append=False, check=False, env=None):
        command = " ".join(args)
        if args[:2] == ["docker", "build"]:
            result = environment_lifecycle.CommandResult(args, 0, "image built\n")
        elif args == ["terraform", "fmt", "-check"]:
            result = environment_lifecycle.CommandResult(args, 1, "main.tf\n")
        elif args[0] == "docker":
            result = environment_lifecycle.CommandResult(args, 0, "")
        else:
            result = environment_lifecycle.CommandResult(args, 0, "")

        message = f"$ {command}\n{result.stdout}"
        if append:
            environment_lifecycle.append_log(log_path, message)
        else:
            environment_lifecycle.write_log(log_path, message)
        return result

    environment_lifecycle.run_command = fake_run_command
    try:
        rc = environment_lifecycle.main(
            [
                "--output-dir",
                str(output_dir),
                "--build-artifact-dir",
                str(build_dir),
                "--repository",
                "RanamicusTechnology/11-env-hands-on",
                "--workflow-run-id",
                "28729279045",
                "--workflow-run-attempt",
                "1",
                "--test-run-id",
                "TR-UT-ISSUE-7-28729279045-A1",
                "--issue-number",
                "7",
                "--target-version",
                "0.0.0",
                "--required-final-stage",
                "UT",
                "--pr-number",
                "8",
                "--pr-head-sha",
                "6780c750712f373187be0654642548eb6e93f841",
                "--governance-job-result",
                "success",
                "--governance-result",
                "success",
                "--static-analysis-job-result",
                "success",
                "--static-analysis-result",
                "success",
                "--unit-test-job-result",
                "success",
                "--unit-test-result",
                "success",
                "--build-package-job-result",
                "success",
                "--build-package-result",
                "success",
                "--build-artifact-name",
                "build-go-app_TR-UT-ISSUE-7-28729279045-A1",
                "--build-artifact-id",
                "8088230457",
                "--build-artifact-version",
                version,
                "--build-artifact-checksum",
                checksum,
                "--build-artifact-uploaded",
                "true",
                "--created-at",
                "2026-07-05T00:00:00Z",
            ]
        )
    finally:
        environment_lifecycle.run_command = original_run_command

    assert rc == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads(
        (output_dir / "environment-lifecycle-result.json").read_text(encoding="utf-8")
    )
    assert result["environment_lifecycle_result"] == "failure"
    assert result["failure_reasons"] == ["terraform fmt -check failed"]
    assert result["cleanup"]["environment_resources_may_exist"] is False
    assert result["cleanup"]["cleanup_attempted"] is True
    assert manifest["environment_creation_state"] == "Failed"
    assert manifest["readiness_check_execution_state"] == "Skipped"
    assert manifest["readiness_check_result"] == "FailedBeforeCheck"
    assert manifest["overall_test_result"] == "FailedBeforeTest"
    assert manifest["infrastructure_test_execution_state"] == "Skipped"
    assert manifest["infrastructure_test_result"] == "FailedBeforeTest"
    assert manifest["api_test_execution_state"] == "Skipped"
    assert manifest["api_test_result"] == "FailedBeforeTest"
    assert manifest["cleanup_state"] == "Completed"
    assert manifest["cleanup_target_count"] == 0
    assert manifest["remaining_resource_count"] == 0
    assert manifest["residue_verification_result"] == "Passed"
    assert manifest["cleanup_warning"] is False
    assert result["tests"]["infrastructure"]["result"] == "FailedBeforeTest"
    assert result["tests"]["api"]["result"] == "FailedBeforeTest"


@pytest.mark.parametrize(
    ("failure_stage", "expected_environment_state", "expected_readiness_state"),
    [
        ("ansible-infra", "Failed", "Skipped"),
        ("app-deploy", "Failed", "Skipped"),
        ("readiness", "Completed", "Failed"),
    ],
)
def test_ansible_deploy_and_readiness_failures_have_distinct_states(
    tmp_path,
    failure_stage,
    expected_environment_state,
    expected_readiness_state,
):
    output_dir = tmp_path / "evidence"
    logs_dir = output_dir / "logs"
    output_dir.mkdir()
    logs_dir.mkdir()
    (output_dir / "inventory.yml").write_text("all:\n  hosts: {}\n", encoding="utf-8")
    state = environment_lifecycle.LifecycleState(environment_creation_state="InProgress")
    args = environment_lifecycle.argparse.Namespace(
        build_artifact_dir=str(tmp_path / "build-artifact"),
        build_artifact_version="v0.0.0+b.1.a.1",
    )
    original_run_command = environment_lifecycle.run_command

    def fake_run_command(args, *, cwd, log_path, append=False, check=False, env=None):
        if failure_stage == "ansible-infra" and "ansible/infra/site.yml" in args:
            return environment_lifecycle.CommandResult(args, 1, "infra failed\n")
        if failure_stage == "app-deploy" and "ansible/deploy/site.yml" in args:
            return environment_lifecycle.CommandResult(args, 1, "deploy failed\n")
        if failure_stage == "readiness" and args[:2] == ["docker", "exec"]:
            return environment_lifecycle.CommandResult(args, 1, "check failed\n")
        return environment_lifecycle.CommandResult(args, 0, "")

    environment_lifecycle.run_command = fake_run_command
    try:
        ready = environment_lifecycle.run_ansible_and_checks(
            args,
            state,
            root=tmp_path,
            output_dir=output_dir,
            logs_dir=logs_dir,
            outputs={"container_name": "target"},
        )
    finally:
        environment_lifecycle.run_command = original_run_command

    assert ready is False
    assert state.environment_creation_state == expected_environment_state
    assert state.readiness_check_execution_state == expected_readiness_state
    assert state.readiness_check_result == (
        "Failed" if failure_stage == "readiness" else "FailedBeforeCheck"
    )


def test_formal_test_failure_is_derived_from_junit_case_results(tmp_path):
    output_dir = tmp_path / "evidence"
    junit_path = output_dir / "test-results" / "api-test-junit.xml"
    write_formal_junit(junit_path, "api")
    tree = ET.parse(junit_path)
    failed_case = tree.getroot().find("testcase")
    assert failed_case is not None
    ET.SubElement(failed_case, "failure", {"message": "health assertion failed"})
    tree.write(junit_path, encoding="utf-8", xml_declaration=True)
    state = environment_lifecycle.LifecycleState()
    original_run_command = environment_lifecycle.run_command

    def fake_run_command(args, *, cwd, log_path, append=False, check=False, env=None):
        environment_lifecycle.write_log(log_path, "$ pytest\n1 failed, 3 passed\n")
        return environment_lifecycle.CommandResult(args, 1, "1 failed, 3 passed\n")

    environment_lifecycle.run_command = fake_run_command
    try:
        execution_state, result = environment_lifecycle.run_pytest_suite(
            state=state,
            test_key="api",
            title="api-test",
            command=["pytest", "tests/api"],
            env={},
            root=tmp_path,
            output_dir=output_dir,
        )
    finally:
        environment_lifecycle.run_command = original_run_command

    assert execution_state == "Failed"
    assert result == "Failed"
    payload = json.loads(
        (output_dir / "test-results" / "api-test-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["counts"] == {
        "total": 4,
        "passed": 3,
        "failed": 1,
        "errors": 0,
        "skipped": 0,
    }
    assert_formal_test_case_schema(payload["test_cases"][0])
    assert payload["test_cases"][0]["test_case_id"] == "API-001"
    assert payload["test_cases"][0]["message"] == "health assertion failed"


def test_successful_lifecycle_records_formal_test_results(tmp_path):
    output_dir = tmp_path / "evidence"
    build_dir = tmp_path / "build-artifact"
    github_output = tmp_path / "github-output.txt"
    version = "v0.0.0+b.1.a.1"
    checksum = write_build_artifact(build_dir, version)
    original_run_command = environment_lifecycle.run_command
    original_urlopen = environment_lifecycle.urlopen

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps({"status": "ok", "version": version}).encode("utf-8")

    def fake_urlopen(url, timeout):
        return FakeResponse()

    def fake_run_command(args, *, cwd, log_path, append=False, check=False, env=None):
        command = " ".join(args)
        if args[:2] == ["docker", "build"]:
            result = environment_lifecycle.CommandResult(args, 0, "image built\n")
        elif args[:2] == ["terraform", "output"]:
            output_name = args[-1]
            outputs = {
                "ansible_inventory": "all:\n  hosts:\n    ms1_target:\n",
                "container_name": "ut-7-target",
                "network_name": "ut-7-net",
                "host_http_url": "http://127.0.0.1:18080",
            }
            result = environment_lifecycle.CommandResult(args, 0, outputs[output_name])
        elif len(args) >= 3 and args[0] == environment_lifecycle.sys.executable and args[1:3] == ["-m", "pytest"]:
            junit_path = Path(args[args.index("--junitxml") + 1])
            test_key = "infrastructure" if "infrastructure" in junit_path.name else "api"
            write_formal_junit(junit_path, test_key)
            case_count = len(environment_lifecycle.FORMAL_TEST_CASE_IDS[test_key])
            result = environment_lifecycle.CommandResult(args, 0, f"{case_count} passed\n")
        else:
            result = environment_lifecycle.CommandResult(args, 0, "")

        message = f"$ {command}\n{result.stdout}"
        if append:
            environment_lifecycle.append_log(log_path, message)
        else:
            environment_lifecycle.write_log(log_path, message)
        return result

    environment_lifecycle.run_command = fake_run_command
    environment_lifecycle.urlopen = fake_urlopen
    try:
        rc = environment_lifecycle.main(
            [
                "--output-dir",
                str(output_dir),
                "--build-artifact-dir",
                str(build_dir),
                "--repository",
                "RanamicusTechnology/11-env-hands-on",
                "--workflow-run-id",
                "28729279045",
                "--workflow-run-attempt",
                "1",
                "--test-run-id",
                "TR-UT-ISSUE-7-28729279045-A1",
                "--issue-number",
                "7",
                "--target-version",
                "0.0.0",
                "--required-final-stage",
                "UT",
                "--pr-number",
                "8",
                "--pr-head-sha",
                "6780c750712f373187be0654642548eb6e93f841",
                "--governance-job-result",
                "success",
                "--governance-result",
                "success",
                "--static-analysis-job-result",
                "success",
                "--static-analysis-result",
                "success",
                "--unit-test-job-result",
                "success",
                "--unit-test-result",
                "success",
                "--build-package-job-result",
                "success",
                "--build-package-result",
                "success",
                "--build-artifact-name",
                "build-go-app_TR-UT-ISSUE-7-28729279045-A1",
                "--build-artifact-id",
                "8088230457",
                "--build-artifact-version",
                version,
                "--build-artifact-checksum",
                checksum,
                "--build-artifact-uploaded",
                "true",
                "--github-output",
                str(github_output),
                "--created-at",
                "2026-07-05T00:00:00Z",
            ]
        )
    finally:
        environment_lifecycle.run_command = original_run_command
        environment_lifecycle.urlopen = original_urlopen

    assert rc == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads(
        (output_dir / "environment-lifecycle-result.json").read_text(encoding="utf-8")
    )
    assert result["environment_lifecycle_result"] == "success"
    assert manifest["environment_creation_state"] == "Completed"
    assert manifest["readiness_check_execution_state"] == "Completed"
    assert manifest["readiness_check_result"] == "Passed"
    assert manifest["overall_test_result"] == "Passed"
    assert manifest["test_result"] == "Passed"
    assert manifest["test_result_alias_of"] == "overall_test_result"
    assert manifest["infrastructure_test_execution_state"] == "Completed"
    assert manifest["infrastructure_test_result"] == "Passed"
    assert manifest["api_test_execution_state"] == "Completed"
    assert manifest["api_test_result"] == "Passed"
    assert manifest["missing_evidence"] == []
    assert manifest["missing_evidence_count"] == 0
    assert manifest["environment_evidence_complete"] is True
    assert result["evidence"]["missing_evidence_count"] == 0
    assert result["evidence"]["environment_evidence_complete"] is True
    assert result["tests"]["infrastructure"]["result_files"] == [
        "test-results/infrastructure-test-junit.xml",
        "test-results/infrastructure-test-result.json",
        "summaries/infrastructure-test-summary.md",
    ]
    infrastructure_result = json.loads(
        (output_dir / "test-results" / "infrastructure-test-result.json").read_text(
            encoding="utf-8"
        )
    )
    api_result = json.loads(
        (output_dir / "test-results" / "api-test-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert infrastructure_result["counts"] == {
        "total": 9,
        "passed": 9,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
    }
    assert infrastructure_result["collected_case_ids"] == [
        f"INF-{index:03d}" for index in range(1, 10)
    ]
    assert infrastructure_result["missing_case_ids"] == []
    assert infrastructure_result["unexpected_case_ids"] == []
    assert len(infrastructure_result["test_cases"]) == 9
    for case in infrastructure_result["test_cases"]:
        assert_formal_test_case_schema(case)
    assert api_result["counts"] == {
        "total": 4,
        "passed": 4,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
    }
    assert api_result["collected_case_ids"] == [
        f"API-{index:03d}" for index in range(1, 5)
    ]
    assert api_result["missing_case_ids"] == []
    assert api_result["unexpected_case_ids"] == []
    assert len(api_result["test_cases"]) == 4
    for case in api_result["test_cases"]:
        assert_formal_test_case_schema(case)
    assert "logs/infrastructure-test.log" in manifest["collected_evidence"]
    assert "test-results/api-test-junit.xml" in manifest["collected_evidence"]
    outputs = github_output.read_text(encoding="utf-8")
    assert "missing_evidence_count=0" in outputs
    assert "environment_evidence_complete=true" in outputs
    assert "readiness_check_execution_state=Completed" in outputs
    assert "readiness_check_result=Passed" in outputs
    assert "overall_test_result=Passed" in outputs
    assert "test_result_alias_of=overall_test_result" in outputs
