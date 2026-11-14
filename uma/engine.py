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
CLIMATE_SHARE_MIN = 0.6  # para decir "causa climatica", el clima debe explicar al menos el 60% de la perdida

SUSPECT_LABELS = {
    "forest_loss_ha": "Desmonte",
    "burned_ha": "Incendios",
    "dry_crop_ha": "Agricultura con riego",
    "pasture_ha": "Ganaderia",
    "mining_ha": "Mineria",
    "urban_ha": "Crecimiento urbano",
    "artificial_water_ha": "Represas y reservorios",
    "mining_water_ha": "Pozas mineras",
    "human_land_ha": "Uso humano del suelo (5 km)",
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
        "detail": f"Lo que el clima no explica tiene una tendencia de {resid_pct:+.0f}% de la media base en {span} anos "
                  f"(p={resid_mk['p']:.3f}; hace falta p<0.05 y al menos -{MIN_EFFECT_PCT}%). "
                  f"R2 del modelo de clima = {fit.r2:.2f}.",
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
    # pasa solo si el sospechoso crece antes del quiebre Y se relaciona en el sentido esperado (mas presion, menos agua)
    t3 = bool(top and top["precedes"] and top["p"] < ALPHA and top["rho"] < 0)
    test3 = {
        "pass": t3,
        "detail": (f"El residuo cambia en {resid_break}; {top['label'].lower()} empieza a crecer en {top['onset']}."
                   if top and resid_break else "No se detecta un quiebre claro en el residuo."),
        "p": top["p"] if top else None,
    }

    n_pass = sum(t["pass"] for t in (test1, test2, test3))
    confidence = {3: "Alta", 2: "Media"}.get(n_pass, "Baja")

    # Descomposicion del cambio: promedio de los ultimos 5 anos menos el promedio del periodo base.
    # Es la misma medida que el % de la tarjeta, y las partes suman exactamente el total.
    last, base_idx = df.index[-5:], df.loc[:baseline_end].index
    total_change = float(df["water_ha"].loc[last].mean() - base_mean)
    groups = {}
    for g, vs in CLIMATE_GROUPS.items():
        c = sum(fit.contributions[v] for v in vs)
        groups[g] = float(c.loc[last].mean() - c.loc[base_idx].mean())
    resid_change = float(resid.loc[last].mean() - resid.loc[base_idx].mean())
    human = resid_change if n_pass >= 2 else 0.0
    decomposition = {**groups, "Huella humana": human, "Sin explicar": resid_change - human}
    clim_change = sum(groups.values())
    climate_share = clim_change / total_change if total_change < 0 else None

    state = classify_state(df, resid, suspects[suspects.body_id == body_id], base_mean)
    if n_pass >= 2:            # las pruebas mandan: con 2 o 3 la perdida no la explica el clima
        state = "Huella humana"
    elif state == "Huella humana":
        state = "Sin explicar"  # presion y caida sin pruebas suficientes: no se acusa
    elif state == "Causa climatica" and (climate_share is None or climate_share < CLIMATE_SHARE_MIN):
        state = "Sin explicar"  # cae, pero el clima explica menos de la mayor parte: no se puede decir "climatica"

    quality = data_quality(df)
    if quality["level"] == "baja" and n_pass >= 2:
        confidence = {"Alta": "Media", "Media": "Baja"}[confidence]  # datos dudosos: se baja un nivel

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
        "climate_share": climate_share,
        "data_quality": quality,
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


AREA_TAG = {"subcuenca_local": "cerca", "cuenca_aporte": "cuenca"}


def base_name(name: str) -> str:
    """'mining_ha@cuenca' -> 'mining_ha'."""
    return name.split("@")[0]


def suspect_label(name: str) -> str:
    base, _, area = name.partition("@")
    lab = SUSPECT_LABELS.get(base, base)
    return f"{lab} ({area})" if area else lab


def tag_areas(sus: pd.DataFrame) -> pd.DataFrame:
    """Si un cuerpo de agua tiene sospechosos medidos en dos escalas, cada escala es un sospechoso aparte."""
    if "area" not in sus or sus.empty:
        return sus
    sus = sus.copy()
    multi = sus.groupby("body_id")["area"].transform("nunique") > 1
    sus.loc[multi, "suspect"] = sus.loc[multi, "suspect"] + "@" + sus.loc[multi, "area"].map(AREA_TAG).fillna("")
    return sus


CONTEXT_ONLY = {"natural_water_ha"}  # series de contexto que no son sospechosos


FLOWS = {"forest_loss_ha", "burned_ha"}  # hectareas por ano: se acumulan
MIN_SHARE_OF_LOSS = 0.10   # un sospechoso de area debe crecer al menos el 10% del agua perdida
PRE_GROWTH = 1.5           # y, para anteceder, haber crecido 1.5 veces antes del quiebre del agua


def audit_suspects(df, resid, sus: pd.DataFrame, resid_break: int | None, baseline_end: int) -> list[dict]:
    """Ordena los sospechosos por evidencia.

    Tres criterios (cada uno suma): crece de forma significativa; antecede la caida (ya habia crecido
    PRE_GROWTH veces antes del quiebre del agua); y se relaciona en el sentido esperado (mas presion,
    menos agua de la que explica el clima). Ademas, un sospechoso medido en hectareas que crecio menos
    del 10% del agua perdida es demasiado chico para explicarla: su evidencia queda en debil.
    """
    base_mean = float(df.loc[:baseline_end, "water_ha"].mean())
    water_lost = max(0.0, base_mean - float(df["water_ha"].iloc[-5:].mean()))
    out = []
    for name, g in sus.groupby("suspect"):
        bn = base_name(name)
        if bn in CONTEXT_ONLY:
            continue
        s = g.set_index("year")["value"].reindex(df.index).fillna(0.0)
        if s.std() == 0:
            continue
        rising = mann_kendall(s)["p"] < ALPHA and sen_slope(s.index.values, s) > 0
        level = s.cumsum() if bn in FLOWS else s  # area acumulada para desmonte y fuego
        pressure = _excess(s, baseline_end, bn in FLOWS)
        idx, _ = pettitt(s.values)
        onset = int(df.index[idx])
        rho, p = stats.spearmanr(pressure, resid)
        r2 = float(rho**2)
        early = float(level.iloc[:5].mean())
        growth = float(level.iloc[-5:].mean() - early)
        is_area = bn.endswith("_ha")
        big_enough = (not is_area) or water_lost == 0 or growth >= MIN_SHARE_OF_LOSS * water_lost
        precedes = False
        if rising and resid_break is not None:
            # nivel alrededor del quiebre (el ano anterior al siguiente): como en la regla original, el
            # sospechoso puede arrancar el mismo ano en que se quiebra el agua
            pre = float(level.loc[resid_break - 1:resid_break + 1].mean())
            min_abs = MIN_SHARE_OF_LOSS * water_lost if is_area else 0.0
            precedes = pre >= PRE_GROWTH * max(early, 1e-9) and (pre - early) >= min_abs
        relation = bool(p < ALPHA and rho < 0 and r2 > 0.3)
        hits = sum([precedes, rising, relation])
        evidence = {3: "fuerte", 2: "media"}.get(hits, "debil") if big_enough else "debil"
        out.append({
            "suspect": name,
            "label": suspect_label(name),
            "onset": onset,
            "rho": float(rho),
            "p": float(p),
            "r2": r2,
            "precedes": bool(precedes),
            "rising": bool(rising),
            "growth": round(growth, 1),
            "share_of_loss": round(growth / water_lost, 2) if is_area and water_lost else None,
            "big_enough": bool(big_enough),
            "evidence": evidence,
            "score": (hits if big_enough else 0) + r2,
        })
    out.sort(key=lambda d: d["score"], reverse=True)
    # sospechosos que crecen juntos: se reportan como inseparables
    for a in out:
        a["together_with"] = [b["label"] for b in out if b is not a and b["evidence"] == a["evidence"] != "debil"
                              and abs(b["onset"] - a["onset"]) <= 2]
    return out


# solo el cambio de uso del suelo dispara la alerta; poblacion y luces crecen en casi todas partes
ALERT_SUSPECTS = {"mining_ha", "agri_ha", "pasture_ha", "urban_ha", "forest_loss_ha", "dry_crop_ha",
                  "artificial_water_ha", "mining_water_ha", "human_land_ha"}
ALERT_GROWTH = 1.5   # el sospechoso debe crecer al menos 1.5 veces
ALERT_MIN_HA = 50    # y en al menos 50 ha


def pressure_rising(sus: pd.DataFrame, recent) -> bool:
    """Presion humana creciendo de verdad en los ultimos 15 anos: tendencia significativa,
    al menos 1.5 veces lo que habia al inicio de la ventana y al menos 50 ha mas."""
    for name, g in sus.groupby("suspect"):
        if base_name(name) not in ALERT_SUSPECTS:
            continue
        s = g.set_index("year")["value"].reindex(recent).fillna(0.0)
        if s.std() == 0 or mann_kendall(s)["p"] >= ALPHA or sen_slope(recent, s) <= 0:
            continue
        early, late = s.iloc[:5].mean(), s.iloc[-5:].mean()
        if late - early >= ALERT_MIN_HA and late >= ALERT_GROWTH * max(early, 1e-9):
            return True
    return False


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
    change_pct = 100 * (df["water_ha"].iloc[-5:].mean() - base_mean) / base_mean if base_mean else 0.0
    obs_falling = (mann_kendall(df["water_ha"])["p"] < ALPHA and sen_slope(full, df["water_ha"]) < 0
                   and change_pct <= -MIN_EFFECT_PCT)  # una caida menor al 10% no se etiqueta
    rising = pressure_rising(sus, recent)
    if rising and falling:
        return "Huella humana"
    if falling:
        return "Sin explicar"
    if obs_falling:
        return "Causa climatica"
    if rising:
        return "Alerta temprana"
    return "Intacto"


def data_quality(df) -> dict:
    """Calidad de la serie de agua: coincidencia de Landsat con JRC y anos interpolados."""
    out = {"level": "sin validar", "r_jrc": None, "interpolated_years": []}
    if "nodata_pct" in df:
        out["interpolated_years"] = [int(y) for y in df.index[df["nodata_pct"] > 20]]
    if "water_ha_jrc" in df and df["water_ha_jrc"].notna().sum() > 5:
        both = df[["water_ha", "water_ha_jrc"]].dropna()
        r = float(both["water_ha"].corr(both["water_ha_jrc"]))
        out["r_jrc"] = r
        out["level"] = "alta" if r >= 0.85 else "media" if r >= 0.7 else "baja"
    return out


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
    suspects = tag_areas(suspects)
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
