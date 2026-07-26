#!/usr/bin/env python
"""Generate fake Meraki switchport CSVs for the IDF07-Stack2 test stack
(3x C9200L-48PL-4X-style switches), then render them with generate.py.

Edit VLAN_RANGES below and re-run to try out different port layouts.
Ports not covered by any range default to VLAN 1.
"""
import csv
import subprocess
import sys
from pathlib import Path

# (start_port, end_port, port_type, vlan) - inclusive ranges, checked in order
VLAN_RANGES = [
    (19, 30, "Access", "50"),
    (31, 34, "Access", "309"),
    (35, 36, "Access", "310"),
    (37, 46, "Access", "501"),
    (47, 48, "Trunk", "native 1"),
]

# Which SFP ports (49-52) are actually plugged in / forwarding. Any not
# listed here are rendered as unconnected, same as a real empty SFP slot.
SFP_CONNECTED = {49}

SWITCH_NAMES = [
    "CZOKR-IDF07-H3DressingRoomAccessPoE.139",
    "CZOKR-IDF07-H3DressingRoomAccessPoE.140",
    "CZOKR-IDF07-H3DressingRoomAccessPoE.141",
]

TITLE = "IDF07-Stack2"

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "testdata"

HEADER = ["#", "Name", "Type", "VLAN", "LLDP / CDP", "Link", "Current traffic", "Total bytes", "RSTP", "Mirror"]


def vlan_for_port(p):
    for start, end, port_type, vlan in VLAN_RANGES:
        if start <= p <= end:
            return port_type, vlan
    return "Access", "1"


def write_csv(name: str) -> Path:
    rows = [HEADER]
    for p in range(1, 49):
        ptype, vlan = vlan_for_port(p)
        # No real device plugged in for these synthetic ports, so RSTP stays
        # "Enabled" (link down) rather than "Forwarding" (link up) - matches
        # what an empty Meraki access port reports, and keeps the "active
        # port" connector icon reserved for ports that are actually in use.
        rows.append([str(p), "", ptype, vlan, "—", "Auto negotiate",
                     "— sent, — received", "—", "Enabled", ""])
    for p in range(49, 53):
        if p in SFP_CONNECTED:
            rows.append([str(p), "", "Trunk", "native 1", "—", "Auto negotiate (10 Gbps)",
                         "100 kb/s sent, 50 kb/s received", "1 GB", "Forwarding", ""])
        else:
            rows.append([str(p), "", "Trunk", "native 1", "—", "Auto negotiate",
                         "— sent, — received", "—", "Enabled", ""])
    rows.append(["Dedicated stack port 1", f"{name}, Port 54", "Stack", "1", "—", "",
                 "1 mb/s sent, 1 mb/s received", "10 GB", "'-", ""])
    rows.append(["Dedicated stack port 2", f"{name}, Port 53", "Stack", "1", "—", "",
                 "1 mb/s sent, 1 mb/s received", "10 GB", "'-", ""])

    OUTDIR.mkdir(exist_ok=True)
    path = OUTDIR / f"{name} switchports.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, quoting=csv.QUOTE_ALL).writerows(rows)
    return path


def main():
    paths = [write_csv(name) for name in SWITCH_NAMES]
    for p in paths:
        print(p)

    output_png = OUTDIR / "idf07_stack2.png"
    subprocess.run(
        [sys.executable, str(ROOT / "generate.py"), *map(str, paths), "-o", str(output_png), "-t", TITLE],
        check=True,
    )


if __name__ == "__main__":
    main()
