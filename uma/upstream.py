"""Cuenca de aporte completa de cada cuerpo de agua (todo lo que drena hacia el, aguas arriba).

  python -m uma.upstream --project TU-PROYECTO

Usa HydroBASINS nivel 8: toma las subcuencas que tocan el cuerpo de agua y sube por NEXT_DOWN
hasta juntar todas las que drenan hacia ellas. Guarda data/real/basins/<body_id>.geojson y un
resumen en data/real/basins.csv (area, y si el cuerpo de agua esta aguas abajo de otro de la lista).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import ee
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
HB = "WWF/HydroSHEDS/v1/Basins/hybas_8"


def upstream_ids(seed_ids: set[int], main_bas: set[int]) -> set[int]:
    fc = ee.FeatureCollection(HB).filter(ee.Filter.inList("MAIN_BAS", list(main_bas)))
    props = fc.reduceColumns(ee.Reducer.toList(2), ["HYBAS_ID", "NEXT_DOWN"]).get("list").getInfo()
    parents = defaultdict(list)
    for hid, nd in props:
        parents[int(nd)].append(int(hid))
    out, stack = set(seed_ids), list(seed_ids)
    while stack:
        for p in parents.get(stack.pop(), []):
            if p not in out:
                out.add(p)
                stack.append(p)
    return out


def body_basin(lat, lon, radius_km):
    area = ee.Geometry.Point([lon, lat]).buffer(radius_km * 1000)
    seeds = ee.FeatureCollection(HB).filterBounds(area)
    info = seeds.reduceColumns(ee.Reducer.toList(2), ["HYBAS_ID", "MAIN_BAS"]).get("list").getInfo()
    ids = upstream_ids({int(h) for h, _ in info}, {int(m) for _, m in info})
    geom = ee.FeatureCollection(HB).filter(ee.Filter.inList("HYBAS_ID", list(ids))).geometry(1000).dissolve(1000)
    return ids, geom


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    out = ROOT / "data" / "real" / "basins"
    out.mkdir(parents=True, exist_ok=True)
    cfg = pd.read_csv(ROOT / "config" / "bodies.csv")
    rows, idsets = [], {}
    for _, b in cfg.iterrows():
        ids, geom = body_basin(b.lat, b.lon, b.radius_km)
        simple = geom.simplify(2000)
        gj = simple.getInfo()
        km2 = geom.area(1000).divide(1e6).getInfo()
        (out / f"{b.body_id}.geojson").write_text(json.dumps({"type": "Feature", "properties": {"body_id": b.body_id,
                                                  "area_km2": round(km2)}, "geometry": gj}), encoding="utf-8")
        idsets[b.body_id] = ids
        rows.append({"body_id": b.body_id, "upstream_km2": round(km2), "n_subbasins": len(ids)})
        print(f"{b['name']}: cuenca de aporte {km2:,.0f} km2 ({len(ids)} subcuencas)")
    # upstream_bodies: cuerpos de agua de la lista que drenan hacia este (su cuenca esta contenida en la de este)
    for r in rows:
        r["upstream_bodies"] = ",".join(o for o, s in idsets.items()
                                      if o != r["body_id"] and s < idsets[r["body_id"]] and len(s) > 0) or ""
    pd.DataFrame(rows).to_csv(ROOT / "data" / "real" / "basins.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
