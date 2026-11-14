"""Que hay alrededor de cada cuerpo de agua: mapa de cambios y lugares con nombre.

  python -m uma.context --project TU-PROYECTO            # todo
  python -m uma.context --project TU-PROYECTO --only poopo --skip-osm

Por cada cuerpo de agua, en una ventana mas amplia que la laguna (los alrededores), guarda en
data/real/context/:
  <id>_antes.png, <id>_despues.png   Landsat de epoca seca del ano inicial y final
  <id>_cambios.png                   capa transparente con lo que aparecio entre ambos anos:
                                     mineria nueva, ciudad nueva, cultivos nuevos, pasto nuevo,
                                     bosque perdido (MapBiomas Bolivia + Hansen); contorno de la laguna
  <id>_lugares.json                  minas, industrias, ciudades, represas y canales de OpenStreetMap
  <id>_meta.json                     ventana, anos, hectareas de cada cambio
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

import ee
import pandas as pd

from uma.gee_extract import DS, HA, MAPBIOMAS, landsat_col, landsat_vis, retry

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "real" / "context"
YEAR_A, YEAR_B = 1990, 2023  # MapBiomas Bolivia llega a 2023; las imagenes usan 3 anos centrados

# capa de cambios: clave -> (color, etiqueta)
CHANGES = {
    "mining": ("ff1744", "Mineria nueva"),
    "urban": ("d500f9", "Ciudad nueva"),
    "agri": ("ffd600", "Cultivos nuevos"),
    "pasture": ("ff9100", "Pasto nuevo"),
    "forest_loss": ("8d6e63", "Bosque perdido"),
}
MB = {"mining": [30], "urban": [24], "agri": [18, 19, 20, 39, 40, 41, 62], "pasture": [15]}

OSM_TAGS = {
    "Mina o cantera": ['nwr["landuse"="quarry"]', 'nwr["industrial"="mine"]', 'nwr["man_made"="mineshaft"]',
                       'nwr["landuse"="mining"]', 'nwr["resource"]'],
    "Industria": ['nwr["landuse"="industrial"]["name"]', 'nwr["man_made"="works"]'],
    "Ciudad o pueblo": ['node["place"~"city|town"]'],
    "Represa o canal": ['nwr["waterway"~"dam|weir"]', 'way["waterway"="canal"]["name"]', 'nwr["water"="reservoir"]'],
}
OVERPASS = "https://overpass-api.de/api/interpreter"


def landsat_3y(year, region):
    """Mediana de epoca seca de tres anos (year-1 a year+1): menos nubes y bordes de escena."""
    col = landsat_col(year - 1, region).merge(landsat_col(year, region)).merge(landsat_col(year + 1, region))
    return col.median()


MAX_WINDOW_KM = 60.0


def window(lat, lon, radius_km):
    """Ventana de alrededores: 2.5 veces el radio de la laguna, entre 20 y MAX_WINDOW_KM (mas grande no se genera)."""
    r = min(MAX_WINDOW_KM, max(20.0, 2.5 * radius_km))
    return ee.Geometry.Point([lon, lat]).buffer(r * 1000).bounds(), r


def change_image(region, lake):
    mb = ee.Image(MAPBIOMAS)
    a, b = mb.select(f"classification_{YEAR_A}"), mb.select(f"classification_{YEAR_B}")
    layers, masks = [], {}
    for k, codes in MB.items():
        new = b.remap(codes, [1] * len(codes), 0).eq(1).And(a.remap(codes, [1] * len(codes), 0).eq(0))
        masks[k] = new
    loss = ee.Image(DS["hansen"]).select("lossyear")
    masks["forest_loss"] = loss.gt(0).And(loss.lte(YEAR_B - 2000))
    order = ["forest_loss", "pasture", "agri", "urban", "mining"]  # lo mas importante se pinta encima
    img = None  # sin base: lo que no cambio queda transparente
    for k in order:
        layer = masks[k].selfMask().visualize(palette=[CHANGES[k][0]])
        img = layer if img is None else img.blend(layer)
    outline = ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(lake)]), 1, 3).visualize(palette=["ffffff"])
    img = img.blend(outline)
    stats = {}
    for k in order:
        v = retry(lambda: HA().updateMask(masks[k]).reduceRegion(ee.Reducer.sum(), region, 60, maxPixels=1e11,
                                                                 tileScale=4).get("area").getInfo())
        stats[k] = round(v or 0)
    return img, stats


def download(url, path):
    for i in range(4):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                path.write_bytes(r.read())
            return
        except OSError:
            if i == 3:
                raise
            time.sleep(20)


def osm_places(lat, lon, r_km):
    dlat = r_km / 111
    dlon = r_km / (111 * math.cos(math.radians(lat)))
    bbox = f"{lat - dlat},{lon - dlon},{lat + dlat},{lon + dlon}"
    out = []
    for kind, qs in OSM_TAGS.items():
        q = "[out:json][timeout:60];(" + "".join(f"{x}({bbox});" for x in qs) + ");out center tags 200;"
        data = urllib.parse.urlencode({"data": q}).encode()
        req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "uma-hackathon/0.1"})
        for i in range(3):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    els = json.load(r)["elements"]
                break
            except OSError:
                if i == 2:
                    els = []
                time.sleep(15)
        for e in els:
            c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
            if c.get("lat") is None:
                continue
            t = e.get("tags", {})
            d = 111 * math.hypot(c["lat"] - lat, (c["lon"] - lon) * math.cos(math.radians(lat)))
            out.append({"kind": kind, "name": t.get("name") or t.get("operator") or "",
                        "detail": t.get("resource") or t.get("product") or t.get("industrial") or t.get("place") or "",
                        "lat": round(c["lat"], 5), "lon": round(c["lon"], 5), "dist_km": round(d, 1),
                        "osm": f"https://www.openstreetmap.org/{e['type']}/{e['id']}"})
        time.sleep(2)  # cortesia con el servidor publico de Overpass
    df = pd.DataFrame(out)
    if df.empty:
        return []
    df = df.sort_values(["kind", "dist_km"]).drop_duplicates(["kind", "name", "lat"])
    return df.to_dict("records")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-osm", action="store_true")
    ap.add_argument("--max-window-km", type=float, default=60.0)
    a = ap.parse_args(argv)
    global MAX_WINDOW_KM
    MAX_WINDOW_KM = a.max_window_km
    ee.Initialize(project=a.project)
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = pd.read_csv(ROOT / "config" / "bodies.csv")
    if a.only:
        cfg = cfg[cfg.body_id.isin(a.only.split(","))]
    for _, b in cfg.iterrows():
        try:
            one(b, a.skip_osm)
        except Exception as e:  # una laguna fallida no detiene las demas
            print(f"   fallo {b.body_id}: {e}", flush=True)


def one(b, skip_osm):
    if True:
        print(f"== {b['name']}", flush=True)
        region, r_km = window(b.lat, b.lon, b.radius_km)
        lake = ee.Geometry.Point([b.lon, b.lat]).buffer(b.radius_km * 1000)
        params = {"region": region, "dimensions": 1000, "format": "png"}
        for tag, y in (("antes", YEAR_A), ("despues", YEAR_B)):
            p = OUT / f"{b.body_id}_{tag}.png"
            if not p.exists():
                download(landsat_vis(landsat_3y(y, region)).getThumbURL(params), p)
        img, stats = change_image(region, lake)
        download(img.getThumbURL(params), OUT / f"{b.body_id}_cambios.png")
        print("   cambios (ha):", stats, flush=True)
        meta = {"years": [YEAR_A, YEAR_B], "window_km": r_km, "changes_ha": stats,
                "legend": {k: {"color": "#" + c, "label": l} for k, (c, l) in CHANGES.items()}}
        (OUT / f"{b.body_id}_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        if not skip_osm:
            places = osm_places(b.lat, b.lon, r_km)
            (OUT / f"{b.body_id}_lugares.json").write_text(json.dumps(places, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
            print(f"   OpenStreetMap: {len(places)} lugares", flush=True)


if __name__ == "__main__":
    main()
