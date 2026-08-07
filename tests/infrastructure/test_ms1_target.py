# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def env_or_file(name, relative_path):
    value = os.environ.get(name)
    if value:
        return value
    path = REPO_ROOT / relative_path
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def expected_app_version():
    return os.environ.get("EXPECTED_APP_VERSION") or os.environ.get("APP_VERSION", "")


@pytest.fixture(autouse=True)
def require_environment_inputs():
    missing = []
    if not env_or_file("TARGET_CONTAINER_NAME", "dist/ms1/container_name.txt"):
        missing.append("TARGET_CONTAINER_NAME or dist/ms1/container_name.txt")
    if not env_or_file("TARGET_NETWORK_NAME", "dist/ms1/network_name.txt"):
        missing.append("TARGET_NETWORK_NAME or dist/ms1/network_name.txt")
    if not (os.environ.get("EXPECTED_ENVIRONMENT_FACE_ID") or os.environ.get("ENVIRONMENT_FACE_ID")):
        missing.append("EXPECTED_ENVIRONMENT_FACE_ID or ENVIRONMENT_FACE_ID")
    if not expected_app_version():
        missing.append("EXPECTED_APP_VERSION or APP_VERSION")
    if missing:
        pytest.skip(
            "Lesson 5.5 infrastructure tests require environment inputs: " + ", ".join(missing)
        )


def docker_inspect(resource_type, name):
    completed = subprocess.run(
        ["docker", "inspect", "--type", resource_type, name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert len(payload) == 1
    return payload[0]


def assert_expected_labels(labels):
    expected_pairs = []
    environment_face_id = os.environ.get("EXPECTED_ENVIRONMENT_FACE_ID") or os.environ.get(
        "ENVIRONMENT_FACE_ID"
    )
    if environment_face_id:
        label_key = "environment_face_id" if "environment_face_id" in labels else "ranamicus.environment_face_id"
        expected_pairs.append((label_key, environment_face_id))

    if os.environ.get("EXPECTED_TEST_RUN_ID"):
        expected_pairs.append(("test_run_id", os.environ["EXPECTED_TEST_RUN_ID"]))
    if os.environ.get("EXPECTED_ISSUE_NUMBER"):
        expected_pairs.append(("issue_number", os.environ["EXPECTED_ISSUE_NUMBER"]))
    if os.environ.get("EXPECTED_MANAGED_BY"):
        expected_pairs.append(("managed_by", os.environ["EXPECTED_MANAGED_BY"]))
    managed_label_key = os.environ.get("EXPECTED_MANAGED_LABEL_KEY") or os.environ.get("MANAGED_LABEL_KEY")
    managed_label_value = os.environ.get("EXPECTED_MANAGED_LABEL_VALUE") or os.environ.get(
        "MANAGED_LABEL_VALUE",
        "",
    )
    if managed_label_key:
        expected_pairs.append(
            (
                managed_label_key,
                managed_label_value,
            )
        )
    if os.environ.get("EXPECTED_ENVIRONMENT_PATTERN_ID"):
        expected_pairs.append(("environment_pattern_id", os.environ["EXPECTED_ENVIRONMENT_PATTERN_ID"]))
    elif os.environ.get("EXPECTED_TEST_RUN_ID"):
        expected_pairs.append(("environment_pattern_id", "UT"))

    for key, value in expected_pairs:
        assert labels.get(key) == value


def test_nginx_is_installed(host, record_property):
    record_property("test_case_id", "INF-001")
    assert host.package("nginx").is_installed


def test_target_container_exists_and_has_expected_labels(record_property):
    record_property("test_case_id", "INF-002")
    container = docker_inspect("container", env_or_file("TARGET_CONTAINER_NAME", "dist/ms1/container_name.txt"))
    assert container["State"]["Running"] is True
    assert_expected_labels(container["Config"]["Labels"])


def test_target_network_exists_and_has_expected_labels(record_property):
    record_property("test_case_id", "INF-003")
    network = docker_inspect("network", env_or_file("TARGET_NETWORK_NAME", "dist/ms1/network_name.txt"))
    assert_expected_labels(network["Labels"])


def test_nginx_configuration_file_exists(host, record_property):
    record_property("test_case_id", "INF-004")
    config = host.file("/etc/nginx/sites-enabled/ms1-app.conf")
    assert config.exists
    assert config.is_symlink


def test_nginx_configuration_is_valid(host, record_property):
    record_property("test_case_id", "INF-005")
    result = host.run("nginx -t")
    assert result.rc == 0, result.stderr


def test_required_ports_are_listening(host, record_property):
    record_property("test_case_id", "INF-006")
    result = host.run("ss -ltn")
    assert result.rc == 0, result.stderr
    assert ":80 " in result.stdout
    assert ":8080 " in result.stdout


def test_go_application_binary_exists(host, record_property):
    record_property("test_case_id", "INF-007")
    app = host.file("/opt/ms1-app/bin/ms1-app")
    assert app.exists
    assert app.is_file
    assert app.mode & 0o111


def test_go_application_process_is_running(host, record_property):
    record_property("test_case_id", "INF-008")
    result = host.run("pgrep -af '/opt/ms1-app/bin/ms1-app'")
    assert result.rc == 0, result.stderr


def test_nginx_proxies_to_go_application(host, record_property):
    record_property("test_case_id", "INF-009")
    expected_version = expected_app_version()
    result = host.run("python3 -c 'import json, urllib.request; print(json.dumps(json.load(urllib.request.urlopen(\"http://127.0.0.1/health\", timeout=5)), sort_keys=True))'")
    assert result.rc == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["service"] == "ms1-go-api"
    assert payload["version"] == expected_version
