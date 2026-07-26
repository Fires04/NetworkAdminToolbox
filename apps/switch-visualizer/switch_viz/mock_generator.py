"""Generate synthetic Switch objects from a stack YAML config.

This replaces the copy-paste generate_test_csv_*.py scripts. Instead of
writing CSV files to disk and calling generate.py via subprocess, we build
Switch/Port objects in memory directly and hand them to the renderer.
"""

from switch_viz.csv_parser import Port, Switch


HEADER = [
    "#", "Name", "Type", "VLAN", "LLDP / CDP",
    "Link", "Current traffic", "Total bytes", "RSTP", "Mirror",
]


def _vlan_for_port(port_num: int, vlan_ranges: list) -> tuple[str, str]:
    """Return (port_type, vlan) for a given port number.

    vlan_ranges is a list of dicts with keys: ports [start, end], vlan, type (optional).
    Ports not covered by any range default to Access VLAN 1.
    """
    for r in vlan_ranges:
        start, end = r["ports"]
        if start <= port_num <= end:
            return r.get("type", "Access"), str(r["vlan"])
    return "Access", "1"


def generate_switch(name: str, vlan_ranges: list, sfp_connected: set) -> Switch:
    """Build a synthetic Switch object without touching the filesystem.

    Args:
        name:          Display name of the switch.
        vlan_ranges:   List of range dicts from the stack YAML config.
        sfp_connected: Set of SFP port numbers (49-52) that are forwarding.
    """
    sw = Switch(name=name)

    for p in range(1, 49):
        port_type, vlan = _vlan_for_port(p, vlan_ranges)
        sw.access_ports.append(Port(
            label=str(p),
            port_type=port_type,
            vlan=vlan,
            active=False,  # synthetic access ports are never "connected"
        ))

    for p in range(49, 53):
        port_type = "Trunk"
        vlan = "1"
        active = p in sfp_connected
        sw.sfp_ports.append(Port(
            label=str(p),
            port_type=port_type,
            vlan=vlan,
            active=active,
        ))

    for idx in (1, 2):
        sw.stack_ports.append(Port(
            label=f"S{idx}",
            port_type="Stack",
            vlan="",
            active=True,  # dedicated stack ports are always active by definition
        ))

    return sw


def load_stack_config(config_path: str) -> dict:
    """Load and validate a stack YAML config file."""
    import yaml
    from pathlib import Path

    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))

    if "switches" not in data or not data["switches"]:
        raise ValueError(f"{config_path}: 'switches' list is required")
    if "vlan_ranges" not in data:
        raise ValueError(f"{config_path}: 'vlan_ranges' list is required")

    # Normalise vlan values to strings
    for r in data["vlan_ranges"]:
        r["vlan"] = str(r["vlan"])

    data.setdefault("sfp_connected", [49])
    data.setdefault("title", "")

    return data


def switches_from_config(config: dict) -> tuple[list, list]:
    """Return (switches, status_labels) from a loaded config dict."""
    sfp_connected = set(config["sfp_connected"])
    switches = []
    status_labels = []

    for sw_cfg in config["switches"]:
        sw = generate_switch(
            name=sw_cfg["name"],
            vlan_ranges=config["vlan_ranges"],
            sfp_connected=sfp_connected,
        )
        switches.append(sw)
        status_labels.append(sw_cfg.get("role", "Member"))

    return switches, status_labels
