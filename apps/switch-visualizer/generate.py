#!/usr/bin/env python
"""CLI: generate a VLAN/port-map PNG from one or more Meraki switchport CSV exports.

Usage (nový způsob — doporučený):
    python generate.py \\
        -switch "CZOKR-IDF08-H3DressingRoomAccessPoE.117:Member:file117.csv" \\
        -switch "CZOKR-IDF08-H3DressingRoomAccessPoE.118:Active:file118.csv" \\
        -o output.png -t "CZOKR-IDF08-STACK"

Formát argumentu -switch:  "NazevSwitche:Role:cesta/k/souboru.csv"
  - NazevSwitche  — text zobrazený v panelu; pokud je prázdný (""), použije se
                    název ze souboru
  - Role          — Active | Member | Standby (libovolný text)
  - cesta         — cesta k CSV exportu z Meraki dashboardu

Starý způsob (zpětná kompatibilita — první soubor = Active, ostatní = Member):
    python generate.py switch1.csv [switch2.csv ...] -o output.png [-t "Title"]
"""
import argparse
import sys

from csv_parser import parse_switch_csv
from renderer import render

VALID_ROLES = {"active", "member", "standby"}


def parse_switch_arg(value: str):
    """Parse a -switch argument in the form 'Name:Role:file' or 'Name:file'."""
    parts = value.split(":", 2)
    if len(parts) == 3:
        name, role, path = parts
        role = role.strip() or "Member"
    elif len(parts) == 2:
        name, path = parts
        role = "Member"
    else:
        # No colon — treat as plain file path (backward compat)
        name, role, path = "", "Member", parts[0]
    return name.strip(), role.strip(), path.strip()


def main():
    parser = argparse.ArgumentParser(
        description="Generate a VLAN port-map image from Meraki switchport CSVs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-switch",
        dest="switches",
        metavar="NAME:ROLE:FILE",
        action="append",
        help=(
            'Switch definition: "DisplayName:Role:cesta.csv". '
            "Role = Active | Member | Standby. "
            "Lze opakovat pro každý switch ve stacku."
        ),
    )
    parser.add_argument(
        "csv_files",
        nargs="*",
        help="Alternativně: seznam CSV souborů (první = Active, ostatní = Member).",
    )
    parser.add_argument("-o", "--output", default="stack.png", help="Výstupní PNG (default: stack.png)")
    parser.add_argument("-t", "--title", default=None, help="Nadpis obrázku")
    args = parser.parse_args()

    if args.switches:
        # Nový způsob: -switch "Name:Role:file"
        entries = [parse_switch_arg(s) for s in args.switches]
        switches = []
        status_labels = []
        for name, role, path in entries:
            sw = parse_switch_csv(path)
            if name:
                sw.name = name
            switches.append(sw)
            status_labels.append(role)
    elif args.csv_files:
        # Starý způsob: poziční argumenty
        switches = [parse_switch_csv(path) for path in args.csv_files]
        status_labels = ["Active"] + ["Member"] * (len(switches) - 1)
    else:
        parser.error("Zadej alespoň jeden -switch argument nebo CSV soubor.")
        return 1

    title = args.title or " / ".join(sw.name for sw in switches)
    output = render(switches, status_labels, title, args.output)
    print(f"Saved {output}")


if __name__ == "__main__":
    sys.exit(main())
