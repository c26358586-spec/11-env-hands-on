# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

import importlib.util
import hashlib
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "pr-ci"
sys.path.insert(0, str(SCRIPT_DIR))
MODULE_PATH = SCRIPT_DIR / "environment_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("environment_lifecycle", MODULE_PATH)
environment_lifecycle = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = environment_lifecycle
SPEC.loader.exec_module(environment_lifecycle)


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


def test_environment_face_id_uses_issue_run_and_attempt():
    assert environment_lifecycle.environment_face_id("7", "123456", "2") == "UT-7-123456-A2"


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
    assert manifest["test_result"] == "FailedBeforeTest"
    assert manifest["cleanup_state"] == "Completed"
    assert manifest["cleanup_target_count"] == 0
    assert manifest["remaining_resource_count"] == 0
    assert "NotRequired" not in json.dumps(manifest)


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

    def fake_run_command(args, *, cwd, log_path, append=False, check=False):
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
    assert manifest["cleanup_state"] == "Completed"
    assert manifest["cleanup_target_count"] == 0
    assert manifest["remaining_resource_count"] == 0
    assert manifest["residue_verification_result"] == "Passed"
    assert manifest["cleanup_warning"] is False
