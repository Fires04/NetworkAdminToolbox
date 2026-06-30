"""Renders Switch objects into a PNG image in Meraki dashboard style."""

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from switch_viz.vlan_colors import GRAY, build_vlan_color_map, color_for_port
from switch_viz.csv_parser import Port, Switch

# ── layout constants ──────────────────────────────────────────────────────────

BOX = 34
GAP = 6
MARGIN = 24
SEP = 20          # gap between access / SFP / stack groups
SWITCH_GAP = 28   # vertical gap between switch panels
TITLE_H = 34
LEGEND_SWATCH = 18
LEGEND_GAP = 14

BG = (30, 30, 30)
PANEL_BG = (236, 236, 230)
TITLE_COLOR = (20, 20, 20)
TEXT_LIGHT = (255, 255, 255)
LABEL_DARK = (40, 40, 40)


# ── render options ────────────────────────────────────────────────────────────

@dataclass
class RenderOptions:
    port_order: str = "columns"       # "columns" | "rows"
    port_one_top: bool = True         # True = port 1 on top row
    stack_ports: int = 2              # synthetic stack ports for simple CSV (0-2)
    sfp_ports: list = None            # port labels to show as SFP, e.g. ["49","50","51","52"]

    def __post_init__(self):
        if self.sfp_ports is None:
            self.sfp_ports = []


DEFAULT_OPTIONS = RenderOptions()


# ── fonts ─────────────────────────────────────────────────────────────────────

def _font(size, bold=False):
    candidates = [
        "segoeuib.ttf" if bold else "segoeui.ttf",   # Windows
        "arialbd.ttf"  if bold else "arial.ttf",      # Windows fallback
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",          # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",   # Linux absolute
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_TITLE = _font(16, bold=True)
FONT_BADGE = _font(11, bold=True)
FONT_PORT = _font(10)
FONT_TINY = _font(7)
FONT_GROUP = _font(10, bold=True)
FONT_LEGEND_TITLE = _font(13, bold=True)
FONT_LEGEND = _font(12)


# ── drawing helpers ───────────────────────────────────────────────────────────

def _draw_connector_icon(draw, x, y, size=9, color=(255, 255, 255)):
    """Small plug glyph: two prongs + body, placed in the bottom-right corner."""
    body_w = size * 0.65
    draw.rounded_rectangle([x, y + size * 0.35, x + body_w, y + size], radius=1, fill=color)
    for prong_x in (x + size * 0.15, x + size * 0.45):
        draw.line([prong_x, y, prong_x, y + size * 0.4], fill=color, width=2)


def _draw_port_box(draw, x, y, port, color):
    draw.rounded_rectangle([x, y, x + BOX, y + BOX], radius=4, fill=color)
    # Port label — shifted slightly up when native_vlan label is present
    label_offset_y = -3 if port.native_vlan else 0
    bbox = draw.textbbox((0, 0), port.label, font=FONT_PORT)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (x + (BOX - w) / 2, y + (BOX - h) / 2 - bbox[1] + label_offset_y),
        port.label, font=FONT_PORT, fill=TEXT_LIGHT,
    )
    # Native VLAN label — bottom-left corner
    if port.native_vlan:
        draw.text((x + 2, y + BOX - 10), port.native_vlan, font=FONT_TINY, fill=TEXT_LIGHT)
    # Active icon — bottom-right corner
    if port.active:
        s = 9
        _draw_connector_icon(draw, x + BOX - s - 2, y + BOX - s - 2, size=s)


# ── port layout ───────────────────────────────────────────────────────────────

def _arrange_ports(ports: list, opts: RenderOptions) -> list[tuple]:
    """Return list of (port, col, row) based on port_order and port_one_top.

    columns mode (Meraki style): ports fill column-by-column, 2 rows deep.
      port[0] → (col=0, row=0), port[1] → (col=0, row=1),
      port[2] → (col=1, row=0), ...

    rows mode (Cisco Catalyst style): first half fills top row, second half bottom.
      port[0..N/2-1] → row=0; port[N/2..] → row=1
    """
    result = []
    n = len(ports)
    if opts.port_order == "columns":
        for i, port in enumerate(ports):
            col = i // 2
            row = i % 2
            if not opts.port_one_top:
                row = 1 - row
            result.append((port, col, row))
    else:  # rows
        n_top = math.ceil(n / 2)
        for i, port in enumerate(ports):
            if i < n_top:
                col, row = i, 0
            else:
                col, row = i - n_top, 1
            if not opts.port_one_top:
                row = 1 - row
            result.append((port, col, row))
    return result


