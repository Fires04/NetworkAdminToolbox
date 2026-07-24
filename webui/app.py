#!/usr/bin/env python3
"""
webui/app.py - generic web front-end for the clidescribe-based tool
collection living in the parent folder.

It scans SCRIPTS_DIR for *.py files, asks each one `--describe`, and for any
script that answers with a valid clidescribe JSON schema, auto-generates a
form and a runner page for it. No script-specific web code is needed: add a
new tool that speaks the clidescribe convention and it shows up here
automatically.

Run:
    python3 webui/app.py

Then open http://127.0.0.1:5000/ -- deliberately localhost-only; this is a
personal toolbox, not something to expose on a network.
"""
import html
import json
import subprocess
import sys
from pathlib import Path

from flask import Flask, redirect, request, url_for

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
EXCLUDE_FILES = {"clidescribe.py"}
DESCRIBE_TIMEOUT = 5
RUN_TIMEOUT = 60

sys.path.insert(0, str(SCRIPTS_DIR))
import clidescribe  # noqa: E402  (needs SCRIPTS_DIR on sys.path first)

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------

def discover_tools():
    """Return {tool_name: {"path": Path, "schema": dict}} for every *.py file
    in SCRIPTS_DIR that answers `--describe` with valid clidescribe JSON."""
    tools = {}
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        if path.name in EXCLUDE_FILES:
            continue
        try:
            result = subprocess.run(
                [sys.executable, str(path), "--describe"],
                capture_output=True, text=True, timeout=DESCRIBE_TIMEOUT,
            )
            schema = json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            continue
        if not isinstance(schema, dict) or "arguments" not in schema:
            continue
        tools[path.stem] = {"path": path, "schema": schema}
    return tools


# ---------------------------------------------------------------------------
# HTML (kept inline -- this is a small personal-toolbox prototype, not a
# templated multi-page app)
# ---------------------------------------------------------------------------

PAGE_HEAD = """<!doctype html>
<html><head><meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; max-width: 780px;
         margin: 2rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  a {{ color: #0563c1; }}
  .tool-list {{ list-style: none; padding: 0; }}
  .tool-list li {{ margin: 0.4rem 0; }}
  .tool-list code {{ color: #666; font-size: 0.85em; }}
  form label {{ display: block; margin-top: 1rem; font-weight: 600; }}
  form .help {{ font-weight: normal; color: #666; font-size: 0.85em; }}
  input[type=text], input[type=number], input[type=password], textarea, select {{
    width: 100%; box-sizing: border-box; padding: 0.4rem; margin-top: 0.25rem;
    font-family: inherit; font-size: 1rem;
  }}
  textarea {{ font-family: monospace; height: 4.5em; }}
  input[type=checkbox] {{ margin-top: 0.5rem; }}
  button {{ margin-top: 1.5rem; padding: 0.6rem 1.4rem; font-size: 1rem;
            cursor: pointer; }}
  pre#output {{ background: #111; color: #ddd; padding: 1rem; overflow-x: auto;
                white-space: pre-wrap; margin-top: 1rem; min-height: 2em; }}
  .cmdline {{ font-family: monospace; background: #f0f0f0; padding: 0.5rem;
              border-radius: 4px; margin-top: 1rem; word-break: break-all; }}
  .status-ok {{ color: #1a7f37; font-weight: bold; }}
  .status-fail {{ color: #c1121f; font-weight: bold; }}
</style></head><body>
"""
PAGE_TAIL = "</body></html>"


def render_index(tools):
    items = "".join(
        f'<li><a href="{url_for("tool_page", name=name)}">{html.escape(name)}</a> '
        f'<code>{html.escape(t["schema"].get("description", ""))}</code></li>'
        for name, t in tools.items()
    )
    body = f"""
<h1>Tool collection</h1>
<p>Every script here that supports <code>--describe</code> shows up automatically.</p>
<ul class="tool-list">{items or "<li>No describable tools found.</li>"}</ul>
"""
    return PAGE_HEAD.format(title="Tool collection") + body + PAGE_TAIL


