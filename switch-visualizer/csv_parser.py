"""Parser for Meraki switch port-status CSV exports."""
import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Port:
    label: str           # display label, e.g. "1", "49", "S1", "S2"
    port_type: str       # Access, Trunk, Stack
    vlan: str             # VLAN id as string ("1", "501", "native 1", ...)
    name: str = ""
    active: bool = False  # True if the port has an established link (RSTP "Forwarding")


@dataclass
class Switch:
    name: str
    access_ports: list = field(default_factory=list)   # ports 1..48, in CSV order
    sfp_ports: list = field(default_factory=list)        # ports 49..52
    stack_ports: list = field(default_factory=list)      # dedicated stack ports


def vlan_id(raw_vlan: str) -> str:
    """Normalize a VLAN field, e.g. 'native 1' -> '1'."""
    raw_vlan = (raw_vlan or "").strip()
    if raw_vlan.lower().startswith("native"):
        return raw_vlan.split()[-1]
    return raw_vlan


def parse_switch_csv(path: str) -> Switch:
    """Parse a single Meraki switchport CSV export into a Switch.

    Row layout (after the header row) is positional, not driven by the
    free-text '#' column (which can contain combined trunk descriptions
    for stacked uplinks instead of a plain port number):
      - first 48 data rows  -> access ports 1-48
      - next data rows whose '#' does not start with 'Dedicated stack port'
        -> SFP/uplink ports (typically 49-52)
      - rows whose '#' starts with 'Dedicated stack port' -> stack ports
    """
    p = Path(path)
    switch = Switch(name=p.stem)

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return switch

    data_rows = rows[1:]  # skip header

    access_count = 0
    for row in data_rows:
        if not row:
            continue
        num_field = row[0].strip()
        name = row[1].strip() if len(row) > 1 else ""
        port_type = row[2].strip() if len(row) > 2 else ""
        vlan = vlan_id(row[3]) if len(row) > 3 else ""
        rstp = row[8].strip().lower() if len(row) > 8 else ""
        # Dedicated stack ports don't run STP - Meraki reports RSTP as "'-"
        # for them - but a listed stack port is, by definition, an active
        # stack link, so it doesn't go through the forwarding/blocked check.
        is_stack_row = num_field.startswith("Dedicated stack port")
        active = True if is_stack_row else rstp == "forwarding"

        if is_stack_row:
            idx = num_field.replace("Dedicated stack port", "").strip()
            switch.stack_ports.append(Port(label=f"S{idx}", port_type="Stack", vlan="", name=name, active=active))
        elif access_count < 48:
            access_count += 1
            switch.access_ports.append(Port(label=str(access_count), port_type=port_type, vlan=vlan, name=name, active=active))
        else:
            sfp_index = len(switch.sfp_ports) + 49
            switch.sfp_ports.append(Port(label=str(sfp_index), port_type=port_type, vlan=vlan, name=name, active=active))

    return switch