def _n_cols(ports: list, opts: RenderOptions) -> int:
    if not ports:
        return 0
    return math.ceil(len(ports) / 2)


# ── switch normalisation ──────────────────────────────────────────────────────

def _effective_ports(sw: Switch, opts: RenderOptions) -> tuple[list, list, list]:
    """Resolve access / sfp / stack port lists, applying RenderOptions.

    opts.sfp_ports is a list of port labels (strings) that should be shown as
    SFP uplinks. Ports are pulled from the combined access+sfp pool so the
    label list works identically for Meraki and simple CSV formats.
    opts.stack_ports controls synthetic stack port count for simple CSVs;
    for Meraki CSVs actual stack ports from the parser are used (unless 0).
    """
    all_ports = list(sw.access_ports) + list(sw.sfp_ports)
    stack = list(sw.stack_ports)

    if opts.sfp_ports:
        sfp_labels = set(opts.sfp_ports)
        sfp = [p for p in all_ports if p.label in sfp_labels]
        access = [p for p in all_ports if p.label not in sfp_labels]
    else:
        sfp = []
        access = all_ports

    if not stack and opts.stack_ports > 0:
        stack = [
            Port(label=f"S{i}", port_type="Stack", vlan="", active=True)
            for i in range(1, opts.stack_ports + 1)
        ]
    if opts.stack_ports == 0:
        stack = []

    return access, sfp, stack


# ── panel sizing ──────────────────────────────────────────────────────────────

def _panel_size(access, sfp, stack, opts):
    n_cols = _n_cols(access, opts)
    access_w = max(1, n_cols) * (BOX + GAP) - GAP
    sfp_w = math.ceil(len(sfp) / 2) * (BOX + GAP) - GAP if sfp else 0
    stack_w = (BOX + GAP) - GAP if stack else 0

    width = MARGIN * 2 + access_w
    if sfp:
        width += SEP + sfp_w
    if stack:
        width += SEP + stack_w

    height = TITLE_H + MARGIN + 2 * BOX + GAP + MARGIN // 2
    return int(width), int(height)


# ── main render ───────────────────────────────────────────────────────────────

