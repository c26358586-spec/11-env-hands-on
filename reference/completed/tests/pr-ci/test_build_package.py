# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

import importlib.util
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "pr-ci"
sys.path.insert(0, str(SCRIPT_DIR))
MODULE_PATH = SCRIPT_DIR / "build_package.py"
SPEC = importlib.util.spec_from_file_location("build_package", MODULE_PATH)
build_package = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_package)


def test_normalize_target_version_removes_leading_v():
    assert build_package.normalize_target_version("v0.1.0") == "0.1.0"
    assert build_package.normalize_target_version("0.1.0") == "0.1.0"


def test_build_artifact_version_uses_run_number_and_attempt():
    assert (
        build_package.build_artifact_version("v0.1.0", "12", "2")
        == "v0.1.0+b.12.a.2"
    )


def test_semver_pattern_accepts_x_y_z_only():
    assert build_package.SEMVER_PATTERN.match("0.1.0")
    assert not build_package.SEMVER_PATTERN.match("v0.1.0")
