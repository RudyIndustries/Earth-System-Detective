"""Lluvia combinada: promedio de NASA POWER y CHIRPS en la cuenca de aporte de cada cuerpo de agua.

  python -m uma.climate_blend --project TU-PROYECTO

La verificacion cruzada mostro que NASA POWER y CHIRPS coinciden solo en parte (r de 0.53 a 0.77 y
diferencias de hasta 100 mm al ano). Ninguna es la verdad; el promedio de dos fuentes independientes
reduce el error de cada una. series.csv guarda las tres columnas:
  precip_power_mm   NASA POWER (MERRA-2/IMERG), promedio de la grilla de la cuenca
  precip_chirps_mm  CHIRPS (estaciones + satelite), promedio de la cuenca
  precip_mm         promedio de ambas: es la que usa el modelo de clima
"""
from __future__ import annotations

import argparse
from pathlib import Path

import ee
import pandas as pd

from uma.suspects_upstream import basin_geometry
from uma.verify import chirps

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    s = pd.read_csv(DATA / "series.csv")
    rows = []
    for bid in s.body_id.unique():
        if not (DATA / "basins" / f"{bid}.geojson").exists():
            continue
        c = chirps(basin_geometry(bid))
        rows += [{"body_id": bid, "year": int(y), "precip_chirps_mm": round(float(v), 1)} for y, v in c.items()
                 if v is not None]
        print(bid, "listo", flush=True)
    ch = pd.DataFrame(rows)
    ch.to_csv(DATA / "chirps.csv", index=False)
    if "precip_power_mm" not in s:
        s = s.rename(columns={"precip_mm": "precip_power_mm"})
    s = s.drop(columns=[c for c in ("precip_chirps_mm", "precip_mm") if c in s]).merge(ch, on=["body_id", "year"],
                                                                                       how="left")
    s["precip_mm"] = s[["precip_power_mm", "precip_chirps_mm"]].mean(axis=1)  # si falta CHIRPS, queda POWER
    s.to_csv(DATA / "series.csv", index=False)
    print(s.groupby("body_id")[["precip_power_mm", "precip_chirps_mm", "precip_mm"]].mean().round(0).to_string())


if __name__ == "__main__":
    main()
