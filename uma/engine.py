"""Motor de evaluación exploratoria de Uma (versión conservadora).

Compara referencias con validación temporal y evalúa anomalías con incertidumbre.
Una pérdida residual no se convierte automáticamente en intervención humana.
La implementación de calidad y evidencia está en validation.py y safeguarded.py.

Formato de entrada (contrato con P1, ver README):
  bodies.csv   body_id, name, lat, lon, kind, control_id, department
  series.csv   body_id, year, water_ha, precip_mm, temp_c, oni
  suspects.csv body_id, year, suspect, value
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05
CLIMATE_VARS = ["precip_mm", "precip_lag1", "temp_c", "oni"]
CLIMATE_GROUPS = {"Sequia y calor": ["precip_mm", "precip_lag1", "temp_c"], "El Nino": ["oni"]}
MAX_LAG_YEARS = 5
MIN_EFFECT_PCT = 10  # una perdida menor al 10% de la media base no se considera relevante

SUSPECT_LABELS = {
    "forest_loss_ha": "Desmonte",
    "burned_ha": "Incendios",
    "dry_crop_ha": "Agricultura con riego",
    "pasture_ha": "Ganaderia",
    "mining_ha": "Mineria",
    "urban_ha": "Crecimiento urbano",
    "artificial_water_ha": "Represas y desvios",
    "agri_ha": "Agricultura",
    "night_lights": "Luces nocturnas (ciudad e industria)",
    "population": "Poblacion",
}


# ---------------------------------------------------------------- estadistica
def mann_kendall(y) -> dict:
    """Mann-Kendall con correccion por empates. Devuelve tau, z, p."""
    y = np.asarray(y, dtype=float)
    y = y[~np.isnan(y)]
    n = len(y)
    if n < 4:
        return {"tau": 0.0, "z": 0.0, "p": 1.0}
    s = 0.0
    for i in range(n - 1):
        s += np.sign(y[i + 1:] - y[i]).sum()
    _, counts = np.unique(y, return_counts=True)
    var_s = (n * (n - 1) * (2 * n + 5) - (counts * (counts - 1) * (2 * counts + 5)).sum()) / 18.0
    if var_s <= 0:
        return {"tau": 0.0, "z": 0.0, "p": 1.0}
    z = (s - np.sign(s)) / math.sqrt(var_s) if s != 0 else 0.0
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    tau = s / (0.5 * n * (n - 1))
    return {"tau": float(tau), "z": float(z), "p": float(p)}


def sen_slope(x, y) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = ~np.isnan(y)
    x, y = x[ok], y[ok]
    slopes = [(y[j] - y[i]) / (x[j] - x[i]) for i in range(len(x)) for j in range(i + 1, len(x)) if x[j] != x[i]]
    return float(np.median(slopes)) if slopes else 0.0


def pettitt(y) -> tuple[int, float]:
    """Prueba de Pettitt: indice del punto de cambio y su valor p aproximado."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 6:
        return 0, 1.0
    u = np.array([np.sign(y[: t + 1, None] - y[None, t + 1:]).sum() for t in range(n - 1)])
    k = int(np.argmax(np.abs(u)))
    kmax = abs(u[k])
    p = min(1.0, 2 * math.exp(-6 * kmax**2 / (n**3 + n**2)))
    return k + 1, float(p)  # primer indice del segundo tramo


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Correccion de Holm para pruebas multiples (muchos cuerpos de agua)."""
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


# ---------------------------------------------------------------- modelo
@dataclass
class ClimateFit:
    model: object
    baseline_end: int
    r2: float
    expected: pd.Series
    contributions: dict[str, pd.Series]


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    from .validation import prepare
    return prepare(df)


def fit_climate(df: pd.DataFrame, baseline_end: int) -> ClimateFit:
    """Modelo seleccionado con cortes temporales dentro del período base."""
    from .safeguarded import climate
    from types import SimpleNamespace
    result = climate(df, baseline_end)
    return ClimateFit(SimpleNamespace(rsquared=result["r2"]), baseline_end,
                      result["r2"], result["expected"], result["contributions"])


def _residual(df: pd.DataFrame, baseline_end: int) -> tuple[ClimateFit, pd.Series]:
    fit = fit_climate(df, baseline_end)
    return fit, df["water_ha"] - fit.expected


# ---------------------------------------------------------------- analisis
def analyze_body(body_id: str, series: pd.DataFrame, suspects: pd.DataFrame,
                 control_id: str | None, baseline_end: int) -> dict:
    from .safeguarded import analyze_body as analyze
    return analyze(body_id, series, suspects, control_id, baseline_end)


def audit_suspects(df, resid, sus, resid_break, baseline_end):
    from .safeguarded import audit_suspects as analyze
    return analyze(df, resid, sus, resid_break, baseline_end)


def backtest(df, baseline_end: int) -> dict:
    from .safeguarded import climate
    return climate(df, baseline_end)["backtest"]


def run(bodies: pd.DataFrame, series: pd.DataFrame, suspects: pd.DataFrame, baseline_end: int = 2000) -> list[dict]:
    results = []
    for _, b in bodies.iterrows():
        ctrl = b.get("control_id")
        ctrl = ctrl if isinstance(ctrl, str) and ctrl else None
        r = analyze_body(b.body_id, series, suspects, ctrl, baseline_end)
        r.update({"name": b["name"], "lat": float(b.lat), "lon": float(b.lon), "kind": b.kind,
                  "department": b.get("department", ""), "control_id": ctrl})
        results.append(r)
    # correccion por pruebas multiples sobre la tendencia de todos los cuerpos de agua
    adj = holm({r["body_id"]: r["trend"]["p"] for r in results})
    for r in results:
        r["trend"]["p_holm"] = adj[r["body_id"]]
    # Corregir también las pruebas que determinan los estados, no solo la tendencia descriptiva.
    from .safeguarded import finalize
    for name in ("clima", "control"):
        corrected = holm({r["body_id"]: r["tests"][name]["p"] for r in results
                          if r["tests"][name].get("evaluated") and r["tests"][name].get("p") is not None})
        for r in results:
            t = r["tests"][name]
            t["p_adjusted"] = corrected.get(r["body_id"])
            t["pass"] = bool(t["pass"] and t["p_adjusted"] is not None and t["p_adjusted"] < ALPHA)
            if t["p_adjusted"] is not None:
                t["detail"] += f" Holm entre cuerpos: p={t['p_adjusted']:.3f}."
    return [finalize(r) for r in results]
