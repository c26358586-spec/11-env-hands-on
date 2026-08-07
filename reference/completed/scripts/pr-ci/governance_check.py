#!/usr/bin/env python3
# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BODY_ISSUE_PATTERNS = (
    re.compile(r"\b(?:Closes|Fixes|Resolves)\s+#(?P<number>\d+)\b", re.IGNORECASE),
    re.compile(r"\b(?:Related|Issue)\s*:\s*#(?P<number>\d+)\b", re.IGNORECASE),
)
BRANCH_ISSUE_PATTERN = re.compile(
    r"^(?:feature|fix)/(?:issue-)?(?P<number>\d+)(?:[-_/].*)?$",
    re.IGNORECASE,
)
PLACEHOLDER_PATTERN = re.compile(r"^<[^>]+>$")


def unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


def extract_body_issue_numbers(body: str) -> list[str]:
    numbers: list[str] = []
    for pattern in BODY_ISSUE_PATTERNS:
        numbers.extend(match.group("number") for match in pattern.finditer(body or ""))
    return unique_in_order(numbers)


def extract_branch_issue_numbers(branch_name: str) -> list[str]:
    match = BRANCH_ISSUE_PATTERN.match(branch_name or "")
    if not match:
        return []
    return [match.group("number")]


def extract_metadata_value(body: str, key: str) -> str:
    pattern = re.compile(
        rf"^[ \t]*{re.escape(key)}[ \t]*:[ \t]*(?P<value>.*?)[ \t]*$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(body or "")
    if not match:
        return ""
    value = match.group("value").strip()
    if not value or PLACEHOLDER_PATTERN.match(value):
        return ""
    return value


def resolve_issue_number(body_numbers: list[str], branch_numbers: list[str]) -> tuple[str, list[str]]:
    failure_reasons: list[str] = []

    if len(body_numbers) > 1:
        failure_reasons.append(
            "PR本文に複数のIssue番号候補があります。候補を1つにしてください。"
        )
    if len(branch_numbers) > 1:
        failure_reasons.append(
            "branch名に複数のIssue番号候補があります。候補を1つにしてください。"
        )

    body_issue = body_numbers[0] if len(body_numbers) == 1 else ""
    branch_issue = branch_numbers[0] if len(branch_numbers) == 1 else ""

    if body_issue and branch_issue and body_issue != branch_issue:
        failure_reasons.append(
            f"PR本文のIssue番号とbranch名のIssue番号が一致しません。body={body_issue} branch={branch_issue}"
        )

    if body_issue:
        return body_issue, failure_reasons
    if branch_issue:
        return branch_issue, failure_reasons

    failure_reasons.append(
        "Issue番号候補を取得できません。PR本文にCloses #<issue-number>等を記載するか、branch名をfeature/issue-<number>-...形式にしてください。"
    )
    return "UNLINKED", failure_reasons


def lookup_issue_state(
    repository: str,
    issue_number: str,
    token: str | None,
    api_url: str,
) -> dict[str, Any]:
    if not token:
        return {
            "checked": False,
            "ok": True,
            "state": None,
            "message": "GITHUB_TOKENがないためIssue状態確認をskipしました。",
        }

    url = f"{api_url.rstrip('/')}/repos/{repository}/issues/{issue_number}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ranamicus-pr-ci-governance-check",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "checked": True,
                "ok": False,
                "state": None,
                "message": f"Issue #{issue_number} が見つかりません。",
            }
        return {
            "checked": False,
            "ok": True,
            "state": None,
            "message": f"Issue状態確認をskipしました。GitHub API HTTP status={exc.code}",
        }
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "checked": False,
            "ok": True,
            "state": None,
            "message": f"Issue状態確認をskipしました。reason={exc}",
        }

    state = str(payload.get("state", ""))
    return {
        "checked": True,
        "ok": state == "open",
        "state": state,
        "message": f"Issue #{issue_number} state={state}",
    }


