# Buckaroo MCPB Distribution Plan

## Goal

Users double-click a `.mcpb` file (or find Buckaroo in Claude Desktop's Connectors Directory) and it just works — no Python, no `uvx`, no terminal.

## Current State

```
Claude Desktop/Code
    │ stdio (JSON-RPC 2.0)
    ▼
uvx --from "buckaroo[mcp]" buckaroo-table
    │  (buckaroo_mcp_tool.py — FastMCP server)
    │  spawns subprocess
    ▼
python -m buckaroo.server  (Tornado on port 8700)
    │  serves static JS/CSS, WebSocket data streaming
    ▼
Browser tab (interactive table viewer)
```

Users must have `uv`/`uvx` installed, a working Python 3.11+, and command-line comfort.

## Decision: `"type": "uv"` is the path

MCPB supports four server types. After research, only one is viable for Buckaroo:

| Type | Verdict | Why |
|------|---------|-----|
| `node` | Not viable | Would require rewriting the server in JS/TS. Loses pandas/polars/pyarrow. |
| `python` | Broken | Cannot portably bundle compiled extensions (.so/.pyd). Anthropic's own `file-manager-python` example fails ([issue #47](https://github.com/anthropics/dxt/issues/47)). An Anthropic engineer confirmed: *"There's essentially no good path for fully self-contained python MCPBs"* with compiled deps ([issue #158](https://github.com/anthropics/dxt/issues/158)). `mcpb pack` also strips venv directories ([issue #29](https://github.com/anthropics/dxt/issues/29)). |
| `binary` | Fragile | PyInstaller output works in theory, but `mcpb pack` strips executable permissions ([issues #12](https://github.com/anthropics/dxt/issues/12), [#13](https://github.com/anthropics/dxt/issues/13)). Nobody has shipped a PyInstaller-based MCPB. Also requires per-platform builds (~100MB each), `sys.executable` doesn't work in frozen binaries (would need in-process server rewrite), and hitting the 100MB directory submission limit is tight. |
| **`uv`** | **The answer** | Bundle is just `manifest.json` + `pyproject.toml` (~5KB). Claude Desktop manages Python + deps via `uv` at runtime — installs correct platform-specific wheels on the user's machine. Cross-platform from a single bundle. This is what Anthropic is actively pushing as the solution. **Status: experimental (manifest v0.4+).** |

### Why not Pyodide?

Researched running Python-in-WASM inside Node.js. Three dealbreakers: no polars in Pyodide 0.29, no sockets (tornado can't run in WASM), no subprocess. Pydantic tried this with [mcp-run-python](https://github.com/pydantic/mcp-run-python) and abandoned it.

### Why not Electron/Tauri?

MCPB eliminates the need. Claude Desktop is the host app. No custom UI, installer, or update mechanism needed.

---

## Architecture

```
buckaroo-table.mcpb  (ZIP archive, ~5KB)
├── manifest.json
├── icon.png
└── server/
    ├── pyproject.toml         (declares buckaroo[mcp] as dep)
    └── buckaroo_mcp_tool.py   (entry point, same as today)
```

At install time, Claude Desktop:
1. Extracts the `.mcpb`
2. Shows config UI (port selection)
3. On first run: `uv` installs Python + `buckaroo[mcp]` from PyPI into an isolated venv
4. Runs `buckaroo-table` entry point via stdio
5. Subsequent runs use cached venv (fast startup)

Upgrading Buckaroo = publishing to PyPI. `uv sync` pulls the latest version automatically.

---

## Repo Structure

New repo: **`paddymul/buckaroo-desktop`**

```
buckaroo-desktop/
├── manifest.json
├── icon.png
├── server/
│   ├── pyproject.toml
│   └── buckaroo_mcp_tool.py
├── tests/
│   └── test_mcp_smoke.py
├── .github/
│   └── workflows/
│       ├── build-mcpb.yml     (pack + test)
│       └── release.yml        (attach to GitHub Release)
├── .mcpbignore
└── README.md
```

### `manifest.json`

```json
{
  "manifest_version": "0.4",
  "name": "buckaroo-table",
  "display_name": "Buckaroo Table Viewer",
  "version": "0.12.8",
  "description": "Interactive table viewer for CSV, TSV, Parquet, and JSON files",
  "long_description": "Buckaroo lets you view and explore tabular data files interactively. When you mention a data file, Claude opens it in a rich table UI in your browser with sorting, filtering, summary statistics, and data transformations.",
  "author": {
    "name": "Paddy Mullen",
    "url": "https://github.com/paddymul/buckaroo"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/paddymul/buckaroo"
  },
  "homepage": "https://github.com/paddymul/buckaroo",
  "support": "https://github.com/paddymul/buckaroo/issues",
  "icon": "icon.png",
  "server": {
    "type": "uv",
    "entry_point": "server/buckaroo_mcp_tool.py"
  },
  "tools": [
    {
      "name": "view_data",
      "description": "Load a tabular data file (CSV, TSV, Parquet, JSON) in Buckaroo for interactive viewing",
      "annotations": {
        "readOnlyHint": true,
        "openWorldHint": false
      }
    },
    {
      "name": "buckaroo_table",
      "description": "Load a tabular data file in Buckaroo (alias for view_data)",
      "annotations": {
        "readOnlyHint": true,
        "openWorldHint": false
      }
    },
    {
      "name": "buckaroo_diagnostics",
      "description": "Run diagnostics on the Buckaroo data server",
      "annotations": {
        "readOnlyHint": true,
        "openWorldHint": false
      }
    }
  ],
  "user_config": {
    "port": {
      "type": "number",
      "title": "Server Port",
      "description": "Port for the Buckaroo data server (change if 8700 conflicts)",
      "default": 8700,
      "min": 1024,
      "max": 65535
    }
  },
  "compatibility": {
    "platforms": ["darwin", "win32", "linux"],
    "runtimes": {
      "python": ">=3.11"
    }
  },
  "keywords": ["data", "table", "csv", "parquet", "viewer", "pandas", "polars"],
  "license": "BSD-3-Clause"
}
```

### `server/pyproject.toml`

```toml
[project]
name = "buckaroo-mcp"
version = "0.12.8"
requires-python = ">=3.11"
dependencies = ["buckaroo[mcp]>=0.12.8"]

[project.scripts]
buckaroo-table = "buckaroo_mcp_tool:main"
```

### `.mcpbignore`

```
.github/
tests/
*.md
.git/
.venv/
__pycache__/
```

---

## Release Pipeline

```
paddymul/buckaroo (bug fix / feature)
    │
    ├─ 1. Merge to main
    ├─ 2. Bump version, tag, push
    └─ 3. CI publishes wheel to PyPI (buckaroo 0.12.9)
           │
           │  repository_dispatch event
           ▼
paddymul/buckaroo-desktop
    │
    ├─ 4. CI bumps version in manifest.json + pyproject.toml
    ├─ 5. mcpb validate → mcpb pack → smoke test
    ├─ 6. Attach .mcpb to GitHub Release
    └─ 7. (If in Anthropic directory) auto-update pushed to users
```

### Cross-repo trigger

In `paddymul/buckaroo`'s release workflow:
```yaml
- name: Trigger desktop build
  uses: peter-evans/repository-dispatch@v3
  with:
    repository: paddymul/buckaroo-desktop
    event-type: new-buckaroo-release
    client-payload: '{"version": "${{ github.ref_name }}"}'
```

### Version strategy

Use `>=0.12.8` (not `==0.12.9`) in `server/pyproject.toml`. This way `uv` auto-resolves to the latest compatible PyPI release without needing a new `.mcpb` for every Buckaroo patch.

The `.mcpb` version only needs to bump when:
- The manifest itself changes (new tool, config option, etc.)
- The minimum Buckaroo version changes (breaking change)
- The entry point script (`buckaroo_mcp_tool.py`) changes

---

## Testing Strategy

### No `mcpb test` command exists. Testing is layered:

#### Layer 1: Manifest validation
```bash
npm install -g @anthropic-ai/mcpb
mcpb validate manifest.json
mcpb pack . --output buckaroo-table.mcpb
mcpb info buckaroo-table.mcpb
```

#### Layer 2: MCP smoke test (Python SDK as client)

```python
# tests/test_mcp_smoke.py
import asyncio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@pytest.mark.asyncio
async def test_initialize_and_list_tools():
    """Verify the MCP server starts and exposes expected tools."""
    params = StdioServerParameters(
        command="buckaroo-table",
        args=[],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            assert "view_data" in tool_names
            assert "buckaroo_diagnostics" in tool_names

@pytest.mark.asyncio
async def test_view_data_with_csv(tmp_path):
    """Verify view_data loads a CSV and returns a summary."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,age\nAlice,30\nBob,25\n")

    params = StdioServerParameters(command="buckaroo-table", args=[])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "view_data",
                arguments={"path": str(csv_file)},
            )
            text = str(result.content)
            assert "2" in text  # 2 rows
            assert "name" in text
```

#### Layer 3: Interactive testing with MCP Inspector
```bash
npx @modelcontextprotocol/inspector buckaroo-table
```
Opens a browser UI where you can call tools interactively.

#### Layer 4: Install in Claude Desktop
```bash
mcpb pack . --output buckaroo-table.mcpb
open buckaroo-table.mcpb  # double-click to install
```
Then ask Claude: *"Use buckaroo to view this CSV: /path/to/data.csv"*

### CI Workflow

```yaml
# .github/workflows/build-mcpb.yml
name: Build and Test MCPB

on:
  push:
    branches: [main]
  pull_request:
  repository_dispatch:
    types: [new-buckaroo-release]
  workflow_dispatch:

jobs:
  validate-and-pack:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install tools
        run: |
          npm install -g @anthropic-ai/mcpb
          pip install "buckaroo[mcp]" mcp pytest pytest-asyncio

      - name: Validate manifest
        run: mcpb validate manifest.json

      - name: Pack bundle
        run: mcpb pack . --output buckaroo-table.mcpb

      - name: Inspect bundle
        run: mcpb info buckaroo-table.mcpb

      - name: MCP smoke test
        run: pytest tests/test_mcp_smoke.py -v

      - name: Upload bundle
        uses: actions/upload-artifact@v4
        with:
          name: buckaroo-table-mcpb
          path: buckaroo-table.mcpb

  # Test on multiple platforms to verify uv resolves deps correctly
  cross-platform-smoke:
    strategy:
      fail-fast: false
      matrix:
        os: [macos-14, macos-15-intel, windows-latest, ubuntu-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install and test
        run: |
          pip install "buckaroo[mcp]" mcp pytest pytest-asyncio
          pytest tests/test_mcp_smoke.py -v

  release:
    needs: [validate-and-pack, cross-platform-smoke]
    if: github.event_name == 'repository_dispatch' || startsWith(github.ref, 'refs/tags/')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: buckaroo-table-mcpb

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: buckaroo-table.mcpb
          tag_name: v${{ github.event.client_payload.version || github.ref_name }}
```

---

## Milestones

### M1: Validate the `uv` type works (1 day)

Before building anything, prove the `uv` type actually works in Claude Desktop today.

- [x] Install `@anthropic-ai/mcpb` CLI — v2.1.2 installed
- [x] Study the [`hello-world-uv` example](https://github.com/modelcontextprotocol/mcpb/tree/main/examples/hello-world-uv) — confirmed field names (snake_case), pyproject.toml at root, `mcp_config` required by v2.1.2 validator
- [x] `mcpb validate` passes on Buckaroo manifest
- [x] `mcpb pack` produces 6.2KB `buckaroo-table.mcpb`
- [ ] Double-click `.mcpb` to install in Claude Desktop and verify `uv` installs deps and starts server
- [ ] **Decision gate**: If `uv` type works → M2 complete. If not → fall back to `binary`.

> **Key schema finding**: `server.mcp_config` is required by the v2.1.2 validator even for `uv` type (contradicts spec). Using `uv run ${__dirname}/src/buckaroo_mcp_tool.py`. Tool `annotations` go in the MCP server, not the manifest.

### M2: Build the Buckaroo MCPB (1-2 days)

- [x] Created `buckaroo-mcpb` repo (this repo)
- [x] Written `manifest.json` (uv type, mcp_config, user_config for port, tools list)
- [x] Written `pyproject.toml` at repo root (declares `buckaroo[mcp]>=0.12.8`)
- [x] Copied `buckaroo_mcp_tool.py` into `src/` — entry_point is `src/buckaroo_mcp_tool.py`
- [x] Written `.mcpbignore` (excludes .github/, tests/, *.md, .git/, .venv/, __pycache__)
- [x] Created placeholder `icon.png` (512×512 blue — replace with real Buckaroo logo)
- [x] `mcpb pack` → 6.2KB bundle, 4 files (manifest, icon, pyproject.toml, src/tool)
- [ ] Double-click install in Claude Desktop, test end-to-end with a CSV file
- [ ] Write MCP smoke tests (M2b below)

### M2b: Write MCP smoke tests

- [x] Written `tests/test_mcp_smoke.py` — initialize + list tools, view_data with CSV
- [x] Tests pass locally: 2 passed (tool listing: 0.44s, view_data with CSV: 17s including server start)

### M3: CI + Releases (1 day)

- [x] Written `.github/workflows/build-mcpb.yml` — validate, pack, smoke test, cross-platform matrix, release job
- [x] Fixed `mcpb pack` invocation (positional arg, not `--output` flag — v2.1.2 syntax)
- [ ] Push to GitHub and verify CI passes
- [ ] Wire up `repository_dispatch` from `buckaroo` release workflow
- [ ] Create first GitHub Release with `.mcpb` artifact
- [ ] Update `buckaroo` README with download link and install instructions

### M4: Anthropic Directory Submission

- [ ] Add tool annotations to `buckaroo_mcp_tool.py` (`readOnlyHint`, etc.) — do this in the main `buckaroo` repo, publish to PyPI
- [ ] Write privacy policy
- [ ] Create 3+ example prompts for the submission form
- [ ] Test on clean macOS and Windows (borrow a machine or use CI)
- [ ] Submit via https://forms.gle/tyiAZvch1kDADKoP9

### M5: Ongoing

- [ ] Monitor `uv` type stabilization (currently experimental v0.4+)
- [ ] If/when Anthropic directory lists Buckaroo: users get auto-updates, no more manual `.mcpb` downloads

---

## Upgrade Story

| Distribution channel | How users get updates |
|----------------------|-----------------------|
| **Anthropic Directory** | Automatic. Claude Desktop checks for new versions. |
| **GitHub Releases** | Manual. User downloads new `.mcpb`, double-clicks. Old version is replaced. Pain point: re-install erases `user_config` ([issue #77](https://github.com/anthropics/dxt/issues/77)). |
| **`uv` type specifically** | The `.mcpb` itself rarely changes. Buckaroo updates come from PyPI — `uv sync` pulls the latest version that satisfies the `>=0.12.8` constraint. For most Buckaroo patches, **no new `.mcpb` is needed at all.** |

---

## Known Risks and Open Issues

### 1. Is `"type": "uv"` actually stable enough?
It's tagged experimental (manifest v0.4+). Claude Desktop may not support it yet, or may have bugs. **M1 validates this before we invest further.**

### 2. Claude Desktop may refuse install if no system Python is found
[Issue #96](https://github.com/anthropics/dxt/issues/96) reports this even when `uv` can manage Python itself. If this blocks us, workaround is to document that users need Python 3.11+ installed (still better than needing `uvx`).

### 3. First-run latency
`uv sync` on first install downloads Python + all deps. For `buckaroo[mcp]` (polars, pandas, pyarrow, tornado, mcp), this could take 30-60 seconds on a typical connection. Subsequent starts are fast (cached venv). May need to surface a "first-time setup" message.

### 4. `mcpb pack` permission stripping
[Issues #12, #13](https://github.com/anthropics/dxt/issues/12) — affects `binary` type primarily, but worth verifying doesn't affect `uv` type entry points.

### 5. Entry point resolution with `uv` type
Need to verify: does `"entry_point": "server/buckaroo_mcp_tool.py"` work, or does the `uv` runtime expect a `[project.scripts]` entry point from `pyproject.toml`? The `hello-world-uv` example uses `"entry_point": "src/server.py"` (direct file reference), so direct file should work.

---

## Appendix: Fallback — `"type": "binary"` (PyInstaller)

If `"type": "uv"` doesn't work in practice, fall back to PyInstaller bundles:

- Separate `.mcpb` per platform (macOS ARM, macOS Intel, Windows)
- ~100MB each (Python runtime + pandas + polars + pyarrow + numpy + tornado)
- Must fix `sys.executable` in `buckaroo_mcp_tool.py` — PyInstaller frozen binaries can't use `sys.executable` to spawn Python subprocesses. Solution: run `buckaroo.server` in-process on a thread instead of as a subprocess.
- CI builds on `macos-14` (ARM), `macos-15-intel`, `windows-latest`
- Bundle size target: < 100MB (may need to drop pandas, use polars-only for MCP path)
- Must work around `mcpb pack` stripping executable permissions

This is significantly more work. The `uv` type avoids all of it.

---

## References

- [MCPB repo (spec + CLI + examples)](https://github.com/modelcontextprotocol/mcpb)
- [Manifest spec (MANIFEST.md)](https://github.com/modelcontextprotocol/mcpb/blob/main/MANIFEST.md)
- [CLI docs (CLI.md)](https://github.com/modelcontextprotocol/mcpb/blob/main/CLI.md)
- [Anthropic blog: One-click MCP server installation](https://www.anthropic.com/engineering/desktop-extensions)
- [Claude Help: Building Desktop Extensions](https://support.claude.com/en/articles/12922929-building-desktop-extensions-with-mcpb)
- [Claude Help: Directory Submission Guide](https://support.claude.com/en/articles/12922832-local-mcp-server-submission-guide)
- [Issue #47: file-manager-python broken](https://github.com/anthropics/dxt/issues/47)
- [Issue #158: UV runtime support](https://github.com/anthropics/dxt/issues/158)
- [Issue #96: Claude Desktop + uv install problem](https://github.com/anthropics/dxt/issues/96)
- [Issue #65: Update mechanism](https://github.com/anthropics/dxt/issues/65)
- [Issue #77: Re-install erases config](https://github.com/anthropics/dxt/issues/77)
- [Issue #68: Post-install hooks proposal](https://github.com/anthropics/dxt/issues/68)
- [Microsoft: MCPB on Windows](https://learn.microsoft.com/en-us/windows/ai/mcp/servers/mcp-mcpb)
- [`hello-world-uv` example](https://github.com/modelcontextprotocol/mcpb/tree/main/examples/hello-world-uv)
