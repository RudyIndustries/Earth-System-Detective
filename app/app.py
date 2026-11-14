"""Uma - interfaz (P3). Lee results.json que escribe run_engine.py.

  streamlit run app/app.py            # datos de prueba
  (usa data/real si existe results.json; si no, datos de prueba)
  UMA_GEE_PROJECT=mi-proyecto activa la capa Landsat en vivo
"""
import datetime
import json
import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st
import streamlit.components.v1 as components

import map3d

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_real = ROOT / "data" / "real"
DATA = Path(os.environ.get("UMA_DATA") or (_real if (_real / "results.json").exists() else ROOT / "data" / "sample"))

STATE_COLORS = {
    "Huella humana": [214, 69, 65],
    "Causa climatica": [230, 160, 40],
    "Alerta temprana": [150, 80, 200],
    "Sin explicar": [120, 120, 120],
    "Intacto": [40, 150, 200],
}
STATE_ACTION = {
    "Huella humana": "Prevenir: controlar la actividad sospechosa, proteger la cuenca, restaurar.",
    "Causa climatica": "Adaptarse: cosecha de agua, reservorios, planes de sequia.",
    "Alerta temprana": "Actuar ya, cuando proteger todavia es barato.",
    "Sin explicar": "Revisar: el agua cae mas de lo que explica el clima, pero no hay un sospechoso medido.",
    "Intacto": "Seguimiento.",
}

st.set_page_config(page_title="Uma", layout="wide")

results_path = DATA / "results.json"
if not results_path.exists():
    st.error(f"No existe {results_path}. Corre primero: python run_engine.py")
    st.stop()
results = json.loads(results_path.read_text(encoding="utf-8"))
by_id = {r["body_id"]: r for r in results}
controls = {r["control_id"] for r in results if r.get("control_id")}

st.title("Uma")
st.caption("Detective de huella humana en el agua de Bolivia. Separa el clima (sequia, El Nino) de la accion humana.")
if DATA.name == "sample":
    st.warning("Datos de prueba ficticios. No usar estos numeros en el pitch.")

CTX = DATA / "context"


def load_places(body_id):
    f = CTX / f"{body_id}_lugares.json"
    return json.loads(f.read_text(encoding="utf-8")) if body_id and f.exists() else []


def load_meta(body_id):
    f = CTX / f"{body_id}_meta.json"
    needed = [CTX / f"{body_id}_{k}.png" for k in ("antes", "despues", "cambios")]
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() and all(p.exists() for p in needed) else None


# que tipo de lugar buscar cerca segun el sospechoso
SUSPECT_PLACE = {"mining_ha": ["Mina o cantera"], "urban_ha": ["Ciudad o pueblo", "Industria"],
                 "population": ["Ciudad o pueblo"], "night_lights": ["Industria", "Ciudad o pueblo"],
                 "artificial_water_ha": ["Represa o canal"], "dry_crop_ha": ["Represa o canal"]}
SUSPECT_CHANGE = {"mining_ha": "mining", "urban_ha": "urban", "population": "urban", "night_lights": "urban",
                  "agri_ha": "agri", "dry_crop_ha": "agri", "pasture_ha": "pasture", "forest_loss_ha": "forest_loss",
                  "burned_ha": "forest_loss"}

# ------------------------------------------------------------------ mapa 3D + alertas
show_ctrl = st.sidebar.toggle("Mostrar gemelas de control", value=False)
visible = [r for r in results if show_ctrl or r["body_id"] not in controls or r["state"] == "Huella humana"]
options = [r["body_id"] for r in visible]

st.sidebar.subheader("Capa del mapa 3D")
live_ok = map3d.ee_ready()
layer_opts = ["Satelite actual (Esri)"] + (["Landsat en vivo (Earth Engine)"] if live_ok else [])
layer_choice = st.sidebar.radio("Textura sobre el relieve", layer_opts)
year = st.sidebar.slider("Ano de la imagen Landsat", 1985, 2024, 2021, disabled=len(layer_opts) == 1)
show_water = st.sidebar.checkbox("Agua detectada ese ano (JRC, hasta 2021)", value=True, disabled=len(layer_opts) == 1)
show_fires = st.sidebar.checkbox("Focos de calor NASA FIRMS, ultimos 7 dias", value=False, disabled=len(layer_opts) == 1)
if not live_ok:
    st.sidebar.caption("Capa en vivo apagada: falta autenticar Earth Engine y definir UMA_GEE_PROJECT.")

