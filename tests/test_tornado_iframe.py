"""Layer 3: Tornado server tests — verify the session URL Claude Desktop would iframe."""

import json
import os
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest

_PYTHON = sys.executable
_SERVER_PORT = 8701  # use a different port to avoid clashing with any running server
_SERVER_URL = f"http://localhost:{_SERVER_PORT}"


def _health():
    try:
        resp = urlopen(f"{_SERVER_URL}/health", timeout=1)
        if resp.status == 200:
            return json.loads(resp.read())
    except (URLError, OSError):
        pass
    return None


@pytest.fixture(scope="module")
def tornado_server():
    """Start buckaroo.server on port 8701 for the duration of the module."""
    proc = subprocess.Popen(
        [_PYTHON, "-m", "buckaroo.server", "--port", str(_SERVER_PORT), "--no-browser"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait up to 10s for the server to be ready
    for _ in range(40):
        time.sleep(0.25)
        if _health():
            break
    else:
        proc.terminate()
        pytest.fail("Tornado server did not start within 10s")

    yield

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_health_endpoint(tornado_server):
    """Server /health responds with status ok and buckaroo version."""
    data = _health()
    assert data is not None
    assert data.get("status") == "ok"
    assert "version" in data


def test_load_csv_and_session_url_returns_html(tornado_server, tmp_path):
    """POST /load → GET /s/{session} must return 200 text/html."""
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("city,pop\nNYC,8000000\nLA,4000000\n")

    session_id = "testpanel000aaa"
    payload = json.dumps({
        "session": session_id,
        "path": str(csv_file),
        "mode": "buckaroo",
    }).encode()
    req = Request(
        f"{_SERVER_URL}/load",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urlopen(req, timeout=15)
    assert resp.status == 200
    body = json.loads(resp.read())
    assert body["rows"] == 2
    assert body["session"] == session_id

    # The session URL is what the panel iframe would load
    page_resp = urlopen(f"{_SERVER_URL}/s/{session_id}", timeout=5)
    assert page_resp.status == 200
    content_type = page_resp.headers.get("Content-Type", "")
    assert "text/html" in content_type


def test_session_url_contains_buckaroo_assets(tornado_server, tmp_path):
    """The session page references standalone.js (confirms full app is served)."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("x,y\n1,2\n3,4\n")

    session_id = "testpanel111bbb"
    payload = json.dumps({
        "session": session_id,
        "path": str(csv_file),
        "mode": "buckaroo",
    }).encode()
    req = Request(
        f"{_SERVER_URL}/load",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    urlopen(req, timeout=15)

    page_resp = urlopen(f"{_SERVER_URL}/s/{session_id}", timeout=5)
    html = page_resp.read().decode()
    assert "standalone" in html or "buckaroo" in html.lower()
