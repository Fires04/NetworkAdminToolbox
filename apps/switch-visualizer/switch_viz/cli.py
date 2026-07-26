"""mviz — Switch stack VLAN port-map visualiser.

Sub-commands
------------
render   Generate a PNG from real Meraki switchport CSV exports.
mock     Generate a PNG from a YAML stack config (no real CSVs needed).

Examples
--------
# Real CSV exports from Meraki dashboard:
mviz render \\
    --switch "CZOKR-IDF08-H3.117:Member:117.csv" \\
    --switch "CZOKR-IDF08-H3.118:Active:118.csv" \\
    -o output/idf08.png -t "CZOKR-IDF08-STACK"

# Planning / mock image from YAML config:
mviz mock --config configs/idf07_stack2.yaml
mviz mock --config configs/idf08_stack2.yaml -o custom.png
"""

import argparse
import sys
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_switch_arg(value: str):
    """Parse a --switch argument: 'Name:Role:file' | 'Name:file' | 'file'."""
    parts = value.split(":", 2)
    if len(parts) == 3:
        name, role, path = parts
    elif len(parts) == 2:
        name, path = parts
        role = "Member"
    else:
        name, role, path = "", "Member", parts[0]
    return name.strip(), role.strip() or "Member", path.strip()


# ── sub-command: render ───────────────────────────────────────────────────────

def _cmd_render(args):
    from switch_viz.csv_parser import parse_switch_csv
    from switch_viz.renderer import render

    if args.switch:
        switches, status_labels = [], []
        for raw in args.switch:
            name, role, path = _parse_switch_arg(raw)
            sw = parse_switch_csv(path)
            if name:
                sw.name = name
            switches.append(sw)
            status_labels.append(role)
    elif args.csv_files:
        switches = [parse_switch_csv(p) for p in args.csv_files]
        status_labels = ["Active"] + ["Member"] * (len(switches) - 1)
    else:
        print("render: zadej alespoň jeden --switch nebo CSV soubor.", file=sys.stderr)
        return 1

    title = args.title or " / ".join(sw.name for sw in switches)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out = render(switches, status_labels, title, args.output)
    print(f"Saved {out}")
    return 0


# ── sub-command: mock ─────────────────────────────────────────────────────────

def _cmd_mock(args):
    from switch_viz.mock_generator import load_stack_config, switches_from_config
    from switch_viz.renderer import render

    config = load_stack_config(args.config)
    switches, status_labels = switches_from_config(config)

    title = args.title or config.get("title") or " / ".join(sw.name for sw in switches)
    output = args.output or config.get("output") or "stack.png"

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    out = render(switches, status_labels, title, output)
    print(f"Saved {out}")
    return 0


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="mviz",
        description="Switch stack VLAN port-map visualiser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # -- render ---------------------------------------------------------------
    p_render = sub.add_parser(
        "render",
        help="Generate PNG from real Meraki switchport CSV exports",
        description=_cmd_render.__doc__,
    )
    p_render.add_argument(
        "--switch", "-s",
        metavar="NAME:ROLE:FILE",
        action="append",
        help='Switch definition "DisplayName:Role:file.csv" (opakovatelný). Role = Active | Member | Standby.',
    )
    p_render.add_argument(
        "csv_files",
        nargs="*",
        metavar="FILE",
        help="CSV soubory (zpětná kompatibilita; první = Active, ostatní = Member).",
    )
    p_render.add_argument("-o", "--output", default="stack.png", metavar="PNG", help="Výstupní PNG (default: stack.png)")
    p_render.add_argument("-t", "--title", default=None, metavar="TEXT", help="Nadpis obrázku")

    # -- mock -----------------------------------------------------------------
    p_mock = sub.add_parser(
        "mock",
        help="Generate PNG from a YAML stack config (no real CSVs needed)",
    )
    p_mock.add_argument(
        "--config", "-c",
        required=True,
        metavar="YAML",
        help="Cesta k YAML konfiguraci stacku (viz configs/*.yaml).",
    )
    p_mock.add_argument("-o", "--output", default=None, metavar="PNG", help="Výstupní PNG (přepíše hodnotu z YAML)")
    p_mock.add_argument("-t", "--title", default=None, metavar="TEXT", help="Nadpis obrázku (přepíše hodnotu z YAML)")

    args = parser.parse_args()

    if args.command == "render":
        return _cmd_render(args)
    if args.command == "mock":
        return _cmd_mock(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