def _field_html(arg):
    name = arg["name"]
    label = name.replace("_", " ")
    help_text = html.escape(arg.get("help", ""))
    field_id = f"f_{name}"

    if arg["type"] == "boolean":
        checked = "checked" if arg.get("default") else ""
        return (f'<label><input type="checkbox" id="{field_id}" name="{name}" {checked}> '
                f'{html.escape(label)} <span class="help">{help_text}</span></label>')

    label_html = f'<label for="{field_id}">{html.escape(label)}<div class="help">{help_text}</div></label>'

    if arg["type"] == "enum":
        options = ['<option value="">-- select --</option>']
        default = arg.get("default")
        for choice in arg.get("choices", []):
            sel = "selected" if choice == default else ""
            options.append(f'<option value="{html.escape(choice)}" {sel}>{html.escape(choice)}</option>')
        return label_html + f'<select id="{field_id}" name="{name}">{"".join(options)}</select>'

    if arg["positional"] and arg["multiple"]:
        return (label_html +
                f'<textarea id="{field_id}" name="{name}" placeholder="one per line, or comma-separated"></textarea>')

    input_type = "password" if "password" in name.lower() else \
                 "number" if arg["type"] in ("integer", "number") else "text"
    default = arg.get("default")
    value_attr = f'value="{html.escape(str(default))}"' if default not in (None, False) else ""
    step_attr = 'step="any"' if arg["type"] == "number" else ""
    return label_html + f'<input type="{input_type}" id="{field_id}" name="{name}" {value_attr} {step_attr}>'


def render_tool_page(name, schema):
    fields = "".join(f"<div>{_field_html(arg)}</div>" for arg in schema["arguments"])
    body = f"""
<p><a href="{url_for('index')}">&larr; all tools</a></p>
<h1>{html.escape(name)}</h1>
<p>{html.escape(schema.get("description", ""))}</p>
<form id="tool-form">
  {fields}
  <button type="submit">Run</button>
</form>
<div id="cmdline" class="cmdline" style="display:none"></div>
<pre id="output"></pre>
<script>
document.getElementById('tool-form').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const form = e.target;
  const data = {{}};
  for (const el of form.elements) {{
    if (!el.name) continue;
    if (el.type === 'checkbox') {{ data[el.name] = el.checked; }}
    else {{ data[el.name] = el.value; }}
  }}
  const out = document.getElementById('output');
  const cmd = document.getElementById('cmdline');
  out.textContent = 'Running...';
  cmd.style.display = 'none';
  const resp = await fetch(window.location.pathname + '/run', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(data)
  }});
  const result = await resp.json();
  cmd.textContent = '$ ' + result.cmdline;
  cmd.style.display = 'block';
  out.innerHTML = result.ok ? '<span class="status-ok">OK</span>\\n' : '<span class="status-fail">FAILED</span>\\n';
  const pre = document.createElement('span');
  pre.textContent = result.output;
  out.appendChild(pre);
}});
</script>
"""
    return PAGE_HEAD.format(title=name) + body + PAGE_TAIL


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_index(discover_tools())


@app.route("/tool/<name>")
def tool_page(name):
    tools = discover_tools()
    if name not in tools:
        return redirect(url_for("index"))
    return render_tool_page(name, tools[name]["schema"])


@app.route("/tool/<name>/run", methods=["POST"])
def tool_run(name):
    tools = discover_tools()
    if name not in tools:
        return {"ok": False, "cmdline": "", "output": f"unknown tool: {name}"}, 404

    schema = tools[name]["schema"]
    path = tools[name]["path"]
    values = request.get_json(force=True, silent=True) or {}

    argv = clidescribe.build_argv(schema, values)
    full_cmd = [sys.executable, str(path)] + argv

    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT)
        output = result.stdout + result.stderr
        ok = result.returncode == 0
    except subprocess.TimeoutExpired:
        output = f"(timed out after {RUN_TIMEOUT}s)"
        ok = False

    return {
        "ok": ok,
        "cmdline": " ".join([Path(full_cmd[0]).name, path.name] + argv),
        "output": output,
    }


if __name__ == "__main__":
    print(f"Scanning tools in: {SCRIPTS_DIR}")
    for tool_name in discover_tools():
        print(f"  found: {tool_name}")
    app.run(host="127.0.0.1", port=5000, debug=False)
