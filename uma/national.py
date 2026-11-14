"""Barrido nacional: diagnostico rapido de todas las lagunas de Bolivia con el mismo motor.

  python -m uma.national --project TU-PROYECTO            # todo (se puede cortar y retomar)
  python -m uma.national --project TU-PROYECTO --max 300  # cuantas lagunas como maximo

Pasos (cada uno guarda su resultado en data/national/ y se salta si ya existe):
  1. lagos.geojson     lagunas: agua natural de MapBiomas Agua presente >= 25% de los anos, >= 100 ha,
                       y forma compacta (los rios, alargados, se descartan)
  2. agua.csv          agua natural por ano 1985-2024 en cada laguna (MapBiomas Agua, todas a la vez)
  3. presion.csv       uso humano del suelo por ano en un anillo de 5 km (MapBiomas Bolivia) y desmonte (Hansen)
  4. clima.csv         NASA POWER por laguna (celdas de 0.5 grados compartidas)
  5. results.json      motor de atribucion; la gemela es un control regional sintetico: la mediana de las
                       lagunas con poca presion humana de la misma region (celda de 3 grados)

Es un diagnostico rapido: sin cuenca de aporte ni sospechosos detallados. Sirve para encontrar donde
mirar con el analisis completo.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import ee
import numpy as np
import pandas as pd

from uma import engine
from uma.gee_extract import HA, MAPBIOMAS, MB_WATER, retry
from uma.nasa_power import point_monthly

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "national"
BOLIVIA = [-69.7, -22.95, -57.4, -9.6]
YEARS = list(range(1985, 2025))
NATURAL = [11, 12, 13, 14]
ANTHROPIC = [9, 15, 18, 19, 20, 21, 24, 30, 31, 39, 40, 41, 62]


def country():
    return (ee.FeatureCollection("FAO/GAUL/2015/level0").filter(ee.Filter.eq("ADM0_NAME", "Bolivia"))
            .geometry())


def detect(max_n: int) -> pd.DataFrame:
    f = OUT / "lagos.geojson"
    if f.exists():
        return pd.DataFrame([dict(x["properties"]) for x in json.loads(f.read_text(encoding="utf-8"))["features"]])
    print("1) detectando lagunas", flush=True)
    wb = ee.Image(MB_WATER)
    nat = ee.ImageCollection([wb.select(f"classification_{y}").remap(NATURAL, [1] * len(NATURAL), 0)
                              for y in YEARS]).sum().divide(len(YEARS))
    mask = nat.gte(0.25).selfMask().clip(country())
    vec = mask.reduceToVectors(geometry=ee.Geometry.Rectangle(BOLIVIA), scale=250, geometryType="polygon",
                               eightConnected=False, maxPixels=1e10, bestEffort=True, tileScale=8)

    def props(ft):
        g = ft.geometry()
        a = g.area(250)
        p = g.perimeter(250)
        c = g.centroid(250).coordinates()
        return ft.set({"ha": a.divide(1e4), "compact": a.multiply(4 * math.pi).divide(p.pow(2)),
                       "lon": c.get(0), "lat": c.get(1)})
    vec = vec.map(props).filter(ee.Filter.gte("ha", 100)).filter(ee.Filter.gte("compact", 0.05))
    vec = vec.sort("ha", False).limit(max_n)
    info = retry(lambda: vec.getInfo())
    feats = []
    for i, x in enumerate(info["features"]):
        p = x["properties"]
        props_ = {"lake_id": f"L{i:04d}", "ha": round(p["ha"]), "compact": round(p["compact"], 3),
                  "lat": round(p["lat"], 4), "lon": round(p["lon"], 4)}
        feats.append({"type": "Feature", "properties": props_, "geometry": x["geometry"]})
    OUT.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    print(f"   {len(feats)} lagunas", flush=True)
    return pd.DataFrame([x["properties"] for x in feats])


def lakes_fc(buffer_m=0):
    gj = json.loads((OUT / "lagos.geojson").read_text(encoding="utf-8"))
    fs = []
    for x in gj["features"]:
        g = ee.Geometry(x["geometry"])
        if buffer_m:
            g = g.buffer(buffer_m, 250)
        fs.append(ee.Feature(g, {"lake_id": x["properties"]["lake_id"]}))
    return ee.FeatureCollection(fs)


def per_year(name: str, image_for_year, fc, scale) -> pd.DataFrame:
    f = OUT / f"{name}.csv"
    done = pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["lake_id", "year", "value"])
    for y in YEARS:
        if y in set(done.year):
            continue
        img = image_for_year(y).rename("value")
        res = retry(lambda: img.reduceRegions(fc, ee.Reducer.sum(), scale, tileScale=8).getInfo())
        rows = [{"lake_id": x["properties"]["lake_id"], "year": y, "value": x["properties"].get("value") or 0.0}
                for x in res["features"]]
        done = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
        done.to_csv(f, index=False)
        print(f"   {name} {y}", flush=True)
    return done


def climate(lakes: pd.DataFrame) -> pd.DataFrame:
    f = OUT / "clima.csv"
    if f.exists():
        return pd.read_csv(f)
    print("4) clima NASA POWER", flush=True)
    rows = []
    for r in lakes.itertuples():
        la, lo = round(r.lat * 2) / 2, round(r.lon * 2) / 2  # celda de 0.5 grados compartida
        m = point_monthly(la, lo)
        full = m.groupby("year").filter(lambda g: len(g) == 12)
        a = full.groupby("year").agg(precip_mm=("precip_mm", "sum"), temp_c=("temp_c", "mean")).reset_index()
        a.insert(0, "lake_id", r.lake_id)
        rows.append(a)
    c = pd.concat(rows)
    c.to_csv(f, index=False)
    return c


def diagnose(lakes, water, press, clim):
    print("5) motor de atribucion", flush=True)
    oni = pd.read_csv(ROOT / "data" / "real" / "oni.csv")
    s = water.rename(columns={"lake_id": "body_id", "value": "water_ha"})
    s = s.merge(clim.rename(columns={"lake_id": "body_id"}), on=["body_id", "year"]).merge(oni, on="year")
    s = s[s.year <= 2024].sort_values(["body_id", "year"])
    # presion humana: area humana en el anillo de 5 km
    sus = press.rename(columns={"lake_id": "body_id"}).assign(suspect="human_land_ha")
    # control regional sintetico: mediana de lagunas con poca presion de la misma celda de 3 grados
    lakes = lakes.copy()
    p0 = press[press.year <= 1990].groupby("lake_id").value.mean()
    p1 = press[press.year >= 2020].groupby("lake_id").value.mean()
    ring = lakes.set_index("lake_id")["ha"]  # escala de referencia
    lakes["pressure_growth_ha"] = lakes.lake_id.map(p1 - p0).fillna(0)
    lakes["region"] = (np.floor(lakes.lat / 3).astype(int).astype(str) + "_" + np.floor(lakes.lon / 3).astype(int).astype(str))
    low = lakes[lakes.lake_id.map(p1).fillna(0) <= lakes.lake_id.map(p1).fillna(0).quantile(0.33)]
    base = s[s.year <= 2000].groupby("body_id").water_ha.mean()
    ctrl_rows, ctrl_of = [], {}
    for reg, g in lakes.groupby("region"):
        members = low[low.region == reg].lake_id.tolist()
        if len(members) < 3:
            continue
        sub = s[s.body_id.isin(members)].copy()
        sub["norm"] = sub.water_ha / sub.body_id.map(base)
        med = sub.groupby("year").agg(water_ha=("norm", "median"), precip_mm=("precip_mm", "median"),
                                      temp_c=("temp_c", "median"), oni=("oni", "first")).reset_index()
        med["water_ha"] *= 1000
        med.insert(0, "body_id", f"CTRL_{reg}")
        ctrl_rows.append(med)
        for lid in g.lake_id:
            ctrl_of[lid] = f"CTRL_{reg}"
    series = pd.concat([s] + ctrl_rows, ignore_index=True)
    bodies = pd.DataFrame({"body_id": lakes.lake_id, "name": "Laguna " + lakes.lake_id, "lat": lakes.lat,
                           "lon": lakes.lon, "kind": "natural", "control_id": lakes.lake_id.map(ctrl_of).fillna(""),
                           "department": ""})
    ok = series.groupby("body_id").water_ha.apply(lambda v: v.notna().sum() >= 30 and v.max() > 0)
    bodies = bodies[bodies.body_id.isin(ok[ok].index)]
    results = []
    for _, b in bodies.iterrows():
        try:
            r = engine.analyze_body(b.body_id, series, sus, b.control_id or None, 2000)
        except Exception as e:  # serie degenerada (por ejemplo, agua casi constante en cero)
            print("   omitida", b.body_id, e)
            continue
        r.update({"name": b["name"], "lat": float(b.lat), "lon": float(b.lon), "control_id": b.control_id,
                  "ha": int(ring.get(b.body_id, 0))})
        for k in ("observed", "expected", "oni", "years"):
            r.pop(k, None)
        results.append(r)
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    df = pd.DataFrame([{"state": r["state"], "confidence": r["confidence"]} for r in results])
    print(df.value_counts().to_string())
    return results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--max", type=int, default=300)
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    OUT.mkdir(parents=True, exist_ok=True)
    lakes = detect(a.max)
    print("2) agua natural por ano", flush=True)
    wb = ee.Image(MB_WATER)
    water = per_year("agua", lambda y: HA().updateMask(
        wb.select(f"classification_{y}").remap(NATURAL, [1] * len(NATURAL), 0).eq(1)), lakes_fc(300), 60)
    print("3) uso humano del suelo por ano (anillo de 5 km)", flush=True)
    mb = ee.Image(MAPBIOMAS)
    last_mb = 2023
    press = per_year("presion", lambda y: HA().updateMask(
        mb.select(f"classification_{min(y, last_mb)}").remap(ANTHROPIC, [1] * len(ANTHROPIC), 0).eq(1)),
        lakes_fc(5000), 120)
    clim = climate(lakes)
    diagnose(lakes, water, press, clim)


if __name__ == "__main__":
    main()
