"""Mapa 3D (relieve real) y comparador antes/despues para Uma."""
from __future__ import annotations

import base64
import io
import math
import os
import urllib.request
from functools import lru_cache
from pathlib import Path

import pydeck as pdk

TERRAIN = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"  # AWS Terrain Tiles, sin clave
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
PLACE_COLORS = {"Mina o cantera": [255, 23, 68], "Industria": [255, 145, 0],
                "Ciudad o pueblo": [213, 0, 249], "Represa o canal": [0, 229, 255]}
DECODER = {"rScaler": 256, "gScaler": 1, "bScaler": 1 / 256, "offset": -32768}


@lru_cache(maxsize=256)
def elevation(lat: float, lon: float, z: int = 10) -> float:
    """Altura del terreno en metros (para que las columnas no queden enterradas en el Altiplano)."""
    try:
        from PIL import Image
        n = 2 ** z
        xf = (lon + 180) / 360 * n
        yf = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
        url = TERRAIN.format(z=z, x=int(xf), y=int(yf))
        with urllib.request.urlopen(url, timeout=10) as r:
            img = Image.open(io.BytesIO(r.read())).convert("RGB")
        px = img.getpixel((int((xf % 1) * 256), int((yf % 1) * 256)))
        return px[0] * 256 + px[1] + px[2] / 256 - 32768
    except Exception:
        return 0.0


# ------------------------------------------------------------------ Earth Engine en vivo
_EE_OK: bool | None = None


def ee_ready() -> bool:
    global _EE_OK
    if _EE_OK is None:
        try:
            import ee
            import json
            cfg = Path(__file__).resolve().parent.parent / "config" / "settings.json"
            project = os.environ.get("UMA_GEE_PROJECT") or (
                json.loads(cfg.read_text(encoding="utf-8")).get("gee_project") if cfg.exists() else None)
            ee.Initialize(project=project)
            ee.Number(1).getInfo()  # confirma que la conexion funciona
            _EE_OK = True
        except Exception:
            _EE_OK = False
    return _EE_OK


@lru_cache(maxsize=64)
def live_texture(year: int, with_water: bool, fires: bool = False, day: str = "") -> str | None:
    """URL de teselas de Earth Engine: Landsat de epoca seca del ano elegido, con el agua JRC encima.

    fires: focos de calor NASA FIRMS de los ultimos 7 dias (casi tiempo real). `day` solo invalida la cache.
    """
    if not ee_ready():
        return None
    import ee
    from uma.gee_extract import DS, landsat_dry, landsat_vis
    bolivia = ee.Geometry.Rectangle([-70.5, -23.5, -57.0, -9.5])
    img = landsat_vis(landsat_dry(year, bolivia))
    if with_water and year <= 2021:
        wc = ee.ImageCollection(DS["jrc_yearly"]).filter(ee.Filter.eq("year", year)).first().select("waterClass")
        img = img.blend(wc.gte(2).selfMask().visualize(palette=["1e88e5"], opacity=0.55))
    if fires:
        now = ee.Date(day or ee.Date(0))
        firms = ee.ImageCollection("FIRMS").filterDate(now.advance(-7, "day"), now.advance(1, "day")).select("T21").max()
        img = img.blend(firms.gt(0).selfMask().focalMax(2).visualize(palette=["ff3d00"]))
    return img.getMapId()["tile_fetcher"].url_format


# ------------------------------------------------------------------ deck
def build_deck(rows: list[dict], selected: dict | None, texture: str, places: list | None = None) -> pdk.Deck:
    """rows: dicts con name, lat, lon, state, color, change, loss (perdida %, >= 0)."""
    for r in rows:
        r["z"] = elevation(round(r["lat"], 3), round(r["lon"], 3))
    terrain = pdk.Layer("TerrainLayer", id="relieve", elevation_decoder=DECODER, elevation_data=TERRAIN,
                        texture=texture, max_zoom=13, strategy="no-overlap")
    columns = pdk.Layer("ColumnLayer", id="cuerpos", data=rows, get_position="[lon, lat, z]",
                        get_elevation="loss", elevation_scale=12 if selected else 600,
                        radius=250 if selected else 9000,
                        get_fill_color="color", pickable=True, auto_highlight=True, extruded=True)
    layers = [terrain, columns]
    if selected and places:
        # mismos campos que las columnas para que el tooltip sirva a ambas capas
        pts = [dict(pl, z=elevation(round(pl["lat"], 3), round(pl["lon"], 3)) + 150,
                    color=PLACE_COLORS.get(pl["kind"], [255, 255, 255]),
                    name=pl["name"] or "(sin nombre)", state=pl["kind"], change=f"a {pl['dist_km']} km")
                for pl in places[:30]]
        layers.append(pdk.Layer("ScatterplotLayer", id="lugares", data=pts, get_position="[lon, lat, z]",
                                get_fill_color="color", get_radius=350, radius_min_pixels=5, pickable=True,
                                stroked=True, get_line_color=[0, 0, 0], line_width_min_pixels=1))
        layers.append(pdk.Layer("TextLayer", id="nombres", data=[x for x in pts if x["name"]],
                                get_position="[lon, lat, z]", get_text="name", get_size=13, get_color=[255, 255, 255],
                                get_pixel_offset=[0, -14], background=True, get_background_color=[0, 0, 0, 160]))
    if selected:
        view = pdk.ViewState(latitude=selected["lat"], longitude=selected["lon"], zoom=9.3, pitch=60, bearing=-20)
    else:
        view = pdk.ViewState(latitude=-17.2, longitude=-65.0, zoom=5.2, pitch=45, bearing=0)
    return pdk.Deck(layers=layers, initial_view_state=view, map_style=None,
                    tooltip={"text": "{name}\n{state} · {change}"})


