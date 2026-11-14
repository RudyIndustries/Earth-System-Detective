"""Componentes visuales: tarjetas, etiquetas de estado y graficos SVG animados (sin dependencias)."""
from __future__ import annotations

import html

import streamlit as st

import icons as ic
import theme as th


def md(html_text: str) -> None:
    st.markdown(html_text, unsafe_allow_html=True)


def heading(icon: str, text: str, level: int = 2, color: str = th.ACCENT) -> str:
    size = 28 if level == 2 else 22
    return f"<div class='h h{level}'>{ic.svg(icon, color, size, 2.3)}<span>{html.escape(text)}</span></div>"


def pill(state: str, big: bool = False) -> str:
    s = th.STATES.get(state, th.STATES["Incalculable"])
    return (f"<span class='pill{' big' if big else ''}' style='background:{s['color']}'>"
            f"{ic.svg(s['icon'], th.INK, 24 if big else 17, 2.6)}{html.escape(state)}</span>")


def chip(text: str, icon: str | None = None, color: str = th.MUTED) -> str:
    i = ic.svg(icon, color, 14, 2.4) if icon else ""
    return f"<span class='chip'>{i}{html.escape(text)}</span>"


def kpi(icon: str, value: str, label: str, color: str, delay: float = 0) -> str:
    return (f"<div class='kpi' style='animation-delay:{delay}s'><div class='ic' style='background:{color}22'>"
            f"{ic.svg(icon, color, 24, 2.4)}</div><div><div class='n' style='color:{color}'>{value}</div>"
            f"<div class='t'>{html.escape(label)}</div></div></div>")


def hero(title: str, subtitle: str) -> str:
    waves = ("<svg class='waves' viewBox='0 0 1200 40' preserveAspectRatio='none'>"
             "<path d='M0 20 Q 75 0 150 20 T 300 20 T 450 20 T 600 20 T 750 20 T 900 20 T 1050 20 T 1200 20 V40 H0Z' "
             "fill='rgba(94,234,212,.18)'/>"
             "<path d='M0 26 Q 75 8 150 26 T 300 26 T 450 26 T 600 26 T 750 26 T 900 26 T 1050 26 T 1200 26 V40 H0Z' "
             "fill='rgba(37,99,235,.25)'/></svg>")
    return (f"<div class='hero'><h1>{ic.svg('droplets', th.ACCENT, 34, 2.3)}<span class='float'>{html.escape(title)}"
            f"</span></h1><p>{html.escape(subtitle)}</p>{waves}</div>")


# ------------------------------------------------------------------ graficos SVG animados
def sparkline(values, color: str, width: int = 260, height: int = 56) -> str:
    """Linea que se dibuja sola (pathLength=100 + animacion de trazo)."""
    v = [float(x) for x in values if x is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    span = (hi - lo) or 1.0
    pts = [(i * width / (len(v) - 1), height - 6 - (x - lo) / span * (height - 12)) for i, x in enumerate(v)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = d + f" L{width},{height} L0,{height} Z"
    gid = f"g{abs(hash((color, len(v), round(v[0], 1)))) % 10**8}"
    return (f"<svg viewBox='0 0 {width} {height}' width='100%' height='{height}' preserveAspectRatio='none'>"
            f"<defs><linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{color}' "
            f"stop-opacity='.35'/><stop offset='1' stop-color='{color}' stop-opacity='0'/></linearGradient></defs>"
            f"<path d='{area}' fill='url(#{gid})'/>"
            f"<path class='draw' pathLength='100' d='{d}' fill='none' stroke='{color}' stroke-width='2.6' "
            f"stroke-linecap='round' stroke-linejoin='round'/>"
            f"<circle cx='{pts[-1][0]:.1f}' cy='{pts[-1][1]:.1f}' r='4' fill='{color}'/></svg>")


def ring(fraction: float, color: str, label: str, size: int = 74) -> str:
    """Anillo que se llena hasta `fraction` (0-1) con el texto al centro."""
    pct = max(0.0, min(1.0, fraction)) * 100
    return (f"<svg viewBox='0 0 42 42' width='{size}' height='{size}'>"
            f"<circle cx='21' cy='21' r='15.9' fill='none' stroke='rgba(255,255,255,.08)' stroke-width='4.5'/>"
            f"<circle class='ring-fill' cx='21' cy='21' r='15.9' fill='none' stroke='{color}' stroke-width='4.5' "
            f"stroke-linecap='round' pathLength='100' stroke-dasharray='{pct:.1f} 100' transform='rotate(-90 21 21)'/>"
            f"<text x='21' y='23.5' text-anchor='middle' font-size='8' font-weight='800' fill='{th.TEXT}'>"
            f"{html.escape(label)}</text></svg>")


def donut(parts: dict[str, float], colors: dict[str, str], center: str, size: int = 170) -> str:
    """Dona animada; parts: etiqueta -> valor."""
    total = sum(parts.values()) or 1
    segs, offset = [], 25.0
    for k, v in parts.items():
        frac = 100 * v / total
        if frac <= 0:
            continue
        segs.append(f"<circle class='ring-fill' cx='21' cy='21' r='15.9' fill='none' stroke='{colors[k]}' "
                    f"stroke-width='5.5' pathLength='100' stroke-dasharray='{frac:.2f} {100 - frac:.2f}' "
                    f"stroke-dashoffset='{offset:.2f}'/>")
        offset -= frac
    return (f"<svg viewBox='0 0 42 42' width='{size}' height='{size}'>"
            f"<circle cx='21' cy='21' r='15.9' fill='none' stroke='rgba(255,255,255,.06)' stroke-width='5.5'/>"
            + "".join(segs) +
            f"<text x='21' y='21' text-anchor='middle' font-size='7' font-weight='900' fill='{th.TEXT}'>{center}</text>"
            f"<text x='21' y='27' text-anchor='middle' font-size='3' fill='{th.MUTED}'>cuerpos de agua</text></svg>")


def bars(items: list[tuple[str, float, str]], unit: str = "", max_value: float | None = None) -> str:
    """Barras horizontales que crecen al aparecer; items: (etiqueta, valor, color)."""
    m = max_value or max((abs(v) for _, v, _ in items), default=1) or 1
    rows = []
    for i, (lab, v, color) in enumerate(items):
        w = 100 * abs(v) / m
        rows.append(f"<div style='margin:8px 0'><div style='display:flex;justify-content:space-between;font-size:.9rem'>"
                    f"<span>{html.escape(lab)}</span><b>{v:,.0f}{unit}</b></div>"
                    f"<div class='bar'><span style='width:{w:.1f}%;background:{color};animation-delay:{i * .08:.2f}s'>"
                    f"</span></div></div>")
    return "".join(rows)


def pulse_dot(color: str, size: int = 14) -> str:
    return (f"<svg width='{size * 2}' height='{size * 2}' viewBox='0 0 20 20' style='vertical-align:middle'>"
            f"<circle class='pulse' cx='10' cy='10' r='6' fill='{color}' opacity='.6'/>"
            f"<circle cx='10' cy='10' r='4' fill='{color}'/></svg>")


def nav_icon_css(key: str, icons_: list[str], color: str = th.TEXT) -> str:
    """Iconos Lucide para las opciones de un control segmentado (por posicion)."""
    sel = '[data-testid="stMarkdownContainer"] p'
    return ic.css_rules([(f".st-key-{key} button:nth-of-type({i + 1}) {sel}", n, color, 17)
                         for i, n in enumerate(icons_)])
