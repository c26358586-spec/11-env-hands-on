#!/usr/bin/env python3
# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import urlopen

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
]

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
    prerequisites_met: bool = False
    upstream_ready: bool = False
    artifact_ready: bool = False
    environment_face_id: str = ""
    environment_creation_state: str = "NotStarted"
    readiness_check_execution_state: str = "NotStarted"
    readiness_check_result: str = "FailedBeforeCheck"
    test_execution_state: str = "NotStarted"
    overall_test_result: str = "FailedBeforeTest"
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
    parser = argparse.ArgumentParser(description="Run the Lesson 5.4 disposable UT environment lifecycle.")
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
    if state.readiness_check_result == "Passed":
        return "Passed"
    if state.readiness_check_result == "FailedBeforeCheck":
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


def run_command(
    args: list[str],
    *,
    cwd: Path,
    log_path: Path,
    append: bool = False,
    check: bool = False,
) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
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
) -> None:
    inventory = output_dir / "inventory.yml"
    if not inventory.exists():
        state.failure_reasons.append("Ansible inventory was not created")
        state.environment_creation_state = "Failed"
        state.readiness_check_execution_state = "Skipped"
        state.readiness_check_result = "FailedBeforeCheck"
        state.test_execution_state = "Failed"
        state.overall_test_result = derive_overall_test_result(state)
        return

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
        state.overall_test_result = derive_overall_test_result(state)
        return

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
        state.overall_test_result = derive_overall_test_result(state)
        return

    state.environment_creation_state = "Completed"
    state.readiness_check_execution_state = "InProgress"

    container_name = outputs.get("container_name", "")
    if not container_name:
        state.failure_reasons.append("container_name output is missing")
        state.readiness_check_execution_state = "Failed"
        state.readiness_check_result = "Failed"
        state.test_execution_state = "Failed"
        state.overall_test_result = derive_overall_test_result(state)
        return

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

    state.readiness_check_execution_state = "Failed" if failed else "Completed"
    state.readiness_check_result = "Failed" if failed else "Passed"
    state.test_execution_state = state.readiness_check_execution_state
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
            f"| Overall test result | `{manifest['overall_test_result']}` |",
            f"| Cleanup state | `{manifest['cleanup_state']}` |",
            f"| Remaining resource count | `{manifest['remaining_resource_count']}` |",
            f"| Environment lifecycle result | `{result_payload['environment_lifecycle_result']}` |",
            f"| Test execution state (compatibility) | `{manifest['test_execution_state']}` |",
            f"| Cleanup target count | `{manifest['cleanup_target_count']}` |",
            f"| Cleanup warning | `{str(manifest['cleanup_warning']).lower()}` |",
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
                state.overall_test_result = derive_overall_test_result(state)
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
                run_ansible_and_checks(
                    args,
                    state,
                    root=root,
                    output_dir=output_dir,
                    logs_dir=logs_dir,
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
        ensure_placeholder_logs(logs_dir)

    if state.readiness_check_execution_state == "NotStarted":
        state.readiness_check_execution_state = "Skipped"
        state.readiness_check_result = "FailedBeforeCheck"
    state.overall_test_result = derive_overall_test_result(state)

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
            "cleanup_state": state.cleanup_state,
            "cleanup_warning": state.cleanup_warning,
            "cleanup_target_count": state.cleanup_target_count,
            "remaining_resource_count": state.remaining_resource_count,
            "residue_verification_result": state.residue_verification_result,
            "failure_reason_count": len(state.failure_reasons),
        },
    )
    append_step_summary(args.github_step_summary, summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
