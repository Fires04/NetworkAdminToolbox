# PyFNetwork

`test_protocol.py` - a reusable CLI tester for whether a host actually
*speaks* a given application protocol (OPC UA, HTTP(S), SSH, FTP, SMTP(S),
POP3(S), IMAP(S), RDP, SMB, Modbus TCP, DNS, NTP, or plain TCP), not just
whether a port is open. See `test_protocol.py --protocols` for the full
list, and `-h` for all options.

## The `clidescribe` convention

`clidescribe.py` is a small, dependency-free helper any argparse-based
script in this collection can use to describe itself as JSON:

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

Add a new tool to the collection by writing a normal argparse script next
to this one and wiring in those two `clidescribe` calls. It will show up in
the web UI automatically, with no extra code anywhere else.

## Web UI

`webui/app.py` is a small Flask app that scans this folder for `*.py`
files, calls `--describe` on each, and auto-generates a form + a run
button for anything that answers with a valid schema.

```
pip install -r webui/requirements.txt
python3 webui/app.py
```

Then open http://127.0.0.1:5000/. It binds to localhost only on purpose --
this is a personal toolbox for scripts you trust, not something to expose
on a network.