def evaluate_governance(
    *,
    pr_body: str,
    pr_head_ref: str,
    repository: str,
    workflow_name: str,
    workflow_run_id: str,
    workflow_run_attempt: str,
    job_name: str,
    pr_number: str,
    pr_head_sha: str,
    created_at: str,
    token: str | None = None,
    api_url: str = "https://api.github.com",
    check_issue_state: bool = True,
) -> dict[str, Any]:
    body_issue_numbers = extract_body_issue_numbers(pr_body)
    branch_issue_numbers = extract_branch_issue_numbers(pr_head_ref)
    issue_number, failure_reasons = resolve_issue_number(body_issue_numbers, branch_issue_numbers)

    target_version = extract_metadata_value(pr_body, "target_version")
    required_final_stage = extract_metadata_value(pr_body, "required_final_stage")

    if not target_version:
        failure_reasons.append("PR本文のtarget_versionが未記載、空、またはテンプレート値のままです。")

    if not required_final_stage:
        failure_reasons.append("PR本文のrequired_final_stageが未記載、空、またはテンプレート値のままです。")
    elif required_final_stage != "UT":
        failure_reasons.append(
            f"required_final_stageはLesson 5.2ではUTのみ許容します。actual={required_final_stage}"
        )

    issue_check = {
        "checked": False,
        "ok": True,
        "state": None,
        "message": "Issue未関連付けのためIssue状態確認を実行していません。",
    }
    if issue_number != "UNLINKED" and check_issue_state:
        issue_check = lookup_issue_state(repository, issue_number, token, api_url)
        if issue_check["checked"] and not issue_check["ok"]:
            failure_reasons.append(str(issue_check["message"]))

    if issue_number == "UNLINKED":
        test_run_id = f"TR-UT-UNLINKED-{workflow_run_id}-A{workflow_run_attempt}"
    else:
        test_run_id = f"TR-UT-ISSUE-{issue_number}-{workflow_run_id}-A{workflow_run_attempt}"

    governance_result = "success" if not failure_reasons else "failure"
    artifact_name = f"evidence-governance_{test_run_id}"

    manifest = {
        "test_run_id": test_run_id,
        "repository": repository,
        "workflow_name": workflow_name,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "job_name": job_name,
        "pr_number": pr_number,
        "pr_head_ref": pr_head_ref,
        "pr_head_sha": pr_head_sha,
        "issue_number": issue_number,
        "target_version": target_version,
        "required_final_stage": required_final_stage,
        "governance_result": governance_result,
        "artifact_name": artifact_name,
        "created_at": created_at,
    }

    return {
        "manifest": manifest,
        "governance_result": {
            "governance_result": governance_result,
            "failure_reasons": failure_reasons,
            "body_issue_numbers": body_issue_numbers,
            "branch_issue_numbers": branch_issue_numbers,
            "issue_number": issue_number,
            "target_version": target_version,
            "required_final_stage": required_final_stage,
            "issue_check": issue_check,
        },
    }


def build_summary(manifest: dict[str, Any], result: dict[str, Any]) -> str:
    failure_reasons = result["failure_reasons"] or ["なし"]
    reason_lines = "\n".join(f"- {reason}" for reason in failure_reasons)
    return "\n".join(
        [
            "# governance-check Summary",
            "",
            "| Item | Value |",
            "|---|---|",
            f"| Test run ID | `{manifest['test_run_id']}` |",
            f"| Pull Request | `#{manifest['pr_number']}` |",
            f"| Branch | `{manifest['pr_head_ref']}` |",
            f"| Head SHA | `{manifest['pr_head_sha']}` |",
            f"| Issue | `{manifest['issue_number']}` |",
            f"| target_version | `{manifest['target_version'] or '<missing>'}` |",
            f"| required_final_stage | `{manifest['required_final_stage'] or '<missing>'}` |",
            f"| Governance result | `{manifest['governance_result']}` |",
            f"| Workflow run ID | `{manifest['workflow_run_id']}` |",
            f"| Run attempt | `A{manifest['workflow_run_attempt']}` |",
            f"| Evidence Artifact | `{manifest['artifact_name']}` |",
            "",
            "## Governance failure reasons",
            "",
            reason_lines,
            "",
        ]
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_github_output(path: str, manifest: dict[str, Any], result: dict[str, Any]) -> None:
    outputs = {
        "test_run_id": manifest["test_run_id"],
        "governance_result": manifest["governance_result"],
        "issue_number": manifest["issue_number"],
        "target_version": manifest["target_version"],
        "required_final_stage": manifest["required_final_stage"],
        "evidence_artifact_name": manifest["artifact_name"],
        "failure_reason_count": str(len(result["failure_reasons"])),
    }
    with open(path, "a", encoding="utf-8") as output_file:
        for key, value in outputs.items():
            output_file.write(f"{key}={value}\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Lesson 5.2 PR CI governance checks.")
    parser.add_argument("--event-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-run-attempt", required=True)
    parser.add_argument("--job-name", default="governance-check")
    parser.add_argument("--github-output")
    parser.add_argument("--github-step-summary")
    parser.add_argument("--created-at")
    parser.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    parser.add_argument("--skip-issue-state-check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    event = json.loads(Path(args.event_path).read_text(encoding="utf-8-sig"))
    pull_request = event.get("pull_request") or {}

    created_at = args.created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    evaluation = evaluate_governance(
        pr_body=pull_request.get("body") or "",
        pr_head_ref=(pull_request.get("head") or {}).get("ref") or "",
        repository=args.repository,
        workflow_name=args.workflow_name,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
        job_name=args.job_name,
        pr_number=str(pull_request.get("number") or event.get("number") or ""),
        pr_head_sha=(pull_request.get("head") or {}).get("sha") or "",
        created_at=created_at,
        token=os.environ.get("GITHUB_TOKEN"),
        api_url=args.api_url,
        check_issue_state=not args.skip_issue_state_check,
    )

    manifest = evaluation["manifest"]
    result = evaluation["governance_result"]
    summary = build_summary(manifest, result)

    write_json(output_dir / "manifest.json", manifest)
    write_json(output_dir / "governance-result.json", result)
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")

    if args.github_output:
        write_github_output(args.github_output, manifest, result)
    if args.github_step_summary:
        with open(args.github_step_summary, "a", encoding="utf-8") as summary_file:
            summary_file.write(summary)

    print(summary)
    return 0 if manifest["governance_result"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
