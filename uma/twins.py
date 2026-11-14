"""Busca gemelas de control para cada cuerpo de agua.

  python -m uma.twins --project TU-PROYECTO --targets poopo,uru_uru,concepcion,titicaca_menor

Una buena gemela tiene el mismo clima y poca presion humana, y NO esta en la misma cadena de drenaje
(si lo esta, hereda los cambios del otro, como Coipasa que recibe el agua del Poopo).
Importante: la gemela NO se elige segun si perdio o gano agua; eso sesgaria la prueba.

Criterios:
  - agua permanente (JRC occurrence >= 25%) de al menos 300 ha, a menos de ~3 grados
  - otra cuenca principal de HydroBASINS (MAIN_BAS distinto)
  - presion humana baja: Global Human Modification (gHM, 0 a 1) en 10 km alrededor
  - altura parecida (NASADEM) y lluvia correlacionada (NASA POWER, 1985-2024)
Salida: data/real/twin_candidates.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import ee
import numpy as np
import pandas as pd

from uma.nasa_power import point_monthly

ROOT = Path(__file__).resolve().parent.parent


def candidates(lat, lon, box_deg=3.0, limit=60, min_occ=25):
    box = ee.Geometry.Rectangle([lon - box_deg, lat - box_deg, lon + box_deg, lat + box_deg])
    occ = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence")
    vec = occ.gte(min_occ).selfMask().reduceToVectors(geometry=box, scale=300, geometryType="polygon",
                                                 eightConnected=True, maxPixels=1e10, bestEffort=True)
    vec = vec.map(lambda f: f.set("ha", f.geometry().area(300).divide(1e4)))
    vec = vec.filter(ee.Filter.rangeContains("ha", 300, 300000)).sort("ha", False).limit(limit)
    ring = vec.map(lambda f: f.setGeometry(f.geometry().buffer(10000, 300)))
    ghm = ee.ImageCollection("CSP/HM/GlobalHumanModification").first().select("gHM")
    dem = ee.Image("NASA/NASADEM_HGT/001").select("elevation")
    stats = ghm.addBands(dem).reduceRegions(ring, ee.Reducer.mean(), 300)
    basins = ee.FeatureCollection("WWF/HydroSHEDS/v1/Basins/hybas_8")
    cent = stats.map(lambda f: f.setGeometry(f.geometry().centroid(300)))
    joined = ee.Join.saveFirst("basin").apply(cent, basins, ee.Filter.intersects(".geo", None, ".geo"))
    joined = joined.map(lambda f: f.set("main_bas", ee.Feature(f.get("basin")).get("MAIN_BAS")).set("basin", None))
    info = joined.getInfo()["features"]
    rows = []
    for f in info:
        p, (x, y) = f["properties"], f["geometry"]["coordinates"]
        rows.append({"lat": round(y, 3), "lon": round(x, 3), "ha": round(p["ha"]), "ghm": p.get("gHM"),
                     "elev_m": p.get("elevation"), "main_bas": p.get("main_bas")})
    return pd.DataFrame(rows)


def target_info(lat, lon):
    pt = ee.Geometry.Point([lon, lat])
    b = ee.FeatureCollection("WWF/HydroSHEDS/v1/Basins/hybas_8").filterBounds(pt).first()
    elev = ee.Image("NASA/NASADEM_HGT/001").reduceRegion(ee.Reducer.mean(), pt.buffer(3000), 90).get("elevation")
    return ee.Dictionary({"main_bas": b.get("MAIN_BAS"), "elev": elev}).getInfo()


def annual_precip(lat, lon):
    m = point_monthly(round(lat, 2), round(lon, 2))
    return m.groupby("year")["precip_mm"].sum()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--targets", default="poopo,uru_uru,concepcion,titicaca_menor")
    ap.add_argument("--top", type=int, default=6)
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    cfg = pd.read_csv(ROOT / "config" / "bodies.csv").set_index("body_id")
    out = []
    for t in a.targets.split(","):
        b = cfg.loc[t]
        ti = target_info(b.lat, b.lon)
        c = candidates(b.lat, b.lon)
        c = c[(c.main_bas != ti["main_bas"]) & c.ghm.notna()].copy()
        c["dist_km"] = 111 * np.hypot(c.lat - b.lat, (c.lon - b.lon) * np.cos(np.radians(b.lat)))
        c["elev_diff_m"] = (c.elev_m - ti["elev"]).abs()
        c["score"] = c.ghm * 10 + c.elev_diff_m / 500 + c.dist_km / 300
        c = c.sort_values("score").head(a.top)
        tp = annual_precip(b.lat, b.lon)
        c["precip_corr"] = [round(tp.corr(annual_precip(r.lat, r.lon)), 2) for r in c.itertuples()]
        c.insert(0, "target", t)
        out.append(c)
        print(f"\n== {b['name']} (altura {ti['elev']:.0f} m)")
        print(c[["lat", "lon", "ha", "ghm", "elev_m", "dist_km", "precip_corr", "score"]].round(2).to_string(index=False))
    pd.concat(out).to_csv(ROOT / "data" / "real" / "twin_candidates.csv", index=False)


if __name__ == "__main__":
    main()
