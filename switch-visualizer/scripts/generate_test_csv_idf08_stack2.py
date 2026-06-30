#!/usr/bin/env python
"""Generate fake Meraki switchport CSVs for the IDF08-Stack2 test stack
(3x C9200L-48PL-4X-style switches), then render them with generate.py.

Edit VLAN_RANGES / SFP_CONNECTED below and re-run to try out different layouts.
Ports not covered by any range default to VLAN 1.
"""
import csv
import subprocess
import sys
from pathlib import Path

# (start_port, end_port, port_type, vlan) - inclusive ranges, checked in order
VLAN_RANGES = [
    (23, 34, "Access", "50"),
    (35, 38, "Access", "309"),
    (39, 46, "Access", "501"),
    (47, 48, "Trunk", "native 1"),
]

# Which SFP ports (49-52) are actually plugged in / forwarding.
SFP_CONNECTED = {49}

SWITCH_NAMES = [
    "CZOKR-IDF08-H4AccessPoE.143",
    "CZOKR-IDF08-H4AccessPoE.144",
    "CZOKR-IDF08-H4AccessPoE.145",
]

TITLE = "IDF08-Stack2"

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

    output_png = OUTDIR / "idf08_stack2.png"
    switch_args = []
    roles = ["Active"] + ["Member"] * (len(SWITCH_NAMES) - 1)
    for name, role, path in zip(SWITCH_NAMES, roles, paths):
        switch_args += ["-switch", f"{name}:{role}:{path}"]

    subprocess.run(
        [sys.executable, str(ROOT / "generate.py"), *switch_args, "-o", str(output_png), "-t", TITLE],
        check=True,
    )


if __name__ == "__main__":
    main()
