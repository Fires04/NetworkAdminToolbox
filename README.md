# PyFNetwork

A small personal toolbox combining two kinds of modules into one web UI,
on one host:port:

```
PyFTools/
  cli_scripts/     -- clidescribe-based CLI scripts (run, print output, exit)
  apps/            -- full standalone web apps, one folder each
  webui/           -- the Flask app that ties both together
```

Both are drop-in-a-folder, zero-central-config: add a script or an app
folder and it shows up in the UI automatically, no other code changes.

## `cli_scripts/`

`cli_scripts/protocol_tester.py` ("Protocol Tester" in the UI) - a reusable
CLI tester for whether a host actually *speaks* a given application
protocol (OPC UA, HTTP(S), SSH, FTP, SMTP(S), POP3(S), IMAP(S), RDP, SMB,
Modbus TCP, DNS, NTP, or plain TCP), not just whether a port is open. See
`protocol_tester.py --protocols` for the full list, and `-h` for all
options.

### The `clidescribe` convention

`cli_scripts/clidescribe.py` is a small, dependency-free helper any
argparse-based script in this folder can use to describe itself as JSON:

```python
import clidescribe

def build_parser():
    parser = argparse.ArgumentParser(...)
    parser.add_argument(...)
    clidescribe.add_describe_flag(parser)   # registers --describe
    return parser

def main():
    parser = build_parser()
    if clidescribe.maybe_describe(parser):  # must run BEFORE parse_args()
        return
    args = parser.parse_args()
    ...
```

Any script that does this answers `python3 script.py --describe` with a
JSON schema (name, description, and every argument's flags/type/choices/
default/help/positional/multiple). That's the whole contract -- nothing
web-specific needs to live in the tool itself.

Add a new tool by writing a normal argparse script in `cli_scripts/` and
wiring in those two `clidescribe` calls. It shows up in the web UI
automatically.

A CLI-only flag that doesn't make sense as a web form field (e.g. a "list
choices and exit" flag when the choices already populate an enum dropdown)
can be hidden from the auto-generated form with `clidescribe.hide_from_schema(action)`
while it keeps working normally on the command line.

## `apps/`

Each subfolder of `apps/` with an `app.yaml` manifest is a full standalone
web app (its own framework, own routes) that gets reverse-proxied under
`/app/<folder-name>/` instead of auto-discovered like the CLI scripts --
it's started on first request as a child process bound to `127.0.0.1` on
its own internal port, so it appears under the toolbox's own address
instead of a separate port.

`apps/switch-visualizer/` (from
[NetworkAdminToolbox](https://github.com/Fires04/NetworkAdminToolbox)) is
an example: a FastAPI/uvicorn app with its own `pyproject.toml`.

### Adding an app module

1. Drop the project under `apps/<name>/`.
2. Add `apps/<name>/app.yaml`:
   ```yaml
   description: "One-line description shown on the toolbox card"
   port: 8002                    # 127.0.0.1-only, pick one that's free
   cmd: ["{python}", "-m", "uvicorn", "web.app:app",
         "--host", "127.0.0.1", "--port", "{port}"]
   ```
   `{python}` (sys.executable) and `{port}` are substituted at launch time.
3. If it has its own dependencies, wire `pip install ./apps/<name>` (or its
   requirements file) into the `Dockerfile`.

The proxy rewrites root-absolute path literals (`fetch('/x')`, `href="/x"`)
in HTML responses so an app that assumes it's served from the domain root
still works when mounted under `/app/<name>/`.

## Web UI

```
pip install -r webui/requirements.txt
python3 webui/app.py
```

Then open http://127.0.0.1:5000/. The home page lists CLI tools and web
apps in separate sections, with a search box that filters both live.

### Docker

The whole toolbox (CLI scripts + apps) builds into a single image:

```
docker build -t pyfnetwork-toolbox .
docker run -d -p 5000:5000 pyfnetwork-toolbox
```

or with `docker-compose.yml`:

```
docker compose up -d --build
```

Only the toolbox's own port is exposed -- each app's internal port
(`apps/*/app.yaml`) stays bound to `127.0.0.1` inside the container.