def render(
    switches: list,
    status_labels: list[str],
    title_text: str,
    output_path: str,
    options: RenderOptions = None,
    options_per_switch: list = None,
    color_map_override: dict = None,
) -> Path:
    def _opts(i: int) -> RenderOptions:
        if options_per_switch and i < len(options_per_switch):
            return options_per_switch[i]
        return options or DEFAULT_OPTIONS

    all_access_vlans = (
        p.vlan
        for sw in switches
        for p in sw.access_ports
        if p.port_type == "Access"
    )
    color_map = build_vlan_color_map(all_access_vlans)

    if color_map_override:
        for k, v in color_map_override.items():
            if isinstance(v, str) and v.startswith("#"):
                h = v.lstrip("#")
                color_map[k] = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            elif isinstance(v, (list, tuple)) and len(v) == 3:
                color_map[k] = tuple(v)

    panels = []
    for i, sw in enumerate(switches):
        sw_opts = _opts(i)
        access, sfp, stack = _effective_ports(sw, sw_opts)
        panels.append((sw, access, sfp, stack, sw_opts))

    sizes = [_panel_size(a, s, st, sw_opts) for _, a, s, st, sw_opts in panels]
    panel_w = max(w for w, h in sizes)
    legend_h = 90

    total_h = MARGIN + 28
    for w, h in sizes:
        total_h += h + SWITCH_GAP
    total_h += legend_h

    img = Image.new("RGB", (panel_w + MARGIN * 2, total_h), BG)
    draw = ImageDraw.Draw(img)

    draw.text((MARGIN, MARGIN), title_text, font=FONT_TITLE, fill=TEXT_LIGHT)

    y = MARGIN + 36
    for (sw, access, sfp, stack, sw_opts), (pw, ph), status in zip(panels, sizes, status_labels):
        x0, y0 = MARGIN, y
        draw.rounded_rectangle([x0, y0, x0 + panel_w, y0 + ph], radius=6, fill=PANEL_BG)

        draw.text((x0 + 16, y0 + 10), sw.name, font=FONT_TITLE, fill=TITLE_COLOR)
        bbox = draw.textbbox((0, 0), sw.name, font=FONT_TITLE)
        badge_x = x0 + 16 + (bbox[2] - bbox[0]) + 14
        badge_color = (76, 175, 80) if status.lower() == "active" else (100, 149, 237)
        draw.text((badge_x, y0 + 13), status, font=FONT_BADGE, fill=badge_color)

        grid_y = y0 + TITLE_H + 8
        grid_x = x0 + MARGIN

        # Access ports
        for port, col, row in _arrange_ports(access, sw_opts):
            px = grid_x + col * (BOX + GAP)
            py = grid_y + row * (BOX + GAP)
            _draw_port_box(draw, px, py, port, color_for_port(port, color_map))

        n_cols = _n_cols(access, sw_opts)
        next_x = grid_x + max(1, n_cols) * (BOX + GAP) - GAP

        # SFP ports
        if sfp:
            sfp_x = next_x + SEP
            draw.text((sfp_x, grid_y - 14), "SFP", font=FONT_GROUP, fill=LABEL_DARK)
            for port, col, row in _arrange_ports(sfp, sw_opts):
                px = sfp_x + col * (BOX + GAP)
                py = grid_y + row * (BOX + GAP)
                _draw_port_box(draw, px, py, port, color_for_port(port, color_map))
            next_x = sfp_x + math.ceil(len(sfp) / 2) * (BOX + GAP) - GAP

        # Stack ports
        if stack:
            stack_x = next_x + SEP
            draw.text((stack_x, grid_y - 14), "Stack", font=FONT_GROUP, fill=LABEL_DARK)
            for i, port in enumerate(stack):
                py = grid_y + i * (BOX + GAP)
                _draw_port_box(draw, stack_x, py, port, color_for_port(port, color_map))

        y += ph + SWITCH_GAP

    # Legend
    legend_y = y + 4
    draw.text((MARGIN, legend_y), "Legenda:", font=FONT_LEGEND_TITLE, fill=TEXT_LIGHT)
    lx, ly = MARGIN, legend_y + 26

    entries = [("VLAN 1", color_map["1"])]
    for vlan, color in color_map.items():
        if vlan in ("1", "trunk", "stack"):
            continue
        entries.append((f"VLAN {vlan}", color))
    entries.append(("Trunk", color_map["trunk"]))
    entries.append(("Stack", color_map["stack"]))

    for label, color in entries:
        draw.rounded_rectangle([lx, ly, lx + LEGEND_SWATCH, ly + LEGEND_SWATCH], radius=3, fill=color)
        draw.text((lx + LEGEND_SWATCH + 8, ly + 1), label, font=FONT_LEGEND, fill=TEXT_LIGHT)
        bbox = draw.textbbox((0, 0), label, font=FONT_LEGEND)
        lx += LEGEND_SWATCH + 8 + (bbox[2] - bbox[0]) + LEGEND_GAP
        if lx > panel_w - 80:
            lx, ly = MARGIN, ly + LEGEND_SWATCH + 10

    draw.rounded_rectangle([lx, ly, lx + LEGEND_SWATCH, ly + LEGEND_SWATCH], radius=3, fill=GRAY)
    _draw_connector_icon(draw, lx + LEGEND_SWATCH - 9 - 1, ly + LEGEND_SWATCH - 9 - 1, size=9)
    draw.text((lx + LEGEND_SWATCH + 8, ly + 1), "Aktivní port (link up)", font=FONT_LEGEND, fill=TEXT_LIGHT)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
