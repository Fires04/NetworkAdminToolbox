"""Color assignment for VLANs, persisted across runs so the same VLAN
always gets the same color in every generated image (within this project)."""

import colorsys
import math
from pathlib import Path

import yaml

GRAY = (158, 158, 158)        # VLAN 1 / untagged default
TRUNK_COLOR = (179, 157, 219)  # lavender
STACK_COLOR = (50, 50, 50)    # near-black

# Curated, mutually contrasting colors. Used first (in order) for new VLANs;
# once exhausted, new colors are generated procedurally.
PALETTE = [
    (239, 154, 102),  # orange
    (100, 181, 246),  # blue
    (102, 187, 165),  # teal/green
    (255, 213, 110),  # amber
    (244, 143, 177),  # pink
    (149, 117, 205),  # purple
    (129, 199, 132),  # green
    (77, 182, 172),   # cyan
    (255, 138, 101),  # deep orange
    (121, 134, 203),  # indigo
]

# Color store lives in the project root (one level above this package file).
DEFAULT_STORE_PATH = Path(__file__).resolve().parent.parent / "vlan_color_map.yaml"

MIN_CONTRAST_DISTANCE = 140  # Euclidean RGB distance between distinct VLAN colors

SPECIAL_KEYS_ORDER = {"1": -2, "trunk": 9_000_000, "stack": 9_000_001}


def _sort_key(vlan: str):
    if vlan in SPECIAL_KEYS_ORDER:
        return (0, SPECIAL_KEYS_ORDER[vlan])
    try:
        return (0, int(vlan))
    except ValueError:
        return (1, vlan)


def _color_distance(c1, c2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _generate_contrasting_color(existing_colors, attempts=300):
    """Pick a color maximally distinct from all existing ones via golden-angle HSV sampling."""
    best, best_score = None, -1
    h = 0.07
    for i in range(attempts):
        h = (h + 0.61803398875) % 1.0
        s = 0.55 + 0.40 * ((i * 7) % 5) / 5
        v = 0.60 + 0.35 * ((i * 3) % 4) / 4
        r, g, b = colorsys.hsv_to_rgb(h, min(s, 0.95), min(v, 0.95))
        candidate = (round(r * 255), round(g * 255), round(b * 255))
        if not existing_colors:
            return candidate
        min_dist = min(_color_distance(candidate, c) for c in existing_colors)
        if min_dist > best_score:
            best, best_score = candidate, min_dist
        if min_dist > MIN_CONTRAST_DISTANCE:
            return candidate
    return best


def load_color_store(path=DEFAULT_STORE_PATH):
    path = Path(path)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(vlan): tuple(rgb) for vlan, rgb in data.items()}


def save_color_store(store, path=DEFAULT_STORE_PATH):
    path = Path(path)
    ordered = {vlan: list(store[vlan]) for vlan in sorted(store, key=_sort_key)}
    path.write_text(yaml.safe_dump(ordered, sort_keys=False), encoding="utf-8")


def build_vlan_color_map(vlan_ids, store_path=DEFAULT_STORE_PATH):
    """Assign a persistent color to each unique VLAN id.

    Loads existing mappings from vlan_color_map.yaml, assigns new colors
    (first from the curated PALETTE, then procedurally generated) for any
    previously unseen VLANs, and saves the updated store back to disk.
    Special keys 'trunk' and 'stack' are always included.
    """
    store = load_color_store(store_path)
    changed = False
    for key, default in (("1", GRAY), ("trunk", TRUNK_COLOR), ("stack", STACK_COLOR)):
        if key not in store:
            store[key] = default
            changed = True

    unique = sorted({v for v in vlan_ids if v}, key=_sort_key)

    for vlan in unique:
        if vlan in store:
            continue
        used = set(store.values())
        candidate = next((c for c in PALETTE if c not in used), None)
        if candidate is None:
            candidate = _generate_contrasting_color(list(used))
        store[vlan] = candidate
        changed = True

    if changed:
        save_color_store(store, store_path)

    keys = unique + ["trunk", "stack"]
    return {key: store[key] for key in keys}


def color_for_port(port, color_map):
    if port.port_type == "Trunk":
        return color_map.get("trunk", TRUNK_COLOR)
    if port.port_type == "Stack":
        return color_map.get("stack", STACK_COLOR)
    return color_map.get(port.vlan, GRAY)
