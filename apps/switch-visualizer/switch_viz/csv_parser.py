"""Parser for Meraki and generic switch-port CSV exports.

Supports three input formats, auto-detected from the header row:

  Meraki   — Meraki Dashboard export:
             "#","Name","Type","VLAN","LLDP / CDP","Link","Current traffic",
             "Total bytes","RSTP","Mirror"

  Simple   — Generic CSV with port metadata:
             Port,VLAN,Type,Connected
             Type defaults to Access; Connected = true/yes/1 → active.

  Minimal  — Bare port list:
             Port,VLAN
             All ports are Access, none active.

All formats produce a Switch with:
  - access_ports: all numbered access + trunk ports from the CSV
  - sfp_ports:    ports detected as SFP uplinks (Meraki format only)
  - stack_ports:  dedicated stack links (Meraki format only)
Port count is always derived from the data, never hardcoded.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Port:
    label: str            # e.g. "1", "49", "S1"
    port_type: str        # Access | Trunk | Stack
    vlan: str             # normalised VLAN id string
    name: str = ""
    active: bool = False  # True if RSTP Forwarding / connected flag set
    native_vlan: str = "" # optional label shown bottom-left in port box


@dataclass
class Switch:
    name: str
    access_ports: list = field(default_factory=list)
    sfp_ports: list = field(default_factory=list)
    stack_ports: list = field(default_factory=list)


# ── helpers ───────────────────────────────────────────────────────────────────

def _norm_vlan(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.lower().startswith("native"):
        return raw.split()[-1]
    return raw or "1"


def _truthy(val: str) -> bool:
    return val.strip().lower() in {"true", "yes", "1", "forwarding"}


# ── format detection ──────────────────────────────────────────────────────────

def detect_format(header: list[str]) -> str:
    """Return 'meraki' | 'simple' | 'minimal' based on the header row."""
    h = [c.strip().strip('"').lower() for c in header]
    if h and h[0] == "#":
        return "meraki"
    if "port" in h and "vlan" in h and ("type" in h or "connected" in h):
        return "simple"
    if "port" in h and "vlan" in h:
        return "minimal"
    # Fallback: treat as minimal (port in first col, vlan in second)
    return "minimal"


# ── format-specific parsers ───────────────────────────────────────────────────

def _parse_meraki(rows: list[list[str]]) -> tuple[list, list, list]:
    """Parse Meraki Dashboard export rows (after header stripped)."""
    access, sfp, stack = [], [], []
    access_count = 0

    for row in rows:
        if not row:
            continue
        num_field = row[0].strip().strip('"')
        name = row[1].strip().strip('"') if len(row) > 1 else ""
        port_type = row[2].strip().strip('"') if len(row) > 2 else "Access"
        vlan = _norm_vlan(row[3]) if len(row) > 3 else "1"
        rstp = row[8].strip().strip('"').lower() if len(row) > 8 else ""

        is_stack = num_field.startswith("Dedicated stack port")
        active = True if is_stack else rstp == "forwarding"

        if is_stack:
            idx = num_field.replace("Dedicated stack port", "").strip()
            stack.append(Port(label=f"S{idx}", port_type="Stack", vlan="", name=name, active=True))
        elif access_count < 48:
            access_count += 1
            access.append(Port(label=str(access_count), port_type=port_type, vlan=vlan, name=name, active=active))
        else:
            # SFP / uplink ports that come after the first 48 access ports
            sfp_label = str(49 + len(sfp))
            sfp.append(Port(label=sfp_label, port_type=port_type, vlan=vlan, name=name, active=active))

    return access, sfp, stack


def _parse_simple(header: list[str], rows: list[list[str]]) -> list:
    """Parse simple/minimal CSV: Port,VLAN[,Type[,Connected]]"""
    h = [c.strip().strip('"').lower() for c in header]
    col = {name: idx for idx, name in enumerate(h)}

    ports = []
    for row in rows:
        if not row or not row[0].strip():
            continue
        port_num = row[col["port"]].strip().strip('"')
        vlan = _norm_vlan(row[col["vlan"]]) if "vlan" in col else "1"
        port_type = row[col.get("type", -1)].strip().strip('"') if "type" in col else "Access"
        connected_raw = row[col["connected"]].strip().strip('"') if "connected" in col else "false"
        active = _truthy(connected_raw)
        ports.append(Port(label=port_num, port_type=port_type or "Access", vlan=vlan, active=active))

    return ports


# ── public API ────────────────────────────────────────────────────────────────

def parse_switch_csv(path: str, name: str = "") -> Switch:
    """Parse a switch CSV into a Switch object.

    The display name defaults to the file stem when not supplied.
    Port count is dynamic — driven entirely by the data.
    """
    p = Path(path)
    sw = Switch(name=name or p.stem)

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return sw

    header = rows[0]
    data_rows = rows[1:]
    fmt = detect_format(header)

    if fmt == "meraki":
        sw.access_ports, sw.sfp_ports, sw.stack_ports = _parse_meraki(data_rows)
    else:
        # simple / minimal: all rows → access_ports; no SFP/stack from CSV
        sw.access_ports = _parse_simple(header, data_rows)

    return sw


def parse_switch_content(content: str, name: str = "") -> Switch:
    """Parse CSV content from a string (used by the web app for uploaded files)."""
    import io
    sw = Switch(name=name)
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    if not rows:
        return sw

    header = rows[0]
    data_rows = rows[1:]
    fmt = detect_format(header)

    if fmt == "meraki":
        sw.access_ports, sw.sfp_ports, sw.stack_ports = _parse_meraki(data_rows)
    else:
        sw.access_ports = _parse_simple(header, data_rows)

    return sw
