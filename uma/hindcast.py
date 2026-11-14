"""Que tan predictivo es Uma: prueba hacia atras (hindcast).

  python -m uma.hindcast            # usa data/real

Para cada ano de corte (2006, 2010, 2014, 2018) corre el motor solo con los datos hasta ese ano,
como si estuvieramos en ese momento, y lo compara con lo que paso en los 5 anos siguientes.

Mide dos cosas:
  1. Alertas: los cuerpos de agua marcados (huella humana, alerta temprana o sin explicar) perdieron
     mas agua despues que los no marcados?
  2. Pronostico a 5 anos del agua: modelo de clima + tendencia del residuo, conociendo el clima real
     de esos anos, contra la persistencia (suponer que el agua se queda igual que el ultimo ano).
     Es la forma honesta de decir si el modelo agrega algo a "no hacer nada".
Salida: data/real/hindcast.csv y un resumen en pantalla.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from uma import engine

ROOT = Path(__file__).resolve().parent.parent
CUTS = [2006, 2010, 2014, 2018]
HORIZON = 5
FLAGGED = {"Huella humana", "Alerta temprana"}


def forecast(df: pd.DataFrame, cut: int, baseline_end: int) -> pd.Series:
    """Agua esperada despues del corte: clima real de esos anos + tendencia del residuo hasta el corte."""
    d = engine._prep(df)
    hist = d.loc[:cut]
    fit = engine.fit_climate(hist, baseline_end)
    resid = hist["water_ha"] - fit.expected.loc[hist.index]
    recent = resid.loc[cut - 9:cut]
    slope = engine.sen_slope(recent.index.values, recent)
    level = float(recent.iloc[-3:].mean())
    import statsmodels.api as sm
    fut = d.loc[cut + 1:cut + HORIZON]
    X = sm.add_constant(fut[engine.CLIMATE_VARS], has_constant="add")
    exp = fit.model.predict(X)
    return exp + level + slope * (fut.index.values - cut + 1)


def main():
    src = ROOT / "data" / "real"
    bodies = pd.read_csv(src / "bodies.csv", dtype={"control_id": str}).fillna({"control_id": ""})
    series = pd.read_csv(src / "series.csv")
    suspects = pd.read_csv(src / "suspects.csv")
    rows = []
    for cut in CUTS:
        s_cut = series[series.year <= cut]
        res = engine.run(bodies, s_cut, suspects[suspects.year <= cut], 2000)
        for r in res:
            df = series[series.body_id == r["body_id"]].sort_values("year").set_index("year")
            before = df.loc[cut - 4:cut, "water_ha"].mean()
            after = df.loc[cut + 1:cut + HORIZON, "water_ha"]
            if after.empty:
                continue
            fut_change = 100 * (after.mean() - before) / before
            fc = forecast(series[series.body_id == r["body_id"]], cut, 2000)
            obs = after.loc[fc.index]
            persist = df.loc[cut, "water_ha"]
            scale = df.loc[:cut, "water_ha"].mean()
            rows.append({
                "cut": cut, "body_id": r["body_id"], "state": r["state"], "confidence": r["confidence"],
                "flagged": r["state"] in FLAGGED, "future_change_pct": round(fut_change, 1),
                "mae_model_pct": round(100 * float((obs - fc).abs().mean()) / scale, 1),
                "mae_persistence_pct": round(100 * float((obs - persist).abs().mean()) / scale, 1),
            })
    h = pd.DataFrame(rows)
    h.to_csv(src / "hindcast.csv", index=False)

    print("Estado en el ano de corte -> cambio del agua en los 5 anos siguientes\n")
    print(h.pivot_table(index="body_id", columns="cut", values="state", aggfunc="first").to_string())
    print()
    print(h.pivot_table(index="body_id", columns="cut", values="future_change_pct", aggfunc="first").to_string())
    f, nf = h[h.flagged], h[~h.flagged]
    print(f"\n1) Alertas: {len(f)} marcados, perdida media despues {f.future_change_pct.mean():+.1f}% | "
          f"{len(nf)} no marcados, {nf.future_change_pct.mean():+.1f}%")
    hits = (f.future_change_pct <= -10).sum()
    print(f"   de los marcados, {hits} perdieron mas de 10% despues ({100 * hits / max(len(f), 1):.0f}%); "
          f"de los no marcados, {(nf.future_change_pct <= -10).sum()} ({100 * (nf.future_change_pct <= -10).mean():.0f}%)")
    skill = 1 - h.mae_model_pct.mean() / h.mae_persistence_pct.mean()
    print(f"\n2) Pronostico a {HORIZON} anos (error medio en % del agua media):")
    print(f"   modelo {h.mae_model_pct.mean():.1f}%  vs  persistencia {h.mae_persistence_pct.mean():.1f}%  "
          f"-> mejora {100 * skill:+.0f}% {'(el modelo agrega informacion)' if skill > 0 else '(no supera a no hacer nada)'}")
    print(h.groupby("body_id")[["mae_model_pct", "mae_persistence_pct"]].mean().round(1).to_string())


if __name__ == "__main__":
    main()
