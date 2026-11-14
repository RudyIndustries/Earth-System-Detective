"""Navegacion entre vistas: la vista activa y el cuerpo de agua elegido viven en session_state."""
from __future__ import annotations

import streamlit as st

VIEWS = ["Panorama", "Mapa", "Monitoreo", "Ficha", "Vigilancia"]
ICONS = ["layout-dashboard", "map", "list", "scan-search", "flame"]


def init() -> None:
    if "goto" in st.session_state:  # pedido de cambio de vista desde un boton
        st.session_state.nav = st.session_state.pop("goto")
    st.session_state.setdefault("nav", VIEWS[0])
    st.session_state.setdefault("sel", None)


def go(view: str, body_id: str | None = None) -> None:
    if body_id is not None:
        st.session_state.sel = body_id
    st.session_state.goto = view
    st.rerun()


def open_button(body_id: str, key: str, label: str = "Ver ficha") -> None:
    if st.button(label, key=key, width="stretch"):
        go("Ficha", body_id)
