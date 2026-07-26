"""Renders a list of Switch objects into a single PNG image, in the
style of the Meraki dashboard stack/VLAN map."""

from PIL import Image, ImageDraw, ImageFont

from vlan_colors import GRAY, build_vlan_color_map, color_for_port

BOX = 34
GAP = 6
MARGIN = 24
SEP = 20            # extra gap between access/SFP/stack groups
SWITCH_GAP = 28      # vertical gap between switch panels
TITLE_H = 34
LEGEND_SWATCH = 18
LEGEND_GAP = 14

BG = (30, 30, 30)
PANEL_BG = (236, 236, 230)
TITLE_COLOR = (20, 20, 20)
TEXT_LIGHT = (255, 255, 255)
LABEL_DARK = (40, 40, 40)


def _font(size, bold=False):
    candidates = [
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
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
FONT_GROUP = _font(10, bold=True)
FONT_LEGEND_TITLE = _font(13, bold=True)
FONT_LEGEND = _font(12)


def _draw_connector_icon(draw, x, y, size=9, color=(255, 255, 255)):
    """Small plug/connector glyph denoting an active (linked) port."""
    body_w = size * 0.65
    draw.rounded_rectangle([x, y + size * 0.35, x + body_w, y + size], radius=1, fill=color)
    prong1 = x + size * 0.15
    prong2 = x + size * 0.45
    draw.line([prong1, y, prong1, y + size * 0.4], fill=color, width=2)
    draw.line([prong2, y, prong2, y + size * 0.4], fill=color, width=2)


def _draw_port_box(draw, x, y, port, color, text_color=TEXT_LIGHT):
    draw.rounded_rectangle([x, y, x + BOX, y + BOX], radius=4, fill=color)
    bbox = draw.textbbox((0, 0), port.label, font=FONT_PORT)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x + (BOX - w) / 2, y + (BOX - h) / 2 - bbox[1]), port.label, font=FONT_PORT, fill=text_color)
    if port.active:
        icon_size = 9
        _draw_connector_icon(draw, x + BOX - icon_size - 2, y + BOX - icon_size - 2, size=icon_size)


def _switch_panel_size(switch):
    n_access_cols = max(1, (len(switch.access_ports) + 1) // 2)
    access_w = n_access_cols * (BOX + GAP) - GAP
    sfp_w = 2 * (BOX + GAP) - GAP if switch.sfp_ports else 0
    stack_w = (BOX + GAP) - GAP if switch.stack_ports else 0

    width = MARGIN * 2 + access_w
    if switch.sfp_ports:
        width += SEP + sfp_w
    if switch.stack_ports:
        width += SEP + stack_w

    height = TITLE_H + MARGIN + 2 * BOX + GAP + MARGIN // 2
    return int(width), int(height), n_access_cols


def render(switches, status_labels, title_text, output_path):
    color_map = build_vlan_color_map(
        p.vlan for sw in switches for p in (sw.access_ports + sw.sfp_ports) if p.port_type == "Access"
    )

    panel_sizes = [_switch_panel_size(sw) for sw in switches]
    panel_w = max(w for w, h, _ in panel_sizes)
    legend_h = 90

    total_h = MARGIN + 28  # header
    for w, h, _ in panel_sizes:
        total_h += h + SWITCH_GAP
    total_h += legend_h

    img = Image.new("RGB", (panel_w + MARGIN * 2, total_h), BG)
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((MARGIN, MARGIN), title_text, font=FONT_TITLE, fill=TEXT_LIGHT)

    y = MARGIN + 36
    for sw, (w, h, n_cols), status in zip(switches, panel_sizes, status_labels):
        x0, y0 = MARGIN, y
        draw.rounded_rectangle([x0, y0, x0 + panel_w, y0 + h], radius=6, fill=PANEL_BG)

        draw.text((x0 + 16, y0 + 10), sw.name, font=FONT_TITLE, fill=TITLE_COLOR)
        bbox = draw.textbbox((0, 0), sw.name, font=FONT_TITLE)
        badge_x = x0 + 16 + (bbox[2] - bbox[0]) + 14
        badge_color = (76, 175, 80) if status.lower() == "active" else (100, 149, 237)
        draw.text((badge_x, y0 + 13), status, font=FONT_BADGE, fill=badge_color)

        grid_y = y0 + TITLE_H + 8
        grid_x = x0 + MARGIN

        # Access ports: odd row on top, even row on bottom (1,3,5.. / 2,4,6..)
        for i, port in enumerate(sw.access_ports):
            col = i // 2
            row = i % 2
            px = grid_x + col * (BOX + GAP)
            py = grid_y + row * (BOX + GAP)
            color = color_for_port(port, color_map)
            _draw_port_box(draw, px, py, port, color)

        next_x = grid_x + n_cols * (BOX + GAP) - GAP

        if sw.sfp_ports:
            sfp_x = next_x + SEP
            draw.text((sfp_x, grid_y - 14), "SFP", font=FONT_GROUP, fill=LABEL_DARK)
            for i, port in enumerate(sw.sfp_ports):
                col = i // 2
                row = i % 2
                px = sfp_x + col * (BOX + GAP)
                py = grid_y + row * (BOX + GAP)
                color = color_for_port(port, color_map)
                _draw_port_box(draw, px, py, port, color)
            next_x = sfp_x + 2 * (BOX + GAP) - GAP

        if sw.stack_ports:
            stack_x = next_x + SEP
            draw.text((stack_x, grid_y - 14), "Stack", font=FONT_GROUP, fill=LABEL_DARK)
            for i, port in enumerate(sw.stack_ports):
                px = stack_x
                py = grid_y + i * (BOX + GAP)
                color = color_for_port(port, color_map)
                _draw_port_box(draw, px, py, port, color)

        y += h + SWITCH_GAP

    # Legend
    legend_y = y + 4
    draw.text((MARGIN, legend_y), "Legenda:", font=FONT_LEGEND_TITLE, fill=TEXT_LIGHT)
    lx = MARGIN
    ly = legend_y + 26
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
            lx = MARGIN
            ly += LEGEND_SWATCH + 10

    draw.rounded_rectangle([lx, ly, lx + LEGEND_SWATCH, ly + LEGEND_SWATCH], radius=3, fill=GRAY)
    _draw_connector_icon(draw, lx + LEGEND_SWATCH - 9 - 1, ly + LEGEND_SWATCH - 9 - 1, size=9)
    draw.text((lx + LEGEND_SWATCH + 8, ly + 1), "Aktivni port (link up)", font=FONT_LEGEND, fill=TEXT_LIGHT)

    img.save(output_path)
    return output_path
