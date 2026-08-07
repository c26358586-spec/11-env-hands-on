# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "pr-ci"
sys.path.insert(0, str(SCRIPT_DIR))
import pr_ci_common

MODULE_PATH = SCRIPT_DIR / "static_analysis.py"
SPEC = importlib.util.spec_from_file_location("static_analysis", MODULE_PATH)
static_analysis = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(static_analysis)


def test_classify_gofmt_success_when_no_output():
    result, reasons = static_analysis.classify_gofmt(0, "")

    assert result == "success"
    assert reasons == []


def test_classify_gofmt_failure_when_files_are_listed():
    result, reasons = static_analysis.classify_gofmt(0, "main.go\n")

    assert result == "failure"
    assert "main.go" in reasons[0]


def test_classify_gofmt_command_error_does_not_treat_diagnostics_as_file_names():
    result, reasons = static_analysis.classify_gofmt(127, "ERROR: gofmt is unavailable\n")

    assert result == "failure"
    assert reasons == ["gofmt -l exited with rc=127"]


def test_common_run_command_appends_diagnostics_with_command_headers(tmp_path):
    log_path = tmp_path / "command.log"

    pr_ci_common.run_command(
        [sys.executable, "-c", "print('first')"],
        cwd=tmp_path,
        log_path=log_path,
    )
    pr_ci_common.run_command(
        [sys.executable, "-c", "print('second')"],
        cwd=tmp_path,
        log_path=log_path,
        append=True,
    )

    log = log_path.read_text(encoding="utf-8")
    assert log.count("$ ") == 2
    assert "first" in log
    assert "second" in log


def test_static_analysis_adds_gofmt_diff_without_polluting_file_list(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "go.mod").write_text(
        "module example.com/issue40-static-analysis\n\ngo 1.26.0\n",
        encoding="utf-8",
    )
    (app_dir / "main.go").write_text("package main\nfunc main(){println(\"x\")}\n", encoding="utf-8")
    output_dir = tmp_path / "evidence"
    def fake_run_command(args, **kwargs):
        log_path = kwargs["log_path"]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if args == ["gofmt", "-l", "."]:
            output = "main.go\n"
        elif args == ["gofmt", "-d", "."]:
            output = (
                "diff main.go.orig main.go\n"
                "--- main.go.orig\n"
                "+++ main.go\n"
                "@@ -1,2 +1,5 @@\n"
                " package main\n"
                "-func main(){println(\"x\")}\n"
                "+func main() {\n"
                "+\tprintln(\"x\")\n"
                "+}\n"
            )
        else:
            output = ""
        mode = "a" if kwargs.get("append") else "w"
        with log_path.open(mode, encoding="utf-8") as log_file:
            log_file.write(f"$ {' '.join(args)}\n{output}")
        return {"returncode": 0, "stdout": output, "log_path": log_path.as_posix()}

    monkeypatch.setattr(static_analysis, "run_command", fake_run_command)
    monkeypatch.setattr(pr_ci_common, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(pr_ci_common, "git_value", lambda args, *, cwd: "test-git-value")
    original_repo_root = static_analysis.repo_root
    static_analysis.repo_root = lambda: tmp_path
    try:
        rc = static_analysis.main(
            [
                "--output-dir",
                str(output_dir),
                "--repository",
                "RanamicusTechnology/11-env-hands-on",
                "--workflow-run-id",
                "100",
                "--workflow-run-attempt",
                "1",
                "--test-run-id",
                "TR-UT-ISSUE-40-100-A1",
                "--issue-number",
                "40",
                "--target-version",
                "0.0.0",
                "--required-final-stage",
                "UT",
                "--pr-number",
                "41",
                "--pr-head-sha",
                "abc123",
                "--created-at",
                "2026-08-03T00:00:00Z",
            ]
        )
    finally:
        static_analysis.repo_root = original_repo_root

    assert rc == 1
    assert (app_dir / "main.go").read_text(encoding="utf-8") == (
        "package main\nfunc main(){println(\"x\")}\n"
    )
    payload = json.loads(
        (output_dir / "static-analysis-result.json").read_text(encoding="utf-8")
    )
    assert "iac_lint" not in payload["checks"]
    assert payload["checks"]["gofmt"]["unformatted_files"] == ["main.go"]
    assert payload["checks"]["gofmt"]["diff_generated"] is True
    log = (output_dir / "logs" / "gofmt.log").read_text(encoding="utf-8")
    assert "$ gofmt -l ." in log
    assert "$ gofmt -d ." in log
    assert "main.go" in log
    assert "@@" in log
    assert "func main(){println" in log
    assert "func main() {" in log


def test_static_analysis_does_not_run_gofmt_diff_for_formatted_source(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "go.mod").write_text(
        "module example.com/issue40-static-analysis\n\ngo 1.26.0\n",
        encoding="utf-8",
    )
    (app_dir / "main.go").write_bytes(
        b'package main\n\nfunc main() {\n\tprintln("x")\n}\n'
    )
    output_dir = tmp_path / "evidence"
    def fake_run_command(args, **kwargs):
        log_path = kwargs["log_path"]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"$ {' '.join(args)}\n", encoding="utf-8")
        return {"returncode": 0, "stdout": "", "log_path": log_path.as_posix()}

    monkeypatch.setattr(static_analysis, "run_command", fake_run_command)
    monkeypatch.setattr(pr_ci_common, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(pr_ci_common, "git_value", lambda args, *, cwd: "test-git-value")
    original_repo_root = static_analysis.repo_root
    static_analysis.repo_root = lambda: tmp_path
    try:
        rc = static_analysis.main(
            [
                "--output-dir",
                str(output_dir),
                "--repository",
                "RanamicusTechnology/11-env-hands-on",
                "--workflow-run-id",
                "100",
                "--workflow-run-attempt",
                "1",
                "--test-run-id",
                "TR-UT-ISSUE-40-100-A1",
                "--issue-number",
                "40",
                "--target-version",
                "0.0.0",
                "--required-final-stage",
                "UT",
                "--pr-number",
                "41",
                "--pr-head-sha",
                "abc123",
            ]
        )
    finally:
        static_analysis.repo_root = original_repo_root

    assert rc == 0
    payload = json.loads(
        (output_dir / "static-analysis-result.json").read_text(encoding="utf-8")
    )
    assert payload["checks"]["gofmt"]["diff_generated"] is False
    assert "$ gofmt -d ." not in (
        output_dir / "logs" / "gofmt.log"
    ).read_text(encoding="utf-8")
