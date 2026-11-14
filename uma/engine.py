"""Motor de atribucion de Uma.

Separa la huella humana del clima en la serie de agua de un cuerpo de agua.
Siempre los mismos pasos:
  1. Tendencia (Mann-Kendall + pendiente de Sen)
  2. Prueba 1: lo que explica el clima (modelo entrenado en el periodo base)
  3. Prueba 2: comparacion con la gemela de control
  4. Prueba 3: coincidencia en el tiempo con un sospechoso
  5. Descomposicion, confianza, auditoria de sospechosos y estado

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
import statsmodels.api as sm
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
    df = df.sort_values("year").copy()
    df["precip_lag1"] = df["precip_mm"].shift(1).bfill()
    return df.set_index("year")


def fit_climate(df: pd.DataFrame, baseline_end: int) -> ClimateFit:
    """Ajusta agua ~ lluvia + lluvia(t-1) + temperatura + ONI solo en el periodo base.

    Entrenar solo en el periodo base evita que el modelo de clima absorba la tendencia
    humana posterior (es la variante 'entrenar hasta X' del documento).
    """
    base = df.loc[:baseline_end]
    X = sm.add_constant(base[CLIMATE_VARS])
    model = sm.OLS(base["water_ha"], X).fit()
    Xall = sm.add_constant(df[CLIMATE_VARS], has_constant="add")
    expected = model.predict(Xall)
    means = base[CLIMATE_VARS].mean()
    contributions = {v: model.params[v] * (df[v] - means[v]) for v in CLIMATE_VARS}
    return ClimateFit(model, baseline_end, float(model.rsquared), expected, contributions)


def _residual(df: pd.DataFrame, baseline_end: int) -> tuple[ClimateFit, pd.Series]:
    fit = fit_climate(df, baseline_end)
    return fit, df["water_ha"] - fit.expected


# ---------------------------------------------------------------- analisis
def analyze_body(body_id: str, series: pd.DataFrame, suspects: pd.DataFrame,
                 control_id: str | None, baseline_end: int) -> dict:
    df = _prep(series[series.body_id == body_id])
    years = df.index.values
    span = years[-1] - years[0]
    base_mean = float(df.loc[:baseline_end, "water_ha"].mean())

    trend = mann_kendall(df["water_ha"])
    total_slope = sen_slope(years, df["water_ha"])

    fit, resid = _residual(df, baseline_end)
    resid_mk = mann_kendall(resid)
    resid_slope = sen_slope(years, resid)
    clim_slope = sen_slope(years, fit.expected)

    # Prueba 1: el clima no alcanza a explicar la perdida
    resid_pct = 100 * resid_slope * span / base_mean if base_mean else 0.0
    t1 = resid_mk["p"] < ALPHA and resid_pct <= -MIN_EFFECT_PCT
    test1 = {
        "pass": bool(t1),
        "detail": f"Residuo {resid_slope*span:+.0f} ha ({resid_pct:+.0f}%) en {span} anos (p={resid_mk['p']:.3f}); "
                  f"el clima solo explica {clim_slope*span:+.0f} ha. R2 del modelo de clima = {fit.r2:.2f}.",
        "p": resid_mk["p"],
    }

    # Prueba 2: la gemela de control no cae igual
    test2 = {"pass": False, "detail": "Sin gemela de control asignada.", "p": None}
    if control_id and (series.body_id == control_id).any():
        cdf = _prep(series[series.body_id == control_id])
        _, cres = _residual(cdf, baseline_end)
        cbase = float(cdf.loc[:baseline_end, "water_ha"].mean())
        diff = (resid / base_mean - cres / cbase).dropna() * 100  # puntos porcentuales
        dmk = mann_kendall(diff)
        dslope = sen_slope(diff.index.values, diff)
        t2 = dmk["p"] < ALPHA and dslope < 0
        test2 = {
            "pass": bool(t2),
            "detail": f"Frente a su gemela pierde {dslope*span:+.1f} puntos % extra (p={dmk['p']:.3f}).",
            "p": dmk["p"],
        }

    # Auditoria de sospechosos + Prueba 3 (coincidencia en el tiempo)
    cp_idx, cp_p = pettitt(resid.values)
    resid_break = int(years[cp_idx]) if cp_p < 0.1 else None
    ranked = audit_suspects(df, resid, suspects[suspects.body_id == body_id], resid_break, baseline_end)
    top = ranked[0] if ranked else None
    t3 = bool(top and top["precedes"] and top["p"] < ALPHA)
    test3 = {
        "pass": t3,
        "detail": (f"El residuo cambia en {resid_break}; {top['label'].lower()} empieza a crecer en {top['onset']}."
                   if top and resid_break else "No se detecta un quiebre claro en el residuo."),
        "p": top["p"] if top else None,
    }

    n_pass = sum(t["pass"] for t in (test1, test2, test3))
    confidence = {3: "Alta", 2: "Media"}.get(n_pass, "Baja")

    # Descomposicion del cambio total (ha a lo largo del periodo)
    groups = {g: sen_slope(years, sum(fit.contributions[v] for v in vs)) * span for g, vs in CLIMATE_GROUPS.items()}
    human = resid_slope * span if n_pass >= 2 else 0.0
    unexplained = total_slope * span - sum(groups.values()) - human
    decomposition = {**groups, "Huella humana": human, "Sin explicar": unexplained}

    state = classify_state(df, resid, suspects[suspects.body_id == body_id], base_mean)
    if n_pass >= 2:            # las pruebas mandan: con 2 o 3 la perdida no la explica el clima
        state = "Huella humana"
    elif state == "Huella humana":
        state = "Sin explicar"  # presion y caida sin pruebas suficientes: no se acusa

    return {
        "body_id": body_id,
        "years": [int(y) for y in years],
        "observed": [round(float(v), 1) for v in df["water_ha"]],
        "expected": [round(float(v), 1) for v in fit.expected],
        "oni": [round(float(v), 2) for v in df["oni"]],
        "baseline_end": baseline_end,
        "baseline_mean_ha": round(base_mean, 1),
        "trend": {**trend, "sen_ha_per_year": total_slope,
                  "change_pct": 100 * (df["water_ha"].iloc[-5:].mean() - base_mean) / base_mean if base_mean else 0.0},
        "climate_r2": fit.r2,
        "tests": {"clima": test1, "control": test2, "coincidencia": test3},
        "n_pass": n_pass,
        "confidence": confidence,
        "decomposition_ha": {k: round(float(v), 1) for k, v in decomposition.items()},
        "suspects": ranked,
        "state": state,
        "backtest": backtest(df, baseline_end),
    }


def _excess(s: pd.Series, baseline_end: int, cumulative: bool) -> pd.Series:
    """Presion por encima de su ritmo base.

    Desmonte y fuego dejan efecto acumulado, pero la suma acumulada de cualquier serie positiva
    siempre sube; por eso se acumula solo el exceso sobre el ritmo del periodo base (o de los
    primeros 5 anos con dato, si el dataset empieza despues, como Hansen en 2001).
    """
    ref = s.loc[:baseline_end]
    if (ref > 0).sum() < 5:
        ref = s[s > 0].iloc[:5]
    ex = s - (ref.mean() if len(ref) else 0.0)
    return ex.cumsum() if cumulative else ex


def audit_suspects(df, resid, sus: pd.DataFrame, resid_break: int | None, baseline_end: int) -> list[dict]:
    out = []
    for name, g in sus.groupby("suspect"):
        s = g.set_index("year")["value"].reindex(df.index).fillna(0.0)
        if s.std() == 0:
            continue
        rising_mk = mann_kendall(s)
        rising = rising_mk["p"] < ALPHA and sen_slope(s.index.values, s) > 0
        pressure = _excess(s, baseline_end, name in ("forest_loss_ha", "burned_ha"))
        idx, _ = pettitt(s.values)
        onset = int(df.index[idx])
        rho, p = stats.spearmanr(pressure, resid)
        r2 = float(rho**2)
        precedes = rising and resid_break is not None and 0 <= resid_break - onset <= MAX_LAG_YEARS
        # se espera relacion negativa: mas presion, menos agua de la esperada
        hits = sum([precedes, rising, bool(p < ALPHA and rho < 0 and r2 > 0.3)])
        out.append({
            "suspect": name,
            "label": SUSPECT_LABELS.get(name, name),
            "onset": onset,
            "rho": float(rho),
            "p": float(p),
            "r2": r2,
            "precedes": bool(precedes),
            "rising": bool(rising),
            "evidence": {3: "fuerte", 2: "media"}.get(hits, "debil"),
            "score": hits + r2,
        })
    out.sort(key=lambda d: d["score"], reverse=True)
    # sospechosos que crecen juntos: se reportan como inseparables
    for a in out:
        a["together_with"] = [b["label"] for b in out if b is not a and b["evidence"] == a["evidence"] != "debil"
                              and abs(b["onset"] - a["onset"]) <= 2]
    return out


def classify_state(df, resid, sus: pd.DataFrame, base_mean: float) -> str:
    """Estados segun la presion humana, el agua observada y el agua sin efecto climatico.

    Huella humana   presion sube, residuo cae
    Causa climatica el agua observada cae pero el residuo no
    Alerta temprana presion sube, residuo aun estable
    Sin explicar    residuo cae sin presion medida (revisar sospechosos no medidos)
    Intacto         nada de lo anterior
    """
    recent = df.index[-15:]

    def _falls(s):
        slope = sen_slope(recent, s.loc[recent])
        big = base_mean and 100 * slope * len(recent) / base_mean <= -MIN_EFFECT_PCT
        return mann_kendall(s.loc[recent])["p"] < ALPHA and bool(big)

    falling = _falls(resid)
    full = df.index
    obs_falling = (mann_kendall(df["water_ha"])["p"] < ALPHA and sen_slope(full, df["water_ha"]) < 0)
    rising = False
    for _, g in sus.groupby("suspect"):  # alguna presion humana creciendo en los ultimos 15 anos
        s = g.set_index("year")["value"].reindex(recent).fillna(0.0)
        if s.std() > 0 and mann_kendall(s)["p"] < ALPHA and sen_slope(recent, s) > 0:
            rising = True
    if rising and falling:
        return "Huella humana"
    if falling:
        return "Sin explicar"
    if obs_falling:
        return "Causa climatica"
    if rising:
        return "Alerta temprana"
    return "Intacto"


def backtest(df, baseline_end: int) -> dict:
    """Validacion con el pasado: entrenar hasta baseline_end y medir el error despues.

    Solo tiene sentido en cuerpos de agua sin huella humana (controles); en los demas
    el error alto ES la senal.
    """
    fit = fit_climate(df, baseline_end)
    after = df.loc[baseline_end + 1:]
    if after.empty:
        return {}
    err = after["water_ha"] - fit.expected.loc[after.index]
    return {"mae_ha": float(err.abs().mean()), "bias_ha": float(err.mean()),
            "mae_pct": float(100 * err.abs().mean() / df["water_ha"].mean())}


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
    return results