# ------------------------------------------------------------------ antes / despues
def _b64(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def before_after_html(before: Path, after: Path, label_a: str, label_b: str,
                      water_a: Path | None = None, water_b: Path | None = None, height: int = 520,
                      changes: Path | None = None, legend: dict | None = None) -> str:
    """Comparador con deslizador: a la izquierda 'antes', a la derecha 'despues'.

    water_*: mascara de agua opcional por lado. changes: capa transparente de lo que aparecio
    (se muestra sobre el 'despues'), con su leyenda {clave: {color, label, ha}}.
    """
    def layer(img, water, extra=""):
        w = f"<img src='{_b64(water)}' class='w'>" if water and water.exists() else ""
        return f"<img src='{_b64(img)}'>{w}{extra}"
    chg = f"<img src='{_b64(changes)}' class='c'>" if changes and changes.exists() else ""
    leg = ""
    if chg and legend:
        items = "".join(f"<span><i style='background:{v['color']}'></i>{v['label']}"
                        f"{' · ' + format(v['ha'], ',') + ' ha' if v.get('ha') else ''}</span>"
                        for v in legend.values())
        leg = (f"<label class='tog'><input type='checkbox' id='chkc' checked> Mostrar que aparecio alrededor</label>"
               f"<div class='leg'>{items}<span><i style='background:#00e5ff'></i>Cuerpo de agua</span></div>")
    return f"""
<style>
.ba{{position:relative;width:100%;height:{height}px;overflow:hidden;border-radius:8px;background:#111;
     font-family:sans-serif;user-select:none}}
.ba .pane{{position:absolute;inset:0}}
.ba img{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}}
.ba img.w{{opacity:0;transition:opacity .2s}}
.ba.showw img.w{{opacity:.6}}
.ba img.c{{opacity:0;transition:opacity .2s}}
.ba.showc img.c{{opacity:.85}}
.leg{{font-family:sans-serif;color:#ddd;font-size:13px;display:flex;flex-wrap:wrap;gap:12px;margin-top:4px}}
.leg i{{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:5px;vertical-align:-1px}}
.ba .after{{clip-path:inset(0 0 0 50%)}}
.ba .bar{{position:absolute;top:0;bottom:0;left:50%;width:3px;background:#fff;box-shadow:0 0 6px #000}}
.ba .tag{{position:absolute;top:10px;padding:4px 10px;border-radius:4px;background:rgba(0,0,0,.65);color:#fff;font-size:14px}}
.ba input[type=range]{{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:ew-resize;margin:0}}
.tog{{font-family:sans-serif;color:#ccc;font-size:13px;margin-top:6px}}
</style>
<div class="ba{' showc' if chg else ''}" id="ba">
  <div class="pane">{layer(before, water_a)}</div>
  <div class="pane after" id="after">{layer(after, water_b, chg)}</div>
  <div class="bar" id="bar"></div>
  <div class="tag" style="left:10px">Antes · {label_a}</div>
  <div class="tag" style="right:10px">Despues · {label_b}</div>
  <input type="range" min="0" max="100" value="50" id="rng">
</div>
{'' if chg else '<label class="tog"><input type="checkbox" id="chk"> Marcar el agua detectada (JRC)</label>'}
{leg}
<script>
const r=document.getElementById('rng'),a=document.getElementById('after'),b=document.getElementById('bar');
r.addEventListener('input',()=>{{a.style.clipPath=`inset(0 0 0 ${{r.value}}%)`;b.style.left=r.value+'%';}});
const c1=document.getElementById('chk'); if(c1) c1.addEventListener('change',e=>document.getElementById('ba').classList.toggle('showw',e.target.checked));
const c2=document.getElementById('chkc'); if(c2) c2.addEventListener('change',e=>document.getElementById('ba').classList.toggle('showc',e.target.checked));
</script>"""
