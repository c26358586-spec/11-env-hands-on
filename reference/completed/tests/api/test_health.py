# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

import json
import os
import subprocess

import pytest
import requests


REQUIRED_ENV = (
    "API_BASE_URL",
)


def expected_app_version():
    return os.environ.get("EXPECTED_APP_VERSION") or os.environ.get("APP_VERSION", "")


@pytest.fixture(autouse=True)
def require_api_inputs():
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if not expected_app_version():
        missing.append("EXPECTED_APP_VERSION or APP_VERSION")
    if missing:
        pytest.skip("Lesson 5.5 API tests require environment inputs: " + ", ".join(missing))


@pytest.fixture
def base_url():
    return os.environ["API_BASE_URL"].rstrip("/")


def test_health_endpoint_via_nginx(base_url, record_property):
    record_property("test_case_id", "API-001")
    expected_version = expected_app_version()
    response = requests.get(f"{base_url}/health", timeout=5)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "ms1-go-api"
    assert payload["version"] == expected_version


def test_health_endpoint_rejects_unsupported_method(base_url, record_property):
    record_property("test_case_id", "API-002")
    response = requests.post(f"{base_url}/health", timeout=5)

    assert response.status_code == 405


def test_unknown_path_returns_not_found(base_url, record_property):
    record_property("test_case_id", "API-003")
    response = requests.get(f"{base_url}/not-found", timeout=5)

    assert response.status_code == 404


def test_direct_container_health_matches_nginx_when_container_is_available(record_property):
    record_property("test_case_id", "API-004")
    container_name = os.environ.get("TARGET_CONTAINER_NAME")
    if not container_name:
        pytest.skip("TARGET_CONTAINER_NAME is not available for direct container check.")

    completed = subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "python3",
            "-c",
            (
                "import json, urllib.request; "
                "print(json.dumps(json.load("
                "urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)), sort_keys=True))"
            ),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = completed.stdout.strip()

    proxied = requests.get(f"{os.environ['API_BASE_URL'].rstrip('/')}/health", timeout=5).json()
    assert payload
    assert payload == json.dumps(proxied, sort_keys=True)
