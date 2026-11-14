"""Carga de datos con cache: cada archivo se lee una sola vez mientras no cambie en disco."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
_REAL = ROOT / "data" / "real"
DATA = Path(os.environ.get("UMA_DATA") or (_REAL if (_REAL / "results.json").exists() else ROOT / "data" / "sample"))
NATDIR = ROOT / "data" / "national"
CTX = DATA / "context"
IMG = DATA / "img"


def _mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_data(show_spinner=False)
def _json(path: str, mtime: float):
    return json.loads(Path(path).read_text(encoding="utf-8")) if mtime else None


@st.cache_data(show_spinner=False)
def _csv(path: str, mtime: float) -> pd.DataFrame | None:
    return pd.read_csv(path) if mtime else None


def json_file(p: Path):
    return _json(str(p), _mtime(p))


def csv_file(p: Path) -> pd.DataFrame | None:
    return _csv(str(p), _mtime(p))


def results() -> list[dict]:
    return json_file(DATA / "results.json") or []


def national() -> list[dict]:
    rows = json_file(NATDIR / "results.json") or []
    for r in rows:  # resultados de versiones anteriores del motor
        if r["state"] not in ("Huella humana", "Alerta temprana", "Incalculable", "Causa climatica", "Intacto"):
            r["state"] = "Incalculable"
    return rows


def artificial_points() -> dict | None:
    return json_file(NATDIR / "agua_artificial.json")


def weekly() -> dict | None:
    return json_file(DATA / "alertas_semanales.json")


def suspects() -> pd.DataFrame:
    df = csv_file(DATA / "suspects.csv")
    return df if df is not None else pd.DataFrame(columns=["body_id", "year", "suspect", "value", "area"])


def places(body_id: str | None) -> list[dict]:
    return (json_file(CTX / f"{body_id}_lugares.json") or []) if body_id else []


def context_meta(body_id: str) -> dict | None:
    """Alrededores solo si estan las tres imagenes (antes, despues, cambios)."""
    if all((CTX / f"{body_id}_{k}.png").exists() for k in ("antes", "despues", "cambios")):
        return json_file(CTX / f"{body_id}_meta.json")
    return None


def fires_for(body_id: str) -> dict | None:
    wk = weekly()
    return next((x for x in wk["rows"] if x["body_id"] == body_id), None) if wk else None


def controls(res: list[dict]) -> set[str]:
    return {r["control_id"] for r in res if r.get("control_id")}


def region(lat: float, lon: float) -> str:
    """Region aproximada para vistas agregadas."""
    if lon < -65.6 and lat < -14.5:
        return "Altiplano y valles"
    return "Llanos (Chaco, Chiquitania, Amazonia)"


def share_pct(r: dict) -> float | None:
    """Cuanto de la perdida explica el clima (%); vacio sin perdida relevante o sin modelo confiable."""
    sh = r.get("climate_share")
    if sh is None or r["trend"]["change_pct"] > -10:
        return None
    return round(100 * max(min(sh, 2.0), -1.0))
