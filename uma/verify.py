"""Verificacion cruzada: compara los datos del sistema con datasets independientes que el motor no usa.

  python -m uma.verify --project TU-PROYECTO

1. Agua de cada laguna: Landsat MNDWI (lo que usa el motor) contra MapBiomas Agua (otro equipo, otro metodo),
   en el mismo circulo y los mismos anos.
2. Lluvia de cada cuenca: NASA POWER (lo que usa el motor) contra CHIRPS (estaciones + satelite).
3. Lectura de MapBiomas Agua: superficie de agua de toda Bolivia por ano, para compararla con la cifra que
   publica MapBiomas (1.4 millones de ha en 2024, 20% bajo la media 1985-2024).
Salida: data/real/verificacion.json y un resumen en pantalla.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import ee
import numpy as np
import pandas as pd

from uma.gee_extract import HA, MB_WATER, retry
from uma.suspects_upstream import basin_geometry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real"
YEARS = list(range(1985, 2025))
MB_WATER_ALL = "projects/mapbiomas-public/assets/bolivia/water/collection4/mapbiomas_bolivia_collection4_water_v1"


def mapbiomas_water(geom, scale=30):
    """Agua natural (clases 11-14) por ano, todas las bandas en una sola consulta."""
    img = ee.Image(MB_WATER)
    bands = [HA().updateMask(img.select(f"classification_{y}").gte(11).And(img.select(f"classification_{y}").lte(14)))
             .rename(f"y{y}") for y in YEARS]
    v = retry(lambda: ee.Image.cat(bands).reduceRegion(ee.Reducer.sum(), geom, scale, maxPixels=1e11,
                                                       tileScale=8).getInfo())
    return pd.Series({y: v.get(f"y{y}") or 0.0 for y in YEARS})


def chirps(geom):
    col = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
    bands = [col.filterDate(f"{y}-01-01", f"{y + 1}-01-01").sum().rename(f"y{y}") for y in YEARS]
    v = retry(lambda: ee.Image.cat(bands).reduceRegion(ee.Reducer.mean(), geom, 5566, maxPixels=1e10,
                                                       tileScale=4).getInfo())
    return pd.Series({y: v.get(f"y{y}") for y in YEARS})


def bolivia_total():
    img = ee.Image(MB_WATER_ALL)
    bol = ee.FeatureCollection("FAO/GAUL/2015/level0").filter(ee.Filter.eq("ADM0_NAME", "Bolivia")).geometry()
    bands = [HA().updateMask(img.select(f"classification_{y}").eq(1)).rename(f"y{y}") for y in YEARS]
    v = retry(lambda: ee.Image.cat(bands).reduceRegion(ee.Reducer.sum(), bol, 300, maxPixels=1e11,
                                                       tileScale=16).getInfo())
    return pd.Series({y: v.get(f"y{y}") or 0.0 for y in YEARS})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    cfg = pd.read_csv(ROOT / "config" / "bodies.csv").set_index("body_id")
    s = pd.read_csv(DATA / "series.csv")
    out = {"lagunas": {}, "bolivia": {}}
    for bid, b in cfg.iterrows():
        d = s[s.body_id == bid].set_index("year")
        if d.empty:
            continue
        circle = ee.Geometry.Point([b.lon, b.lat]).buffer(float(b.radius_km) * 1000)
        mb = mapbiomas_water(circle)
        both = pd.DataFrame({"landsat": d.water_ha, "mapbiomas": mb}).dropna()
        r_water = float(both.landsat.corr(both.mapbiomas))
        ratio = float((both.landsat / both.mapbiomas.replace(0, np.nan)).median())
        rec = {"r_agua_landsat_mapbiomas": round(r_water, 2), "landsat_sobre_mapbiomas": round(ratio, 2),
               "agua_landsat": {int(k): round(v) for k, v in d.water_ha.items()},
               "agua_mapbiomas": {int(k): round(v) for k, v in mb.items()}}
        if (DATA / "basins" / f"{bid}.geojson").exists():
            ch = chirps(basin_geometry(bid))
            pw = pd.DataFrame({"power": d.precip_mm, "chirps": ch}).dropna()
            rec["r_lluvia_power_chirps"] = round(float(pw.power.corr(pw.chirps)), 2)
            rec["lluvia_media_power_mm"] = round(float(pw.power.mean()))
            rec["lluvia_media_chirps_mm"] = round(float(pw.chirps.mean()))
        out["lagunas"][bid] = rec
        print(bid, {k: v for k, v in rec.items() if not k.startswith("agua_")}, flush=True)
    tot = bolivia_total()
    out["bolivia"] = {"agua_ha_por_ano": {int(k): round(v) for k, v in tot.items()},
                      "agua_2024_ha": round(float(tot[2024])), "media_1985_2024_ha": round(float(tot.mean())),
                      "2024_vs_media_pct": round(float(100 * (tot[2024] / tot.mean() - 1)), 1),
                      "anos_bajo_media_desde_2009": int((tot.loc[2009:2024] < tot.mean()).sum())}
    print("Bolivia:", {k: v for k, v in out["bolivia"].items() if k != "agua_ha_por_ano"}, flush=True)
    (DATA / "verificacion.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