if "sel" not in st.session_state or st.session_state.sel not in options:
    st.session_state.sel = None

left, right = st.columns([3, 2])
with left:
    texture = map3d.ESRI
    if layer_choice.startswith("Landsat"):
        with st.spinner(f"Pidiendo a Earth Engine el Landsat de {year}..."):
            texture = map3d.live_texture(year, show_water, show_fires,
                                         datetime.date.today().isoformat()) or map3d.ESRI
    rows = [{
        "body_id": r["body_id"], "name": r["name"], "lat": r["lat"], "lon": r["lon"], "state": r["state"],
        "color": STATE_COLORS[r["state"]], "change": f"{r['trend']['change_pct']:+.0f}%",
        "loss": max(0.0, -r["trend"]["change_pct"]) + 3,
    } for r in visible]
    current = by_id.get(st.session_state.sel)
    event = st.pydeck_chart(map3d.build_deck(rows, current, texture, load_places(st.session_state.sel)),
                            on_select="rerun",
                            selection_mode="single-object", key="map3d", height=560)
    picked = (event.selection.get("objects", {}) or {}).get("cuerpos") if event else None
    if picked:
        new_sel = picked[0]["body_id"]
        if new_sel != st.session_state.sel:
            st.session_state.sel = new_sel
            st.rerun()
    st.markdown(" ".join(f"<span style='color:rgb{tuple(c)}'>■</span> {s}" for s, c in STATE_COLORS.items())
                + " · altura de la columna = % de agua perdida · Ctrl + arrastrar para girar",
                unsafe_allow_html=True)
    if st.session_state.sel and st.button("Volver a Bolivia completa"):
        st.session_state.sel = None
        st.rerun()

with right:
    SEVERITY = {"Huella humana": 0, "Alerta temprana": 1, "Sin explicar": 2, "Causa climatica": 3, "Intacto": 4}
    st.subheader("Alertas: donde actuar primero")
    # una gemela tambien puede resultar con huella humana: se muestra igual (hallazgo del sistema)
    alerts = [r for r in results if r["state"] in ("Alerta temprana", "Huella humana")]
    alerts.sort(key=lambda r: (SEVERITY[r["state"]], r["trend"]["change_pct"]))
    if not alerts:
        st.caption("Ningun cuerpo de agua con huella humana o alerta temprana.")
    for r in alerts:
        sus = r["suspects"][0]["label"] if r["suspects"] else "-"
        tag = " (era gemela de control)" if r["body_id"] in controls else ""
        if st.button(f"🔴 {r['name']}{tag} — {r['state']}, confianza {r['confidence'].lower()} · {sus}",
                     key=f"al_{r['body_id']}"):
            st.session_state.sel = r["body_id"]
            st.rerun()
    st.subheader("Todos los cuerpos de agua")
    for r in sorted([r for r in results if r["body_id"] not in controls],
                    key=lambda r: (SEVERITY[r["state"]], r["trend"]["change_pct"])):
        c = STATE_COLORS[r["state"]]
        if st.button(f"{r['name']}: {r['trend']['change_pct']:+.0f}% · {r['state']} · confianza {r['confidence'].lower()}",
                     key=f"all_{r['body_id']}"):
            st.session_state.sel = r["body_id"]
            st.rerun()

# ------------------------------------------------------------------ tarjeta
st.divider()
def _pick():
    st.session_state.sel = st.session_state.pick


if st.session_state.sel:
    st.session_state.pick = st.session_state.sel
sel = st.selectbox("Cuerpo de agua (o haz clic en una columna del mapa)", options,
                   format_func=lambda i: by_id[i]["name"], key="pick", on_change=_pick)
