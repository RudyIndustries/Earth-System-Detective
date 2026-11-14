"""Datos de prueba con el mismo formato que exporta Earth Engine.

Sirven para que P2 (modelo) y P3 (interfaz) trabajen antes de tener los CSV reales.
Los cuerpos de agua son FICTICIOS: no usar estos numeros en el pitch.
"""
from pathlib import Path

import numpy as np
import pandas as pd

YEARS = np.arange(1985, 2025)


def _climate(rng, base_precip):
    oni = np.clip(rng.normal(0, 0.9, len(YEARS)), -2.2, 2.6)
    for y, v in {1997: 2.2, 2015: 2.4, 2023: 1.9, 1988: -1.8, 2010: -1.5}.items():
        oni[YEARS == y] = v
    precip = base_precip * (1 - 0.12 * oni) + rng.normal(0, base_precip * 0.08, len(YEARS))
    temp = 18 + 0.02 * (YEARS - 1985) + 0.3 * oni + rng.normal(0, 0.2, len(YEARS))
    return precip, temp, oni


def _water(rng, base_ha, precip, temp, human_loss):
    lag = np.r_[precip[0], precip[:-1]]
    w = base_ha * (0.55 + 0.30 * precip / precip.mean() + 0.15 * lag / lag.mean()) - 0.02 * base_ha * (temp - 18)
    return np.maximum(w - human_loss + rng.normal(0, base_ha * 0.03, len(YEARS)), 0)


def build(out_dir: Path, seed: int = 7):
    rng = np.random.default_rng(seed)
    bodies, series, suspects = [], [], []
    cases = [
        # id, nombre, lat, lon, control, perdida humana desde, ha/ano, sospechoso que crece
        ("A", "Caso A - laguna con desmonte (ficticio)", -16.1, -62.0, "A_ctrl", 2003, 40, "forest_loss_ha", 2001),
        ("B", "Caso B - laguna con causa climatica (ficticio)", -18.9, -67.0, "B_ctrl", None, 0, None, None),
        ("C", "Caso C - laguna en alerta temprana (ficticio)", -14.8, -64.9, "C_ctrl", None, 0, "dry_crop_ha", 2016),
        ("D", "Caso D - laguna con mineria (ficticio)", -15.4, -68.4, "D_ctrl", 2008, 25, "mining_ha", 2006),
    ]
    for cid, name, lat, lon, ctrl, h_start, h_rate, sus, s_start in cases:
        precip, temp, oni = _climate(rng, 900 if lon > -65 else 450)
        if cid == "B":  # sequia de fondo que se intensifica: la causa es el clima
            precip = precip * np.linspace(1.0, 0.75, len(YEARS))
        loss = np.where(YEARS >= (h_start or 9999), (YEARS - (h_start or 0)) * h_rate, 0)
        for body_id, nm, la, lo, human in [(cid, name, lat, lon, loss), (ctrl, f"Gemela de control de {cid}", lat + 0.3, lon + 0.3, 0)]:
            p = precip * rng.normal(1, 0.03, len(YEARS))
            w = _water(rng, 2000, p, temp, human)
            series += [dict(body_id=body_id, year=int(y), water_ha=round(v, 1), precip_mm=round(pp, 1),
                            temp_c=round(t, 2), oni=round(o, 2)) for y, v, pp, t, o in zip(YEARS, w, p, temp, oni)]
            bodies.append(dict(body_id=body_id, name=nm, lat=la, lon=lo, kind="natural",
                               control_id=ctrl if body_id == cid else "", department="Ficticio"))
            # sospechosos de fondo (ruido) para todos
            for s_name in ("forest_loss_ha", "burned_ha", "dry_crop_ha", "mining_ha"):
                base = rng.gamma(2, 15, len(YEARS))
                if body_id == cid and s_name == sus:
                    base = base + np.where(YEARS >= s_start, (YEARS - s_start + 1) * 30, 0)
                suspects += [dict(body_id=body_id, year=int(y), suspect=s_name, value=round(v, 1))
                             for y, v in zip(YEARS, base)]
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(bodies).to_csv(out_dir / "bodies.csv", index=False)
    pd.DataFrame(series).to_csv(out_dir / "series.csv", index=False)
    pd.DataFrame(suspects).to_csv(out_dir / "suspects.csv", index=False)


if __name__ == "__main__":
    build(Path(__file__).resolve().parent.parent / "data" / "sample")
    print("Datos de prueba en data/sample/")
