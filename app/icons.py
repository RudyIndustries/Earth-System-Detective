"""Iconos Lucide (lucide-static 0.460.0, licencia ISC) para la interfaz de Uma.

Los SVG estan en app/icons/ para no depender de internet. Dos formas de uso:
  svg(nombre, color, tamano)      SVG en linea, para HTML propio (tarjetas, etiquetas, titulos)
  css_rules([(selector, nombre, color, tamano)])
                                  iconos para botones, pestanas y opciones de Streamlit, que no aceptan
                                  SVG en su texto: se dibujan con ::before sobre el elemento.
"""
from __future__ import annotations

import re
import urllib.parse
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parent / "icons"


@lru_cache(maxsize=None)
def _raw(name: str) -> str:
    t = (DIR / f"{name}.svg").read_text(encoding="utf-8")
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    return " ".join(t.split())


def svg(name: str, color: str = "currentColor", size: int = 18, stroke: float = 2.2, valign: int = -3) -> str:
    t = _raw(name)
    t = re.sub(r'class="[^"]*"', "", t)
    t = t.replace('width="24"', f'width="{size}"').replace('height="24"', f'height="{size}"')
    t = t.replace('stroke="currentColor"', f'stroke="{color}"').replace('stroke-width="2"', f'stroke-width="{stroke}"')
    return t.replace("<svg", f'<svg style="vertical-align:{valign}px;flex-shrink:0"', 1)


def data_uri(name: str, color: str, size: int = 18, stroke: float = 2.2) -> str:
    t = svg(name, color, size, stroke)
    return "url(\"data:image/svg+xml;utf8," + urllib.parse.quote(t) + "\")"


def css_rules(rules) -> str:
    """rules: lista de (selector CSS, nombre del icono, color, tamano en px)."""
    out = []
    for sel, name, color, size in rules:
        out.append(f"{sel}::before {{content:''; display:inline-block; width:{size}px; height:{size}px; "
                   f"margin-right:8px; vertical-align:-{max(size // 5, 2)}px; background:{data_uri(name, color, size)} "
                   f"no-repeat center / contain;}}")
    return "<style>" + "\n".join(out) + "</style>"
