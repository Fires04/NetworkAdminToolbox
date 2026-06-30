"""SwitchVisualizer — FastAPI web application."""

import csv as _csv
import io
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from switch_viz.csv_parser import Port, Switch, detect_format, parse_switch_content
from switch_viz.renderer import RenderOptions, render

app = FastAPI(title="SwitchVisualizer")

BASE_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = BASE_DIR / "samples"
_INDEX_HTML = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")

_result_cache: dict[str, bytes] = {}


# ── Pydantic models ───────────────────────────────────────────────────────────

class PortIn(BaseModel):
    label: str
    name: str = ""
    port_type: str = "Access"
    vlan: str = "1"
    native_vlan: str = ""
    active: bool = False


class SwitchLayout(BaseModel):
    port_order: str = "columns"
    port_one_top: bool = True
    stack_ports: int = 2
    sfp_ports: list[str] = []


class SwitchIn(BaseModel):
    name: str
    role: str = "Active"
    ports: list[PortIn]
    layout: SwitchLayout = SwitchLayout()


class GenerateRequest(BaseModel):
    title: str = ""
    vlan_colors: dict[str, str] = {}   # vlan_id → "#rrggbb"
    switches: list[SwitchIn]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=_INDEX_HTML)


@app.post("/prefill")
async def prefill(files: Annotated[list[UploadFile], File()]):
    """Parse uploaded CSV files and return structured port data for the editor."""
    result: dict = {"switches": [], "sfp_ports": [], "stack_ports": 0, "format": "unknown"}

    for i, upload in enumerate(files):
        if not upload.filename:
            continue
        content = (await upload.read()).decode("utf-8-sig", errors="replace")
        name = Path(upload.filename).stem
        sw = parse_switch_content(content, name=name)

        # Detect format hints from first file only
        reader = _csv.reader(io.StringIO(content))
        rows = list(reader)
        fmt = detect_format(rows[0]) if rows else "unknown"
        if i == 0:
            result["format"] = fmt

        sfp_labels = [p.label for p in sw.sfp_ports] if fmt == "meraki" else []
        stack_count = len(sw.stack_ports) if fmt == "meraki" else 2

        all_ports = sw.access_ports + sw.sfp_ports
        result["switches"].append({
            "name": name,
            "layout": {
                "port_order": "columns",
                "port_one_top": True,
                "stack_ports": stack_count,
                "sfp_ports": sfp_labels,
            },
            "ports": [
                {
                    "label": p.label,
                    "name": p.name,
                    "type": p.port_type,
                    "vlan": p.vlan,
                    "native_vlan": getattr(p, "native_vlan", ""),
                    "active": p.active,
                }
                for p in all_ports
            ],
        })

    return result


@app.post("/generate")
async def generate(req: GenerateRequest):
    """Generate a PNG from the editor state (JSON body)."""
    if not req.switches:
        return Response("No switches provided.", status_code=400)

    switches, labels = [], []
    for sw_in in req.switches:
        ports = [
            Port(
                label=p.label,
                port_type=p.port_type,
                vlan=p.vlan,
                name=p.name,
                active=p.active,
                native_vlan=p.native_vlan,
            )
            for p in sw_in.ports
        ]
        switches.append(Switch(name=sw_in.name, access_ports=ports))
        labels.append(sw_in.role)

    title = req.title or " / ".join(sw.name for sw in switches)
    opts_list = [
        RenderOptions(
            port_order=sw_in.layout.port_order,
            port_one_top=sw_in.layout.port_one_top,
            stack_ports=sw_in.layout.stack_ports,
            sfp_ports=sw_in.layout.sfp_ports,
        )
        for sw_in in req.switches
    ]

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tmp_path = Path(tf.name)
    try:
        render(switches, labels, title, str(tmp_path),
               options_per_switch=opts_list, color_map_override=req.vlan_colors)
        png_bytes = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    token = uuid.uuid4().hex
    _result_cache[token] = png_bytes
    if len(_result_cache) > 20:
        del _result_cache[next(iter(_result_cache))]

    return {"token": token}


@app.get("/result/{token}")
async def get_result(token: str):
    data = _result_cache.get(token)
    if not data:
        return Response("Result not found or expired.", status_code=404)
    return Response(content=data, media_type="image/png")


@app.get("/download/{token}")
async def download(token: str):
    data = _result_cache.get(token)
    if not data:
        return Response("Result not found or expired.", status_code=404)
    return Response(
        content=data,
        media_type="image/png",
        headers={"Content-Disposition": "attachment; filename=stack.png"},
    )


@app.get("/samples/{name}")
async def sample(name: str):
    allowed = {"meraki_export.csv", "simple.csv", "minimal.csv"}
    if name not in allowed:
        return Response("Not found.", status_code=404)
    data = (SAMPLES_DIR / name).read_bytes()
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}"},
    )