r = by_id[sel]

st.header(r["name"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Cambio desde el periodo base", f"{r['trend']['change_pct']:+.0f}%")
c2.metric("Tendencia (Sen)", f"{r['trend']['sen_ha_per_year']:+.1f} ha/ano",
          help=f"Mann-Kendall p={r['trend']['p']:.3f}, corregido por pruebas multiples p={r['trend']['p_holm']:.3f}")
c3.markdown(f"<div style='font-size:0.875rem'>Estado</div><div style='font-size:1.6rem;color:rgb{tuple(STATE_COLORS[r['state']])}'>{r['state']}</div>", unsafe_allow_html=True)
c4.metric("Confianza en la huella humana", r["confidence"], f"{r['n_pass']} de 3 pruebas", delta_color="off")
st.info(STATE_ACTION[r["state"]])
q = r.get("data_quality") or {}
if q.get("level") == "baja":
    st.warning(f"Calidad de datos baja: la serie de agua de Landsat coincide poco con JRC (r = {q['r_jrc']:.2f}). "
               "Puede haber agua bajo vegetacion o algas que el indice no detecta. Tomar este veredicto con cautela.")
elif q.get("r_jrc") is not None:
    st.caption(f"Calidad de la serie de agua: {q['level']} (Landsat vs JRC r = {q['r_jrc']:.2f}"
               + (f"; anos interpolados: {', '.join(map(str, q['interpolated_years']))}" if q.get('interpolated_years') else "")
               + ").")
if r.get("climate_share") is not None:
    st.caption(f"El clima (lluvia, temperatura y El Nino) explica el {100 * min(r['climate_share'], 9.99):.0f}% de la perdida "
               f"entre {r['years'][0]}-{r['baseline_end']} y los ultimos 5 anos.")

st.subheader("Antes y despues")
meta = load_meta(sel)
views = ["La laguna"] + (["Los alrededores: que aparecio"] if meta else [])
view = st.radio("Vista", views, horizontal=True, index=len(views) - 1, label_visibility="collapsed")
if view.startswith("Los alrededores"):
    ya, yb = meta["years"]
    legend = {k: dict(v, ha=meta["changes_ha"].get(k, 0)) for k, v in meta["legend"].items()}
    components.html(map3d.before_after_html(
        CTX / f"{sel}_antes.png", CTX / f"{sel}_despues.png", str(ya), str(yb),
        changes=CTX / f"{sel}_cambios.png", legend=legend), height=600)
    st.caption(f"Ventana de {meta['window_km']:.0f} km alrededor del cuerpo de agua (circulo celeste). Colores: lo que no "
               f"existia en {ya} y si en {yb} (MapBiomas Bolivia; bosque perdido de Hansen). Fuera de Bolivia solo "
               "se ve el bosque perdido.")
else:
    img_dir = DATA / "img"
    img_years = sorted({int(f.stem.split("_")[-1]) for f in img_dir.glob(f"{sel}_*.png")
                        if f.stem.split("_")[-1].isdigit()}) if img_dir.exists() else []
    if len(img_years) >= 2:
        ca, cb = st.columns(2)
        ya = ca.select_slider("Antes", img_years, value=img_years[0], key="ya")
        yb = cb.select_slider("Despues", img_years, value=img_years[-1], key="yb")
        components.html(map3d.before_after_html(
            img_dir / f"{sel}_{ya}.png", img_dir / f"{sel}_{yb}.png", str(ya), str(yb),
            img_dir / f"{sel}_{ya}_water.png", img_dir / f"{sel}_{yb}_water.png"), height=560)
        obs = dict(zip(r["years"], r["observed"]))
        if ya in obs and yb in obs:
            st.caption(f"Agua detectada: {obs[ya]:,.0f} ha en {ya} → {obs[yb]:,.0f} ha en {yb}. "
                       "Imagenes Landsat de epoca seca (junio-octubre), mediana sin nubes.")
    else:
        st.caption("Sin imagenes para este cuerpo de agua. Se generan con: python -m uma.gee_extract --project TU-PROYECTO")

g1, g2 = st.columns([3, 2])
with g1:
    st.subheader("Observado contra lo que explica el clima")
    ts = pd.DataFrame({"year": r["years"], "Observado": r["observed"], "Esperado por el clima": r["expected"],
                       "oni": r["oni"]})
    long = ts.melt(id_vars=["year"], value_vars=["Observado", "Esperado por el clima"], var_name="serie", value_name="ha")
    nino = ts[ts.oni >= 0.5]
    xs = alt.Scale(domain=[r["years"][0], r["years"][-1] + 1], zero=False)
    bands = alt.Chart(nino).mark_rect(opacity=0.15, color="#e6a028").encode(
        x=alt.X("year:Q", scale=xs), x2=alt.X2("year2:Q")).transform_calculate(year2="datum.year + 1")
    lines = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X("year:Q", axis=alt.Axis(format="d"), title=None, scale=xs),
        y=alt.Y("ha:Q", title="Superficie de agua (ha)"),
        color=alt.Color("serie:N", legend=alt.Legend(orient="bottom", title=None)),
        strokeDash=alt.condition(alt.datum.serie == "Esperado por el clima", alt.value([5, 3]), alt.value([0])))
    base_rule = alt.Chart(pd.DataFrame({"year": [r["baseline_end"]]})).mark_rule(color="gray").encode(x=alt.X("year:Q", scale=xs))
    st.altair_chart(bands + lines + base_rule, use_container_width=True)
    st.caption(f"Franjas: anos de El Nino (ONI ≥ 0.5). Linea gris: fin del periodo de entrenamiento ({r['baseline_end']}).")

with g2:
    st.subheader("De donde viene el cambio")
    dec = pd.DataFrame([{"causa": k, "ha": v} for k, v in r["decomposition_ha"].items()])
    st.altair_chart(alt.Chart(dec).mark_bar().encode(
        y=alt.Y("causa:N", sort=list(r["decomposition_ha"].keys()), title=None),
        x=alt.X("ha:Q", title="Hectareas ganadas (+) o perdidas (-)"),
        color=alt.condition(alt.datum.ha < 0, alt.value("#d64541"), alt.value("#2896c8"))),
        use_container_width=True)
    st.caption("Cambio entre el promedio del periodo base y el de los ultimos 5 anos; las barras suman el % de arriba. "
               "Huella humana solo se asigna con 2 o mas pruebas; si no, ese residuo queda como sin explicar.")

st.subheader("Las tres pruebas")
names = {"clima": "1. Lo que el clima no explica", "control": "2. Gemela de control", "coincidencia": "3. Coincidencia en el tiempo"}
for k, t in r["tests"].items():
    st.markdown(f"{'✅' if t['pass'] else '⬜'} **{names[k]}** — {t['detail']}")

st.subheader("Auditoria de sospechosos")
if r["suspects"]:
    sus = pd.DataFrame(r["suspects"])
    sus["Inseparable de"] = sus["together_with"].apply(lambda l: ", ".join(l))
    st.dataframe(sus.rename(columns={"label": "Sospechoso", "evidence": "Evidencia", "onset": "Empieza a crecer",
                                     "precedes": "Antecede la caida", "r2": "R2 con el residuo"})
                 [["Sospechoso", "Evidencia", "Empieza a crecer", "Antecede la caida", "R2 con el residuo", "Inseparable de"]],
                 hide_index=True, use_container_width=True)
else:
    st.write("Sin capas de sospechosos para este cuerpo de agua.")

st.subheader("Que hay alrededor")
places = load_places(sel)
if meta or places:
    top = [x for x in r["suspects"] if x["evidence"] != "debil"][:2] or r["suspects"][:1]
    for sp in top:
        lines = [f"**{sp['label']}** (evidencia {sp['evidence']}, crece desde {sp['onset']})"]
        key = sp["suspect"].split("@")[0]
        ck = SUSPECT_CHANGE.get(key)
        if meta and ck and meta["changes_ha"].get(ck):
            lines.append(f"{meta['legend'][ck]['label']} en los alrededores: {meta['changes_ha'][ck]:,} ha "
                         f"entre {meta['years'][0]} y {meta['years'][1]}")
        kinds = SUSPECT_PLACE.get(key, [])
        near = sorted([x for x in places if x["kind"] in kinds and x["name"]], key=lambda x: x["dist_km"])[:3]
        if near:
            lines.append("Lo mas cercano: " + "; ".join(f"[{x['name']}]({x['osm']}) ({x['kind'].lower()}, {x['dist_km']} km)"
                                                       for x in near))
        st.markdown(" · ".join(lines))
    if places:
        pdf = pd.DataFrame(places)
        st.dataframe(pdf[["kind", "name", "detail", "dist_km", "osm"]].rename(columns={
            "kind": "Tipo", "name": "Nombre", "detail": "Detalle", "dist_km": "Distancia (km)", "osm": "OpenStreetMap"}),
            hide_index=True, use_container_width=True,
            column_config={"OpenStreetMap": st.column_config.LinkColumn(display_text="ver")})
    else:
        st.caption("OpenStreetMap no registra minas, industrias, ciudades ni represas con nombre en esta zona.")
else:
    st.caption("Sin datos de alrededores. Se generan con: python -m uma.context --project TU-PROYECTO")

st.subheader("Historial de auditoria")
from uma import audit
if (DATA / "uma.db").exists():
    hist, revs, alts = audit.history(DATA, sel)
    st.caption("Cada corrida del motor queda registrada con la huella de los datos y del codigo: "
               "cualquier veredicto se puede rastrear y repetir.")
    st.dataframe(hist, hide_index=True, use_container_width=True)
    if len(hist) > 1 and hist.iloc[0]["estado"] != hist.iloc[1]["estado"]:
        st.info(f"El veredicto cambio de **{hist.iloc[1]['estado']}** (corrida {hist.iloc[1]['corrida']}) a "
                f"**{hist.iloc[0]['estado']}** (corrida {hist.iloc[0]['corrida']}). Motivo: {hist.iloc[0]['nota']}")
    if not alts.empty:
        st.markdown("**Alertas**")
        st.dataframe(alts, hide_index=True, use_container_width=True)
    with st.form(f"review_{sel}", clear_on_submit=True):
        st.markdown("**Agregar revision humana**")
        c1, c2 = st.columns(2)
        who = c1.text_input("Quien revisa")
        outcome = c2.selectbox("Resultado", ["En revision", "Confirmado en campo", "Falso positivo", "Requiere mas datos"])
        comment = st.text_area("Comentario")
        if st.form_submit_button("Guardar revision") and who:
            audit.add_review(DATA, sel, who, outcome, comment)
            st.success("Revision guardada en la auditoria.")
            st.rerun()
    if not revs.empty:
        st.markdown("**Revisiones**")
        st.dataframe(revs, hide_index=True, use_container_width=True)
else:
    st.caption("Sin registro de auditoria todavia: se crea al correr run_engine.py.")

with st.expander("Modo tecnico"):
    st.write(f"R2 del modelo de clima (periodo base hasta {r['baseline_end']}): {r['climate_r2']:.2f}")
    st.write("Validacion con el pasado (error despues del periodo base):", r["backtest"])
    st.caption("En una gemela de control el error debe ser bajo; en un caso con huella humana el error alto es la senal.")
    st.json(r["tests"])
    st.download_button("Descargar resultados (JSON)", results_path.read_bytes(), "uma_results.json")

st.caption("Se prueba coincidencia y consistencia, no causalidad estricta. Datos: Landsat 5/7/8/9 (NASA/USGS), "
           "NASA POWER, NASA FIRMS, MODIS MCD64A1, GRACE, NOAA ONI, JRC Global Surface Water (validacion), "
           "MapBiomas Bolivia, Hansen GFC 2025, DMSP/VIIRS, WorldPop, HydroBASINS, OpenStreetMap.")
