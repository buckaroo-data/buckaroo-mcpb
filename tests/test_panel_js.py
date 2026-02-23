"""Layer 2: Playwright tests — verify panel HTML JavaScript logic in headless Chromium."""

import http.server
import json
import os
import threading
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_PANEL_HTML = (_REPO_ROOT / "src" / "panel.html").read_text()

# Fake tool result texts with a session URL embedded
_FAKE_URL = "http://localhost:8700/s/abc123def456"
_FAKE_RESULT_TEXT = (
    f"Loaded test.csv — 2 rows, 2 columns\n\n"
    f"Interactive view: {_FAKE_URL}\n"
    f"Server: pid=1234 (started)"
)


@pytest.fixture(scope="module")
def panel_server():
    """Serve panel.html on a random local port."""
    import tempfile

    tmpdir = tempfile.mkdtemp()
    html_path = os.path.join(tmpdir, "panel.html")
    Path(html_path).write_text(_PANEL_HTML)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=tmpdir, **kwargs)

        def log_message(self, *args):
            pass  # suppress request logs

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    yield f"http://127.0.0.1:{port}/panel.html"
    httpd.shutdown()


def _send_tool_result(page, text, method="ui/notifications/tool-result"):
    """Fire a postMessage simulating Claude Desktop's tool result notification."""
    page.evaluate(
        """([method, text]) => {
            window.postMessage({
                method: method,
                params: {
                    content: [{ type: 'text', text: text }]
                }
            }, '*');
        }""",
        [method, text],
    )


def test_panel_shows_loading_state_on_load(panel_server):
    """On initial load, loading div is visible and iframe is hidden."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(panel_server)
        assert page.locator("#loading").is_visible()
        assert page.locator("#frame").is_hidden()
        browser.close()


def test_panel_iframes_tornado_url_on_tool_result(panel_server):
    """On ui/notifications/tool-result, iframe src is set and loading hides."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(panel_server)

        _send_tool_result(page, _FAKE_RESULT_TEXT)

        page.wait_for_function(
            "document.getElementById('frame').style.display !== 'none'",
            timeout=3000,
        )
        frame_src = page.evaluate("document.getElementById('frame').src")
        assert "localhost:8700/s/abc123def456" in frame_src
        assert page.locator("#loading").is_hidden()
        browser.close()


def test_panel_also_handles_ui_tool_result_method(panel_server):
    """Alternate message method 'ui/toolResult' is also handled."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(panel_server)

        _send_tool_result(page, _FAKE_RESULT_TEXT, method="ui/toolResult")

        page.wait_for_function(
            "document.getElementById('frame').style.display !== 'none'",
            timeout=3000,
        )
        frame_src = page.evaluate("document.getElementById('frame').src")
        assert "localhost:8700/s/abc123def456" in frame_src
        browser.close()


def test_panel_ignores_unrelated_messages(panel_server):
    """Messages with unrecognised methods don't change panel state."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(panel_server)

        page.evaluate(
            "window.postMessage({method: 'something/else', params: {}}, '*')"
        )
        time.sleep(0.3)
        assert page.locator("#loading").is_visible()
        assert page.locator("#frame").is_hidden()
        browser.close()
