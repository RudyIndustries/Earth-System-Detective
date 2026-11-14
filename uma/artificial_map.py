"""Puntos de agua artificial de Bolivia para el mapa (represas, estanques y pozas mineras).

  python -m uma.artificial_map --project TU-PROYECTO --year 2024

Las pozas y represas son pequenas y desaparecen al alejar el mapa; por eso se convierten en puntos con su
superficie y su tipo. Fuente: MapBiomas Agua Bolivia coleccion 4 (22 represa, 23 otra artificial, 24 poza
minera). Salida: data/national/agua_artificial.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import ee

from uma.gee_extract import MB_WATER, retry

ROOT = Path(__file__).resolve().parent.parent
TYPES = {22: "Represa o reservorio", 23: "Estanque u otra agua artificial", 24: "Poza minera", 21: "Represa o reservorio"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--max", type=int, default=4000)
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    cls = ee.Image(MB_WATER).select(f"classification_{a.year}")
    art = cls.updateMask(cls.gte(21).And(cls.lte(24)))
    bol = (ee.FeatureCollection("FAO/GAUL/2015/level0").filter(ee.Filter.eq("ADM0_NAME", "Bolivia")).geometry())
    vec = art.reduceToVectors(geometry=bol, scale=60, geometryType="centroid", eightConnected=True,
                              labelProperty="tipo", reducer=ee.Reducer.mode(), maxPixels=1e11, bestEffort=True,
                              tileScale=16)
    # area de cada mancha: cuantos pixeles de 60 m tiene
    count = art.gt(0).rename("n")
    vec2 = art.addBands(count).reduceToVectors(geometry=bol, scale=60, geometryType="centroid", eightConnected=True,
                                               labelProperty="tipo", reducer=ee.Reducer.count(), maxPixels=1e11,
                                               bestEffort=True, tileScale=16)
    vec2 = vec2.sort("count", False).limit(a.max)
    info = retry(lambda: vec2.getInfo())
    pts = []
    for f in info["features"]:
        lon, lat = f["geometry"]["coordinates"]
        t = int(f["properties"]["tipo"])
        ha = f["properties"]["count"] * 0.36
        pts.append({"lat": round(lat, 5), "lon": round(lon, 5), "ha": round(ha, 1), "code": t,
                    "tipo": TYPES.get(t, "Agua artificial")})
    out = ROOT / "data" / "national"
    out.mkdir(parents=True, exist_ok=True)
    (out / "agua_artificial.json").write_text(json.dumps({"year": a.year, "points": pts}, ensure_ascii=False),
                                              encoding="utf-8")
    from collections import Counter
    print(len(pts), "manchas de agua artificial", dict(Counter(p["tipo"] for p in pts)),
          "superficie total", round(sum(p["ha"] for p in pts)), "ha")


if __name__ == "__main__":
    main()
