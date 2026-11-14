"""Monitoreo: filtros y tarjetas por cuerpo de agua; la tabla completa queda como descarga."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import data
import nav
import theme as th
import ui


def _row(r: dict, kind: str) -> dict:
    f = data.fires_for(r["body_id"]) if kind != "Barrido nacional" else None
    top = next((s for s in r.get("suspects", []) if not s.get("indirect")), None)
    return {"id": r["body_id"], "Estado": r["state"], "Cuerpo de agua": r["name"], "Analisis": kind,
            "Confianza": r["confidence"], "Pruebas": f"{r['n_pass']}/3", "Cambio %": round(r["trend"]["change_pct"]),
            "Clima explica %": data.share_pct(r), "Sospechoso principal": top["label"] if top else "",
            "Evidencia": top["evidence"] if top else "",
            "Incendios 7 dias": "" if not f else ("ALERTA" if f["alerta"] else "normal"),
            "Region": data.region(r["lat"], r["lon"]), "lat": r["lat"], "lon": r["lon"]}


def render(results: list[dict], national: list[dict]) -> None:
    ui.md(ui.heading("list", "Monitoreo de cuerpos de agua"))
    ctrl = data.controls(results)
    df = pd.DataFrame([_row(r, "Gemela de control" if r["body_id"] in ctrl and r["state"] != "Huella humana"
                            else "Completo") for r in results] + [_row(n, "Barrido nacional") for n in national])

    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        states = c1.pills("Estado", list(th.STATES), selection_mode="multi", default=list(th.STATES), key="f_state")
        kinds = c2.pills("Analisis", sorted(df.Analisis.unique()), selection_mode="multi",
                         default=["Completo", "Barrido nacional"] if national else ["Completo"], key="f_kind")
        region = c3.pills("Region", sorted(df.Region.unique()), selection_mode="multi",
                          default=sorted(df.Region.unique()), key="f_region")
        q = st.text_input("Buscar", placeholder="Nombre del cuerpo de agua", label_visibility="collapsed")
    f = df[df.Estado.isin(states or []) & df.Analisis.isin(kinds or []) & df.Region.isin(region or [])]
    if q:
        f = f[f["Cuerpo de agua"].str.contains(q, case=False)]
    f = f.sort_values(["Estado", "Cambio %"], key=lambda c: c.map(th.SEVERITY) if c.name == "Estado" else c)

    cnt = f.Estado.value_counts()
    ui.md("<div class='legend'>" + "".join(f"{ui.pill(s)}<b style='margin-right:10px'>{int(cnt.get(s, 0))}</b>"
                                          for s in th.STATES) + "</div>")

    full = f[f.Analisis != "Barrido nacional"]
    by_id = {r["body_id"]: r for r in results}
    for start in range(0, len(full), 4):
        cols = st.columns(4, gap="small")
        for col, (_, row) in zip(cols, full.iloc[start:start + 4].iterrows()):
            r = by_id[row["id"]]
            color = th.state_color(r["state"])
            with col, st.container(border=True):
                ui.md(f"<div style='font-weight:800'>{row['Cuerpo de agua'].split(' (')[0]}</div>"
                      f"<div style='margin:6px 0'>{ui.pill(r['state'])}</div>"
                      f"<div style='font-size:1.5rem;font-weight:900;color:{color}'>{row['Cambio %']:+d}%</div>"
                      + ui.sparkline(r["observed"], color, height=44)
                      + ui.chip(f"{row['Confianza']} · {row['Pruebas']} pruebas", "gauge"))
                nav.open_button(r["body_id"], f"mon_{r['body_id']}")

    nat = f[f.Analisis == "Barrido nacional"]
    if len(nat):
        st.write("")
        with st.container(border=True):
            ui.md(ui.heading("scan", f"Barrido nacional: {len(nat)} lagunas", 3, th.NATURAL))
            worst = nat.sort_values("Cambio %").head(12)
            ui.md(ui.bars([(n, -c, th.state_color(e)) for n, c, e in
                           zip(worst["Cuerpo de agua"], worst["Cambio %"], worst["Estado"]) if c < 0], "%", 100))
            ui.md("<div class='muted'>Las 12 que mas agua perdieron. Diagnostico rapido: filtro para decidir donde "
                  "hacer el analisis completo.</div>")

    with st.expander("Tabla completa y descarga"):
        show = f.drop(columns=["id", "lat", "lon"])
        styled = show.style.apply(lambda c: [f"background-color:{th.state_color(v)};color:{th.INK};font-weight:700"
                                             for v in c], subset=["Estado"])
        st.dataframe(styled, hide_index=True, width="stretch", height=420)
        st.download_button("Descargar CSV", show.to_csv(index=False).encode("utf-8"), "monitoreo.csv", "text/csv",
                           key="dl_monitor")
