"""Uma - interfaz. Lee los resultados del motor (data/real) y del barrido nacional (data/national).

  streamlit run app/app.py
Vistas: mapa de alertas, monitoreo (tabla), ficha de un cuerpo de agua y vigilancia semanal de incendios.
"""
import datetime
import json
import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import map3d

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_real = ROOT / "data" / "real"
DATA = Path(os.environ.get("UMA_DATA") or (_real if (_real / "results.json").exists() else ROOT / "data" / "sample"))
NATDIR = ROOT / "data" / "national"
CTX = DATA / "context"

# colores vivos por estado (rojo neon, magenta, amarillo, naranja, verde)
STATE_COLORS = {
    "Huella humana": [255, 23, 68],
    "Alerta temprana": [213, 0, 249],
    "Sin explicar": [255, 214, 0],
    "Causa climatica": [255, 145, 0],
    "Intacto": [0, 230, 118],
}
STATE_ICON = {"Huella humana": "🔴", "Alerta temprana": "🟣", "Sin explicar": "🟡", "Causa climatica": "🟠", "Intacto": "🟢"}
SEVERITY = {"Huella humana": 0, "Alerta temprana": 1, "Sin explicar": 2, "Causa climatica": 3, "Intacto": 4}
STATE_ACTION = {
    "Huella humana": "Prevenir: controlar la actividad sospechosa, proteger la cuenca, restaurar.",
    "Causa climatica": "Adaptarse: cosecha de agua, reservorios, planes de sequia.",
    "Alerta temprana": "Actuar ya, cuando proteger todavia es barato.",
    "Sin explicar": "Revisar: el agua cae y el clima no alcanza a explicarlo, pero no hay pruebas para acusar.",
    "Intacto": "Seguimiento.",
}
VIEWS = ["🗺️ Mapa de alertas", "📋 Monitoreo", "🔎 Ficha del cuerpo de agua", "🔥 Vigilancia semanal"]


def hexc(rgb):
    return "#%02x%02x%02x" % tuple(rgb[:3])


