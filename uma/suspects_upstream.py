"""Recalcula los sospechosos humanos en la cuenca de aporte completa de cada cuerpo de agua.

  python -m uma.suspects_upstream --project TU-PROYECTO --only poopo,concepcion

Usa la misma area que el clima (data/real/basins/<id>.geojson, de uma.upstream), asi una mina o un
desvio aguas arriba cuenta como sospechoso. Reemplaza en data/real/suspects.csv solo las filas de los
cuerpos de agua procesados. En cuencas grandes calcula a resolucion mas gruesa (SCALE_MULT).

Limite: MapBiomas Bolivia no cubre la parte de la cuenca fuera de Bolivia (por ejemplo el lado peruano
del Titicaca); Hansen, MODIS, luces y WorldPop si son globales.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import ee
import pandas as pd

from uma import gee_extract as gx

ROOT = Path(__file__).resolve().parent.parent


def basin_geometry(body_id):
    g = json.loads((ROOT / "data" / "real" / "basins" / f"{body_id}.geojson").read_text(encoding="utf-8"))["geometry"]
    if g["type"] == "GeometryCollection":  # quedarse solo con los poligonos
        polys = [x for x in g["geometries"] if x["type"] in ("Polygon", "MultiPolygon")]
        coords = []
        for x in polys:
            coords += [x["coordinates"]] if x["type"] == "Polygon" else x["coordinates"]
        g = {"type": "MultiPolygon", "coordinates": coords}
    return ee.Geometry(g, None, False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--only", required=True)
    ap.add_argument("--suspects", default="", help="solo estos sospechosos, ej. population")
    a = ap.parse_args(argv)
    pick = set(filter(None, a.suspects.split(",")))
    ee.Initialize(project=a.project)
    out = ROOT / "data" / "real"
    up = pd.read_csv(out / "basins.csv").set_index("body_id")
    for body_id in a.only.split(","):
        km2 = float(up.upstream_km2[body_id])
        gx.SCALE_MULT = 1 if km2 < 5000 else 3 if km2 < 50000 else 4
        basin = basin_geometry(body_id)
        gx._mb_cache.clear()
        rows = []
        print(f"== {body_id}: cuenca de aporte {km2:,.0f} km2, escala x{gx.SCALE_MULT}", flush=True)
        for name, fn in gx.SUSPECTS.items():
            if pick and name not in pick:
                continue
            print(f"   {name}", flush=True)
            try:
                d = fn(basin)
                v = d.set_index("year")["value"].astype(float).reindex(gx.YEARS)
                v = v.fillna(0) if name in gx.FLOW_SUSPECTS else v.ffill().bfill().fillna(0)
                d = v.reset_index()
                d.columns = ["year", "value"]
                d.insert(0, "body_id", body_id)
                d.insert(2, "suspect", name)
                rows.append(d)
            except Exception as e:
                print(f"   fallo {name}: {e}", flush=True)
        if rows:  # guardar despues de cada cuerpo de agua
            sus = pd.read_csv(out / "suspects.csv")
            done = {n for n in pd.concat(rows).suspect.unique()}
            if "area" not in sus:
                sus["area"] = "subcuenca_local"
            keep = sus[~((sus.body_id == body_id) & sus.suspect.isin(done) & (sus.area == "cuenca_aporte"))]
            for d in rows:
                d["area"] = "cuenca_aporte"
            new = pd.concat([keep] + rows, ignore_index=True)
            new.to_csv(out / "suspects.csv", index=False)


if __name__ == "__main__":
    main()
