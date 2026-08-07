#!/usr/bin/env python3
# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_timestamp(value: str | None = None) -> str:
    if value:
        return value
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_github_output(path: str | None, outputs: dict[str, Any]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as output_file:
        for key, value in outputs.items():
            if isinstance(value, bool):
                serialized = "true" if value else "false"
            elif value is None:
                serialized = ""
            else:
                serialized = str(value)
            output_file.write(f"{key}={serialized}\n")


def append_step_summary(path: str | None, summary: str) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as summary_file:
        summary_file.write(summary)
        if not summary.endswith("\n"):
            summary_file.write("\n")


def run_command(
    args: list[str],
    *,
    cwd: Path,
    log_path: Path,
    env: dict[str, str] | None = None,
    append: bool = False,
) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        returncode = completed.returncode
        output = completed.stdout or ""
    except OSError as exc:
        returncode = 127
        output = f"ERROR: failed to execute {args[0]}: {exc}\n"
    serialized = f"$ {' '.join(args)}\n{output}"
    mode = "a" if append else "w"
    with log_path.open(mode, encoding="utf-8") as log_file:
        log_file.write(serialized)
        if not serialized.endswith("\n"):
            log_file.write("\n")
    return {
        "command": args,
        "returncode": returncode,
        "stdout": output,
        "log_path": log_path.as_posix(),
    }


def git_value(args: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def relative_existing_files(base_dir: Path, expected_paths: list[str]) -> list[str]:
    collected: list[str] = []
    for relative_path in expected_paths:
        candidate = base_dir / relative_path
        if candidate.exists():
            collected.append(relative_path)
    return collected


def common_evidence_manifest(
    *,
    test_run_id: str,
    workflow_run_id: str,
    workflow_run_attempt: str,
    job_name: str,
    pr_number: str,
    issue_number: str,
    pr_head_sha: str,
    repository: str,
    artifact_name: str,
    generated_timestamp: str,
    expected_evidence: list[str],
    collected_evidence: list[str],
    result: str,
    target_version: str,
    required_final_stage: str,
) -> dict[str, Any]:
    root = repo_root()
    missing_evidence = [
        item for item in expected_evidence if item not in set(collected_evidence)
    ]
    return {
        "test_run_id": test_run_id,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "job_name": job_name,
        "pull_request_number": pr_number,
        "issue_number_or_UNLINKED": issue_number,
        "pr_head_sha": pr_head_sha,
        "tested_git_tree_sha": git_value(["rev-parse", "HEAD^{tree}"], cwd=root),
        "repository": repository,
        "target_version": target_version,
        "required_final_stage": required_final_stage,
        "generated_timestamp": generated_timestamp,
        "artifact_name": artifact_name,
        "retention_days": 30,
        "expected_evidence": expected_evidence,
        "collected_evidence": collected_evidence,
        "missing_evidence": missing_evidence,
        "result": result,
    }


def bool_to_result(value: bool) -> str:
    return "success" if value else "failure"


def env_with(overrides: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(overrides)
    return env