st.set_page_config(page_title="Uma", page_icon="💧", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 3.2rem; padding-bottom: 1rem; max-width: 100%;}
.pill {display:inline-block; padding:6px 16px; border-radius:999px; font-weight:800; font-size:1.05rem;
       color:#111; box-shadow:0 0 14px rgba(255,255,255,.15); margin:2px 6px 2px 0;}
.pill-big {font-size:1.6rem; padding:10px 24px;}
.kpi {border-radius:14px; padding:12px 16px; color:#111; font-weight:800; text-align:center;
      box-shadow:0 0 18px rgba(0,0,0,.35);}
.kpi .n {font-size:2.1rem; line-height:1;}
.kpi .t {font-size:.9rem; opacity:.85;}
.legend {display:flex; flex-wrap:wrap; gap:14px; align-items:center; font-size:1rem; margin:6px 0 2px 0;}
.legend i {display:inline-block; width:18px; height:18px; border-radius:50%; margin-right:6px; vertical-align:-3px;
           box-shadow:0 0 8px currentColor;}
.title {font-size:2rem; font-weight:900; margin:0;}
.sub {opacity:.75; margin-top:-4px;}
</style>""", unsafe_allow_html=True)


def pill(state, big=False):
    c = hexc(STATE_COLORS[state])
    return f"<span class='pill{' pill-big' if big else ''}' style='background:{c}'>{STATE_ICON[state]} {state}</span>"


# ------------------------------------------------------------------ datos
results_path = DATA / "results.json"
if not results_path.exists():
    st.error(f"No existe {results_path}. Corre primero: python run_engine.py")
    st.stop()
results = json.loads(results_path.read_text(encoding="utf-8"))
by_id = {r["body_id"]: r for r in results}
controls = {r["control_id"] for r in results if r.get("control_id")}
national = json.loads((NATDIR / "results.json").read_text(encoding="utf-8")) if (NATDIR / "results.json").exists() else []
artificial_pts = (json.loads((NATDIR / "agua_artificial.json").read_text(encoding="utf-8"))
                  if (NATDIR / "agua_artificial.json").exists() else None)
weekly = json.loads((DATA / "alertas_semanales.json").read_text(encoding="utf-8")) \
    if (DATA / "alertas_semanales.json").exists() else None


def load_places(body_id):
    f = CTX / f"{body_id}_lugares.json"
    return json.loads(f.read_text(encoding="utf-8")) if body_id and f.exists() else []


@st.cache_data
def load_suspects():
    f = DATA / "suspects.csv"
    return pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["body_id", "year", "suspect", "value", "area"])


def load_meta(body_id):
    f = CTX / f"{body_id}_meta.json"
    needed = [CTX / f"{body_id}_{k}.png" for k in ("antes", "despues", "cambios")]
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() and all(p.exists() for p in needed) else None


SUSPECT_PLACE = {"mining_ha": ["Mina o cantera"], "urban_ha": ["Ciudad o pueblo", "Industria"],
                 "population": ["Ciudad o pueblo"], "night_lights": ["Industria", "Ciudad o pueblo"],
                 "artificial_water_ha": ["Represa o canal"], "mining_water_ha": ["Mina o cantera"],
                 "dry_crop_ha": ["Represa o canal"]}
SUSPECT_CHANGE = {"mining_ha": "mining", "mining_water_ha": "mining", "urban_ha": "urban", "population": "urban",
                  "night_lights": "urban", "agri_ha": "agri", "dry_crop_ha": "agri", "pasture_ha": "pasture",
                  "forest_loss_ha": "forest_loss", "burned_ha": "forest_loss"}


def share_pct(r):
    """Cuanto de la perdida explica el clima, en %; vacio si no hubo perdida relevante; tope 200%."""
    sh = r.get("climate_share")
    if sh is None or r["trend"]["change_pct"] > -10:
        return None
    return round(100 * max(min(sh, 2.0), -1.0))


def fires_for(body_id):
    if not weekly:
        return None
    for x in weekly["rows"]:
        if x["body_id"] == body_id:
            return x
    return None


# ------------------------------------------------------------------ navegacion
if "goto" in st.session_state:  # un clic en el mapa o en la tabla pide cambiar de vista
    st.session_state.view = st.session_state.pop("goto")
st.session_state.setdefault("view", VIEWS[0])
st.session_state.setdefault("sel", None)

with st.sidebar:
    st.markdown("<div class='title'>💧 Uma</div><div class='sub'>Detective de huella humana en el agua de Bolivia</div>",
                unsafe_allow_html=True)
    view = st.radio("Vista", VIEWS, key="view", label_visibility="collapsed")
    st.divider()
    show_ctrl = st.toggle("Mostrar gemelas de control", value=False)

visible = [r for r in results if show_ctrl or r["body_id"] not in controls or r["state"] == "Huella humana"]
options = [r["body_id"] for r in visible]
if st.session_state.sel not in options:
    st.session_state.sel = None
if DATA.name == "sample":
    st.warning("Datos de prueba ficticios. No usar estos numeros en el pitch.")


def go_detail(body_id):
    st.session_state.sel = body_id
    st.session_state.goto = VIEWS[2]


# ================================================================== VISTA: MAPA
def view_map():
    with st.sidebar:
        st.subheader("Capas del mapa")
        live_ok = map3d.ee_ready()
        modes = (["Agua natural y artificial (MapBiomas)", "Landsat + agua (Earth Engine)"] if live_ok else []) \
            + ["Satelite actual (Esri)"]
        mode = st.radio("Fondo sobre el relieve 3D", modes)
        year = st.slider("Ano", 1985, 2025, 2024, disabled=not mode.startswith(("Agua", "Landsat")))
        fires = st.checkbox("🔥 Focos de calor NASA FIRMS (7 dias)", value=False, disabled=not live_ok)
        show_art = st.checkbox("💠 Puntos de agua artificial (celeste neon)", value=artificial_pts is not None,
                               disabled=artificial_pts is None)
        show_nat = st.checkbox(f"🔵 Barrido nacional ({len(national)} lagunas)", value=bool(national),
                               disabled=not national)
        if not live_ok:
            st.caption("Capas de Earth Engine apagadas: falta autenticar Earth Engine.")

    # tarjetas de conteo por estado
    allst = [r["state"] for r in visible] + ([n["state"] for n in national] if show_nat else [])
    cnt = pd.Series(allst).value_counts()
    cols = st.columns(len(STATE_COLORS))
    for c, (stt, rgb) in zip(cols, STATE_COLORS.items()):
        c.markdown(f"<div class='kpi' style='background:{hexc(rgb)}'><div class='n'>{int(cnt.get(stt, 0))}</div>"
                   f"<div class='t'>{STATE_ICON[stt]} {stt}</div></div>", unsafe_allow_html=True)

    texture = map3d.ESRI
    if mode.startswith("Agua"):
        with st.spinner(f"Pidiendo a Earth Engine el agua de {year}..."):
            texture = map3d.live_texture(year, "agua", fires, datetime.date.today().isoformat()) or map3d.ESRI
    elif mode.startswith("Landsat"):
        with st.spinner(f"Pidiendo a Earth Engine el Landsat de {year}..."):
            texture = map3d.live_texture(year, "landsat", fires, datetime.date.today().isoformat()) or map3d.ESRI

    rows = [{"body_id": r["body_id"], "name": r["name"], "label": r["name"].split(" (")[0],
             "lat": r["lat"], "lon": r["lon"], "state": r["state"], "color": STATE_COLORS[r["state"]],
             "change": f"{r['trend']['change_pct']:+.0f}%", "loss": max(0.0, -r["trend"]["change_pct"]) + 5}
            for r in visible]

    def zguess(lat, lon):  # altura aproximada para que los puntos no queden bajo el relieve
        return 4300 if lon < -65.6 and lat < -14.5 else 700

    nat_rows = []
    if national and show_nat:
        for n in national:
            nat_rows.append({"name": f"{n['name']} · barrido nacional · {n.get('ha', 0):,} ha", "lat": n["lat"],
                             "lon": n["lon"], "z": zguess(n["lat"], n["lon"]), "state": n["state"],
                             "change": f"{n['trend']['change_pct']:+.0f}%", "color": STATE_COLORS[n["state"]],
                             "radius": 1500 + 60 * (n.get("ha", 0) ** 0.5)})
    art_rows = []
    if artificial_pts and show_art:
        for a in artificial_pts["points"]:
            r_m = (a["ha"] * 1e4 / 3.1416) ** 0.5
            art_rows.append({"name": f"{a['tipo']} · {a['ha']:,.0f} ha", "state": "Agua artificial",
                             "change": f"MapBiomas Agua {artificial_pts['year']}", "lat": a["lat"], "lon": a["lon"],
                             "z": zguess(a["lat"], a["lon"]), "r": max(r_m, 250), "r_glow": max(r_m, 250) * 4})

    current = by_id.get(st.session_state.sel)
    deck = map3d.build_deck(rows, current, texture, load_places(st.session_state.sel), nat_rows, art_rows)
    event = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key="map3d", height=720)
    picked = (event.selection.get("objects", {}) or {}).get("cuerpos") if event else None
    if picked and picked[0]["body_id"] != st.session_state.sel:
        st.session_state.sel = picked[0]["body_id"]
        st.rerun()

    legend = "".join(f"<span><i style='background:{hexc(c)};color:{hexc(c)}'></i>{s}</span>" for s, c in STATE_COLORS.items())
    legend += (f"<span><i style='background:#{map3d.NATURAL_HEX};color:#{map3d.NATURAL_HEX}'></i>Agua natural</span>"
               f"<span><i style='background:#{map3d.ARTIFICIAL_HEX};color:#{map3d.ARTIFICIAL_HEX}'></i>Agua artificial</span>")
    st.markdown(f"<div class='legend'>{legend}</div>", unsafe_allow_html=True)
    st.caption("Columnas: cuerpos de agua con analisis completo (altura = % de agua perdida). Puntos con borde blanco: "
               "barrido nacional. Clic en una columna para volar hasta ahi · Ctrl + arrastrar para girar · rueda para zoom.")

    left, right = st.columns([3, 2])
    with left:
        if current:
            r = current
            top = r["suspects"][0]["label"] if r["suspects"] else "sin sospechoso medido"
            st.markdown(f"### {r['name']}")
            st.markdown(pill(r["state"], big=True), unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("Agua perdida", f"{r['trend']['change_pct']:+.0f}%")
            m2.metric("Confianza", r["confidence"], f"{r['n_pass']} de 3 pruebas", delta_color="off")
            m3.markdown("<div style='font-size:.875rem;opacity:.8'>Sospechoso principal</div>"
                        f"<div style='font-size:1.15rem;font-weight:800'>{top}</div>", unsafe_allow_html=True)
            st.info(STATE_ACTION[r["state"]])
            b1, b2 = st.columns(2)
            if b1.button("🔎 Abrir ficha completa", type="primary", use_container_width=True):
                go_detail(r["body_id"])
                st.rerun()
            if b2.button("🗺️ Volver a Bolivia completa", use_container_width=True):
                st.session_state.sel = None
                st.rerun()
        else:
            st.markdown("### Haz clic en una columna del mapa")
            st.caption("O elige un cuerpo de agua en la lista de la derecha.")
    with right:
        st.markdown("### 🚨 Donde actuar primero")
        for r in sorted(visible, key=lambda r: (SEVERITY[r["state"]], r["trend"]["change_pct"])):
            if st.button(f"{STATE_ICON[r['state']]} {r['name']} · {r['trend']['change_pct']:+.0f}% · {r['state']}",
                         key=f"go_{r['body_id']}", use_container_width=True):
                st.session_state.sel = r["body_id"]
                st.rerun()


# ================================================================== VISTA: MONITOREO
def view_monitor():
    st.markdown("## 📋 Monitoreo de cuerpos de agua")
    rows = []
    for r in results:
        f = fires_for(r["body_id"])
        rows.append({
            "id": r["body_id"], "Estado": r["state"], "Cuerpo de agua": r["name"],
            "Analisis": "Gemela de control" if r["body_id"] in controls and r["state"] != "Huella humana" else "Completo",
            "Confianza": r["confidence"], "Pruebas": f"{r['n_pass']}/3",
            "Cambio %": round(r["trend"]["change_pct"]),
            "Clima explica %": share_pct(r),
            "Sospechoso principal": r["suspects"][0]["label"] if r["suspects"] else "",
            "Evidencia": r["suspects"][0]["evidence"] if r["suspects"] else "",
            "Incendios 7 dias": "" if not f else (("🔥 ALERTA " if f["alerta"] else "") +
                                                  " · ".join(f"{k}: {a['focos']}" for k, a in f["areas"].items())),
            "Calidad datos": (r.get("data_quality") or {}).get("level", ""),
            "Superficie ha": round(r.get("baseline_mean_ha", 0)), "lat": r["lat"], "lon": r["lon"]})
    for n in national:
        rows.append({
            "id": n["body_id"], "Estado": n["state"], "Cuerpo de agua": n["name"], "Analisis": "Barrido nacional",
            "Confianza": n["confidence"], "Pruebas": f"{n['n_pass']}/3", "Cambio %": round(n["trend"]["change_pct"]),
            "Clima explica %": share_pct(n),
            "Sospechoso principal": n["suspects"][0]["label"] if n.get("suspects") else "",
            "Evidencia": n["suspects"][0]["evidence"] if n.get("suspects") else "",
            "Incendios 7 dias": "", "Calidad datos": "", "Superficie ha": n.get("ha", 0), "lat": n["lat"], "lon": n["lon"]})
    df = pd.DataFrame(rows)

    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    estados = c1.multiselect("Estado", list(STATE_COLORS), default=list(STATE_COLORS))
    tipos = c2.multiselect("Analisis", sorted(df.Analisis.unique()), default=sorted(df.Analisis.unique()))
    q = c3.text_input("Buscar por nombre")
    min_loss = c4.number_input("Perdida minima %", value=0, step=10)
    f = df[df.Estado.isin(estados) & df.Analisis.isin(tipos)]
    if q:
        f = f[f["Cuerpo de agua"].str.contains(q, case=False)]
    if min_loss:
        f = f[f["Cambio %"] <= -abs(min_loss)]
    f = f.sort_values(["Estado", "Cambio %"], key=lambda c: c.map(SEVERITY) if c.name == "Estado" else c)

    cnt = f.Estado.value_counts()
    st.markdown(" ".join(pill(s) + f"<b>{int(cnt.get(s, 0))}</b>&nbsp;&nbsp;" for s in STATE_COLORS), unsafe_allow_html=True)

    show = f.drop(columns=["id"]).copy()
    show["Estado"] = show.Estado.map(lambda s: f"{STATE_ICON[s]} {s}")

    def paint(col):
        return [f"background-color:{hexc(STATE_COLORS[v.split(' ', 1)[1]])};color:#111;font-weight:700" for v in col]
    styled = show.style.apply(paint, subset=["Estado"]).format({"Clima explica %": lambda v: "" if pd.isna(v) else f"{v:.0f}"})
    ev = st.dataframe(styled, hide_index=True, use_container_width=True, height=560, on_select="rerun",
                      selection_mode="single-row", key="monitor_table")
    st.caption("Selecciona una fila de analisis completo para abrir su ficha. El barrido nacional es un diagnostico "
               "rapido (MapBiomas Agua, NASA POWER, uso del suelo en 5 km y gemela regional sintetica).")
    sel_rows = ev.selection.get("rows", []) if ev else []
    if sel_rows:
        rid = f.iloc[sel_rows[0]]["id"]
        if rid in by_id:
            go_detail(rid)
            st.rerun()
        else:
            st.info("Este cuerpo de agua es del barrido nacional: todavia no tiene analisis completo.")
    st.download_button("⬇️ Descargar la tabla (CSV)", f.drop(columns=["id"]).to_csv(index=False).encode("utf-8"),
                       "uma_monitoreo.csv", "text/csv")


# ================================================================== VISTA: VIGILANCIA
def view_watch():
    st.markdown("## 🔥 Vigilancia semanal de incendios (NASA FIRMS)")
    if not weekly:
        st.info("Todavia no se corrio la vigilancia: python -m uma.alerts --project TU-PROYECTO --dry-run")
        return
    hot = [x for x in weekly["rows"] if x["alerta"]]
    st.markdown(f"Semana al **{weekly['week_end']}** · revisado {weekly['checked_at'][:16].replace('T', ' ')} · "
                f"avisos: {weekly['notified']}")
    if hot:
        st.error(f"🔥 {len(hot)} cuerpos de agua con alerta de incendio esta semana")
    else:
        st.success("Sin alertas de incendio esta semana: los focos estan dentro de lo normal.")
    rows = []
    for x in weekly["rows"]:
        for nm, a in x["areas"].items():
            rows.append({"Cuerpo de agua": x["name"], "Estado": f"{STATE_ICON.get(x['state'], '')} {x['state']}",
                         "Area": "Cerca de la laguna" if nm == "cerca" else "Toda la cuenca",
                         "Focos esta semana": a["focos"], "Normal para esta semana": a["normal"],
                         "Alerta": "🔥 SI" if a["alerta"] else "no"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("Alerta si un cuerpo de agua en riesgo tiene al menos 5 focos y el doble de lo normal (promedio de la "
               "misma semana en los 5 anos anteriores). Prueba retroactiva: la semana al 2019-08-25 dispara la alerta "
               "en la laguna de la Chiquitania este (163 focos cerca contra 1.2 normales).")
    import sqlite3
    if (DATA / "uma.db").exists():
        con = sqlite3.connect(DATA / "uma.db")
        try:
            h = pd.read_sql("SELECT week_end AS semana, body_id, area, fires AS focos, normal, alert AS alerta, "
                            "notified AS aviso FROM operational_alerts ORDER BY week_end DESC", con)
            st.markdown("### Historial")
            st.dataframe(h, hide_index=True, use_container_width=True)
        except Exception:
            pass
        con.close()


# ================================================================== VISTA: FICHA
def view_detail():
    def _pick():
        st.session_state.sel = st.session_state.pick
    if st.session_state.sel:
        st.session_state.pick = st.session_state.sel
    sel = st.selectbox("Cuerpo de agua", options, format_func=lambda i: f"{STATE_ICON[by_id[i]['state']]} {by_id[i]['name']}",
                       key="pick", on_change=_pick)
    r = by_id[sel]
    st.markdown(f"## {r['name']}")
    st.markdown(pill(r["state"], big=True), unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cambio desde el periodo base", f"{r['trend']['change_pct']:+.0f}%")
    c2.metric("Tendencia (Sen)", f"{r['trend']['sen_ha_per_year']:+.1f} ha/ano",
              help=f"Mann-Kendall p={r['trend']['p']:.3f}, corregido por pruebas multiples p={r['trend']['p_holm']:.3f}")
    c3.metric("Confianza en la huella humana", r["confidence"], f"{r['n_pass']} de 3 pruebas", delta_color="off")
    c4.markdown("<div style='font-size:.875rem;opacity:.8'>Sospechoso principal</div>"
                f"<div style='font-size:1.25rem;font-weight:800'>{r['suspects'][0]['label'] if r['suspects'] else '-'}</div>",
                unsafe_allow_html=True)
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
        st.caption(f"El clima (lluvia, temperatura y El Nino) explica el {100 * min(r['climate_share'], 9.99):.0f}% de la "
                   f"perdida entre {r['years'][0]}-{r['baseline_end']} y los ultimos 5 anos.")

    tabs = st.tabs(["🛰️ Antes y despues", "📈 Clima y causas", "💠 Agua natural vs artificial",
                    "🔍 Pruebas y sospechosos", "📍 Alrededores", "🧾 Auditoria"])
    with tabs[0]:
        meta = load_meta(sel)
        views = ["La laguna"] + (["Los alrededores: que aparecio"] if meta else [])
        vw = st.radio("Vista", views, horizontal=True, index=len(views) - 1, label_visibility="collapsed")
        if vw.startswith("Los alrededores"):
            ya, yb = meta["years"]
            legend = {k: dict(v, ha=meta["changes_ha"].get(k, 0)) for k, v in meta["legend"].items()}
            components.html(map3d.before_after_html(CTX / f"{sel}_antes.png", CTX / f"{sel}_despues.png", str(ya),
                                                    str(yb), changes=CTX / f"{sel}_cambios.png", legend=legend,
                                                    height=620), height=700)
            st.caption(f"Ventana de {meta['window_km']:.0f} km. Colores: lo que no existia en {ya} y si en {yb} "
                       "(MapBiomas Bolivia; bosque perdido de Hansen). Fuera de Bolivia solo se ve el bosque perdido.")
        else:
            img_dir = DATA / "img"
            yrs = sorted({int(p.stem.split("_")[-1]) for p in img_dir.glob(f"{sel}_*.png")
                          if p.stem.split("_")[-1].isdigit()}) if img_dir.exists() else []
            if len(yrs) >= 2:
                ca, cb = st.columns(2)
                ya = ca.select_slider("Antes", yrs, value=yrs[0], key="ya")
                yb = cb.select_slider("Despues", yrs, value=yrs[-1], key="yb")
                components.html(map3d.before_after_html(img_dir / f"{sel}_{ya}.png", img_dir / f"{sel}_{yb}.png",
                                                        str(ya), str(yb), img_dir / f"{sel}_{ya}_water.png",
                                                        img_dir / f"{sel}_{yb}_water.png", height=620), height=680)
                obs = dict(zip(r["years"], r["observed"]))
                if ya in obs and yb in obs:
                    st.caption(f"Agua detectada: {obs[ya]:,.0f} ha en {ya} → {obs[yb]:,.0f} ha en {yb}. "
                               "Landsat de epoca seca (junio-octubre), mediana sin nubes.")
            else:
                st.caption("Sin imagenes para este cuerpo de agua.")

    with tabs[1]:
        g1, g2 = st.columns([3, 2])
        with g1:
            st.markdown("#### Observado contra lo que explica el clima")
            ts = pd.DataFrame({"year": r["years"], "Observado": r["observed"], "Esperado por el clima": r["expected"],
                               "oni": r["oni"]})
            long = ts.melt(id_vars=["year"], value_vars=["Observado", "Esperado por el clima"], var_name="serie",
                           value_name="ha")
            xs = alt.Scale(domain=[r["years"][0], r["years"][-1] + 1], zero=False)
            bands = alt.Chart(ts[ts.oni >= 0.5]).mark_rect(opacity=0.18, color="#ff9100").encode(
                x=alt.X("year:Q", scale=xs), x2=alt.X2("year2:Q")).transform_calculate(year2="datum.year + 1")
            lines = alt.Chart(long).mark_line(point=True, strokeWidth=3).encode(
                x=alt.X("year:Q", axis=alt.Axis(format="d"), title=None, scale=xs),
                y=alt.Y("ha:Q", title="Superficie de agua (ha)"),
                color=alt.Color("serie:N", scale=alt.Scale(range=["#9e9e9e", "#2979ff"]),
                                legend=alt.Legend(orient="bottom", title=None)),
                strokeDash=alt.condition(alt.datum.serie == "Esperado por el clima", alt.value([6, 4]), alt.value([0])))
            rule = alt.Chart(pd.DataFrame({"year": [r["baseline_end"]]})).mark_rule(color="white").encode(
                x=alt.X("year:Q", scale=xs))
            st.altair_chart(bands + lines + rule, use_container_width=True)
            st.caption(f"Franjas naranjas: anos de El Nino. Linea blanca: fin del periodo de entrenamiento ({r['baseline_end']}).")
        with g2:
            st.markdown("#### De donde viene el cambio")
            dec = pd.DataFrame([{"causa": k, "ha": v} for k, v in r["decomposition_ha"].items()])
            colors = {"Sequia y calor": "#ff9100", "El Nino": "#ffd600", "Huella humana": "#ff1744", "Sin explicar": "#9e9e9e"}
            st.altair_chart(alt.Chart(dec).mark_bar(size=34).encode(
                y=alt.Y("causa:N", sort=list(r["decomposition_ha"].keys()), title=None),
                x=alt.X("ha:Q", title="Hectareas ganadas (+) o perdidas (-)"),
                color=alt.Color("causa:N", scale=alt.Scale(domain=list(colors), range=list(colors.values())),
                                legend=None)), use_container_width=True)
            st.caption("Promedio del periodo base contra los ultimos 5 anos; las barras suman el % de arriba. "
                       "Huella humana solo con 2 o mas pruebas.")

    with tabs[2]:
        sus_all = load_suspects()
        sw = sus_all[(sus_all.body_id == sel) & sus_all.suspect.isin(["natural_water_ha", "artificial_water_ha",
                                                                      "mining_water_ha"])]
        if sw.empty or "area" not in sw:
            st.caption("Sin series de agua artificial para este cuerpo de agua.")
        else:
            areas = [x for x in ["subcuenca_local", "cuenca_aporte"] if x in set(sw.area)]
            names = {"subcuenca_local": "Cerca de la laguna", "cuenca_aporte": "Toda la cuenca de aporte"}
            ar = st.radio("Area", areas, format_func=names.get, horizontal=True, key="tend_area",
                          label_visibility="collapsed")
            w = sw[sw.area == ar].pivot_table(index="year", columns="suspect", values="value").reset_index()
            nat = pd.DataFrame({"year": r["years"], "ha": r["observed"], "serie": "Esta laguna (Landsat)"})
            if "natural_water_ha" in w:
                nat = pd.concat([nat, pd.DataFrame({"year": w.year, "ha": w.natural_water_ha,
                                                    "serie": "Agua natural del area"})])
            art = pd.DataFrame({"year": w.year, "ha": w.get("artificial_water_ha", 0) + w.get("mining_water_ha", 0)})
            xs2 = alt.Scale(domain=[1985, 2025])
            left = alt.Chart(nat).mark_line(strokeWidth=3).encode(
                x=alt.X("year:Q", axis=alt.Axis(format="d"), title=None, scale=xs2),
                y=alt.Y("ha:Q", title="Agua natural (ha)", axis=alt.Axis(titleColor="#4f7cff")),
                color=alt.Color("serie:N", scale=alt.Scale(range=["#" + map3d.NATURAL_HEX, "#4f7cff"]),
                                legend=alt.Legend(orient="bottom", title=None)))
            right = alt.Chart(art).mark_area(opacity=0.45, color="#" + map3d.ARTIFICIAL_HEX,
                                             line={"color": "#" + map3d.ARTIFICIAL_HEX, "strokeWidth": 3}).encode(
                x=alt.X("year:Q", scale=xs2),
                y=alt.Y("ha:Q", title="Agua artificial (ha)", axis=alt.Axis(titleColor="#" + map3d.ARTIFICIAL_HEX)))
            st.altair_chart(alt.layer(left, right).resolve_scale(y="independent"), use_container_width=True)
            a0, a1 = art[art.year.between(1985, 1990)].ha.mean(), art[art.year.between(2020, 2024)].ha.mean()
            st.markdown(f"<span class='pill' style='background:#{map3d.ARTIFICIAL_HEX}'>💠 Agua artificial: "
                        f"{a0:,.0f} → {a1:,.0f} ha</span> (1985-1990 contra 2020-2024)", unsafe_allow_html=True)
            st.caption("Azul oscuro: agua natural. Celeste neon (eje derecho): represas, estanques y pozas mineras "
                       "(MapBiomas Agua Bolivia, coleccion 4). Si la artificial sube mientras la natural baja, la "
                       "misma presion humana puede explicar ambas.")

    with tabs[3]:
        names = {"clima": "1. Lo que el clima no explica", "control": "2. Gemela de control",
                 "coincidencia": "3. Coincidencia en el tiempo"}
        for k, t in r["tests"].items():
            st.markdown(f"{'✅' if t['pass'] else '⬜'} **{names[k]}** — {t['detail']}")
        if r["suspects"]:
            sus = pd.DataFrame(r["suspects"])
            sus["Inseparable de"] = sus["together_with"].apply(lambda l: ", ".join(l))
            ev_color = {"fuerte": "#ff1744", "media": "#ff9100", "debil": "#616161"}
            tbl = sus.rename(columns={"label": "Sospechoso", "evidence": "Evidencia", "onset": "Empieza a crecer",
                                      "precedes": "Antecede la caida", "r2": "R2 con el residuo"})[
                ["Sospechoso", "Evidencia", "Empieza a crecer", "Antecede la caida", "R2 con el residuo", "Inseparable de"]]
            st.dataframe(tbl.style.apply(lambda c: [f"background-color:{ev_color.get(v, '')};color:white;font-weight:700"
                                                    for v in c], subset=["Evidencia"]),
                         hide_index=True, use_container_width=True)

    with tabs[4]:
        meta = load_meta(sel)
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
                near = sorted([x for x in places if x["kind"] in SUSPECT_PLACE.get(key, []) and x["name"]],
                              key=lambda x: x["dist_km"])[:3]
                if near:
                    lines.append("Lo mas cercano: " + "; ".join(
                        f"[{x['name']}]({x['osm']}) ({x['kind'].lower()}, {x['dist_km']} km)" for x in near))
                st.markdown(" · ".join(lines))
            if places:
                pdf = pd.DataFrame(places)
                st.dataframe(pdf[["kind", "name", "detail", "dist_km", "osm"]].rename(columns={
                    "kind": "Tipo", "name": "Nombre", "detail": "Detalle", "dist_km": "Distancia (km)",
                    "osm": "OpenStreetMap"}), hide_index=True, use_container_width=True,
                    column_config={"OpenStreetMap": st.column_config.LinkColumn(display_text="ver")})
            else:
                st.caption("OpenStreetMap no registra minas, industrias, ciudades ni represas con nombre en esta zona.")
        else:
            st.caption("Sin datos de alrededores. Se generan con: python -m uma.context --project TU-PROYECTO")

    with tabs[5]:
        from uma import audit
        if (DATA / "uma.db").exists():
            hist, revs, alts = audit.history(DATA, sel)
            st.caption("Cada corrida del motor queda registrada con la huella de los datos y del codigo.")
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
                outcome = c2.selectbox("Resultado", ["En revision", "Confirmado en campo", "Falso positivo",
                                                     "Requiere mas datos"])
                comment = st.text_area("Comentario")
                if st.form_submit_button("Guardar revision") and who:
                    audit.add_review(DATA, sel, who, outcome, comment)
                    st.success("Revision guardada en la auditoria.")
                    st.rerun()
            if not revs.empty:
                st.markdown("**Revisiones**")
                st.dataframe(revs, hide_index=True, use_container_width=True)
        with st.expander("Modo tecnico"):
            st.write(f"R2 del modelo de clima (periodo base hasta {r['baseline_end']}): {r['climate_r2']:.2f}")
            st.write("Validacion con el pasado (error despues del periodo base):", r["backtest"])
            st.json(r["tests"])
            st.download_button("Descargar resultados (JSON)", results_path.read_bytes(), "uma_results.json")


{VIEWS[0]: view_map, VIEWS[1]: view_monitor, VIEWS[2]: view_detail, VIEWS[3]: view_watch}[view]()

st.caption("Uma prueba coincidencia y consistencia, no causalidad estricta. Datos: Landsat 5/7/8/9 (NASA/USGS), "
           "NASA POWER, NASA FIRMS, MODIS MCD64A1, GRACE, NASADEM, NOAA ONI, JRC Global Surface Water (validacion), "
           "MapBiomas Bolivia y MapBiomas Agua, Hansen GFC 2025, DMSP/VIIRS, WorldPop, HydroBASINS, OpenStreetMap.")
