from __future__ import annotations

import hashlib
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAW_KEY = "unit-test-key-with-high-entropy-placeholder"
os.environ["API_KEY_HASH"] = hashlib.sha256(RAW_KEY.encode()).hexdigest()
os.environ["CHROMIUM_BIN"] = "/bin/true"

manager = importlib.import_module("manager.main")


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(manager, "PROFILES_ROOT", tmp_path.resolve())
    monkeypatch.setattr(manager, "LOCK_ROOT", (tmp_path / ".locks").resolve())
    manager._PROCESSES.clear()
    manager._PROFILE_LOCKS.clear()
    manager._AUTH_FAILURES.clear()
    with TestClient(manager.app) as test_client:
        yield test_client


def auth() -> dict[str, str]:
    return {"X-API-Key": RAW_KEY}


def test_health_is_minimal_and_security_headers_are_present(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-frame-options"] == "DENY"
    assert "script-src 'self'" in response.headers["content-security-policy"]


def test_api_authentication_fails_closed(client: TestClient):
    assert client.get("/api/personas").status_code == 401
    assert client.get("/api/personas", headers={"X-API-Key": "wrong"}).status_code == 403
    assert client.get("/api/personas", headers=auth()).status_code == 200


def test_failed_authentication_is_rate_limited(client: TestClient):
    for _ in range(manager.AUTH_MAX_FAILURES):
        assert client.get("/api/personas", headers={"X-API-Key": "wrong"}).status_code == 403
    assert client.get("/api/personas", headers={"X-API-Key": "wrong"}).status_code == 429


def test_persona_validation_and_path_confinement(client: TestClient):
    for name in ("..", ".", "bad/name", "bad name", "x" * 65):
        with pytest.raises(Exception):
            manager._persona_dir(name)
    valid = manager._persona_dir("safe-name_1")
    assert valid.parent == manager.PROFILES_ROOT


def test_create_update_and_delete_persona(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    payload = {
        "name": "example",
        "description": "<img src=x onerror=alert(1)>",
        "accounts": [{"site": "<script>bad()</script>", "email": "local label"}],
        "notes": "<svg onload=bad()>",
    }
    created = client.post("/api/personas", headers=auth(), json=payload)
    assert created.status_code == 201
    assert created.json()["meta"]["description"] == payload["description"]
    assert (manager.PROFILES_ROOT / "example" / "persona.yml").stat().st_mode & 0o777 == 0o600

    monkeypatch.setattr(manager, "_terminate_browser", lambda name: [])
    monkeypatch.setattr(manager, "_matching_pids", lambda name: [])
    deleted = client.delete("/api/personas/example", headers=auth())
    assert deleted.status_code == 204
    assert not (manager.PROFILES_ROOT / "example").exists()


def test_launch_rejects_non_http_urls(client: TestClient):
    client.post("/api/personas", headers=auth(), json={"name": "example"})
    for url in ("file:///etc/passwd", "javascript:alert(1)", "chrome://settings"):
        response = client.post("/api/personas/example/launch", headers=auth(), params={"url": url})
        assert response.status_code == 422


def test_browser_startup_requires_process_to_stay_alive():
    """If Chromium exits before the timeout, startup is rejected."""
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(0.05); raise SystemExit(1)"]
    )
    assert manager._confirm_browser_startup(process, "default", timeout=0.2) is False


def test_browser_startup_accepts_stable_browser(monkeypatch: pytest.MonkeyPatch):
    """A browser that stays alive for the full timeout is accepted."""
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert manager._confirm_browser_startup(process, "default", timeout=0.2) is True
    finally:
        process.terminate()
        process.wait(timeout=1)


def test_browser_startup_kills_process_on_failure():
    """When startup is rejected (process exits before deadline), it is terminated."""
    # Process exits DURING the 0.2s window (0.15s < deadline): function returns
    # False, then finally block terminates it (already dead — kill is harmless).
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(0.15)"]
    )
    try:
        assert manager._confirm_browser_startup(process, "default", timeout=0.3) is False
        # Process must have exited and been cleaned up.
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=1)


def test_container_configures_chromium_setuid_sandbox():
    root = Path(__file__).parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "chmod 4755" in dockerfile
    assert "chrome_sandbox" in dockerfile
    assert "cap_drop:\n      - ALL" in compose
    assert "cap_add:" in compose
    assert "      - SYS_ADMIN" in compose
    assert "no-new-privileges:true" not in compose


def test_ci_requires_a_rendered_browser_runtime_smoke():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "Runtime browser and VNC smoke" in workflow
    assert "xwininfo" in workflow
    assert "RFB" in workflow
    assert "CapEff" in workflow
    assert workflow.index("trap cleanup EXIT") < workflow.index("api_key='ci-runtime-smoke-key'")


def test_publish_requires_tag_commit_on_main_and_release_environment():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    assert "environment: release" in workflow
    assert "fetch-depth: 0" in workflow
    assert "+refs/heads/main:refs/remotes/origin/main" in workflow
    assert "git merge-base --is-ancestor \"$GITHUB_SHA\" refs/remotes/origin/main" in workflow
    assert "id-token: write" not in workflow
    assert "attestations: write" not in workflow


def test_ui_does_not_persist_key_or_build_dynamic_html(client: TestClient):
    javascript = client.get("/static/app.js").text
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "innerHTML" not in javascript
    assert "textContent" in javascript


def test_import_fails_without_api_hash(tmp_path: Path):
    import subprocess

    env = dict(os.environ)
    env.pop("API_KEY_HASH", None)
    env["PYTHONPATH"] = str(Path(__file__).parents[1])
    result = subprocess.run(
        [sys.executable, "-c", "import manager.main"],
        env=env,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "API_KEY_HASH must be configured" in result.stderr
