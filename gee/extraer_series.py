# %% [markdown]
# # Uma - extraccion de series en Earth Engine (P1)
#
# Pegar en Google Colab celda por celda (cada `# %%` es una celda).
# Produce los 3 CSV que lee el motor: bodies.csv, series.csv, suspects.csv.
#
# Antes de correr:
#   1. Cuenta de Earth Engine con un proyecto de Google Cloud registrado.
#   2. Cambiar PROJECT abajo.
#   3. Completar BODIES con los cuerpos de agua elegidos y sus gemelas de control.
#      Verificar coordenadas y radio en code.earthengine.google.com (capa JRC max_extent).
#   4. Verificar los IDs de los datasets en el catalogo: las versiones cambian.

# %%
# !pip install -q earthengine-api pandas
import ee
import pandas as pd

PROJECT = "TU-PROYECTO-DE-GOOGLE-CLOUD"  # <- cambiar   
ee.Authenticate()
ee.Initialize(project=PROJECT)

YEARS = list(range(1985, 2022))  # JRC YearlyHistory llega hasta 2021

# body_id, nombre, lat, lon, radio en metros que cubre el cuerpo de agua, gemela de control, departamento
BODIES = [
    # Ejemplo: verificar coordenadas antes de usar
    ("poopo", "Lago Poopo", -18.80, -67.10, 30000, "CTRL_POOPO", "Oruro"),
    # ("CTRL_POOPO", "Gemela de control de Poopo", lat, lon, radio, "", "Oruro"),
    # ... 4 cuerpos de agua (uno con causa climatica esperada) + sus gemelas
]

# %%
JRC_YEARLY = ee.ImageCollection("JRC/GSW1_4/YearlyHistory")
CHIRPS = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
ERA5 = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR")
BASINS = ee.FeatureCollection("WWF/HydroSHEDS/v1/Basins/hybas_8")
HANSEN = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")  # usar la version mas reciente
BURNED = ee.ImageCollection("MODIS/061/MCD64A1")
HA = ee.Image.pixelArea().divide(1e4)


def basin_for(point):
    """Subcuenca HydroBASINS nivel 8 que contiene el punto.

    Ojo: es la subcuenca local, no toda el area aguas arriba. Para el MVP basta;
    para cuencas grandes, unir las subcuencas aguas arriba con NEXT_DOWN.
    """
    return BASINS.filterBounds(point).first().geometry()


def water_series(geom):
    def per_year(y):
        img = JRC_YEARLY.filter(ee.Filter.eq("year", y)).first()
        wc = img.select("waterClass")
        water = HA.updateMask(wc.gte(2))   # 2 estacional, 3 permanente
        nodata = HA.updateMask(wc.eq(0))   # 0 sin dato (nubes, huecos de Landsat 7)
        total = HA.reduceRegion(ee.Reducer.sum(), geom, 30, maxPixels=1e10).get("area")
        w = water.reduceRegion(ee.Reducer.sum(), geom, 30, maxPixels=1e10).get("area")
        nd = nodata.reduceRegion(ee.Reducer.sum(), geom, 30, maxPixels=1e10).get("area")
        return ee.Feature(None, {"year": y, "water_ha": w, "nodata_pct": ee.Number(nd).divide(total).multiply(100)})
    fc = ee.FeatureCollection(ee.List(YEARS).map(per_year))
    return pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])


def climate_series(basin):
    def per_year(y):
        y = ee.Number(y)
        start, end = ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y.add(1), 1, 1)
        p = CHIRPS.filterDate(start, end).sum().reduceRegion(ee.Reducer.mean(), basin, 5566, maxPixels=1e10).get("precipitation")
        t = (ERA5.filterDate(start, end).select("temperature_2m").mean()
             .reduceRegion(ee.Reducer.mean(), basin, 11132, maxPixels=1e10).get("temperature_2m"))
        return ee.Feature(None, {"year": y, "precip_mm": p, "temp_c": ee.Number(t).subtract(273.15)})
    fc = ee.FeatureCollection(ee.List(YEARS).map(per_year))
    return pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])


def forest_loss_series(basin):
    """Hectareas de bosque perdido por ano en la cuenca (Hansen, 2001 en adelante)."""
    grouped = (HA.addBands(HANSEN.select("lossyear"))
               .reduceRegion(ee.Reducer.sum().group(groupField=1, groupName="ly"), basin, 100,
                             maxPixels=1e11, tileScale=4).get("groups").getInfo())
    rows = [{"year": 2000 + g["ly"], "value": g["sum"]} for g in grouped if g["ly"] > 0]
    return pd.DataFrame(rows, columns=["year", "value"])


def burned_series(basin):
    """Hectareas quemadas por ano en la cuenca (MODIS MCD64A1, 2001 en adelante)."""
    def per_year(y):
        img = BURNED.filter(ee.Filter.calendarRange(y, y, "year")).select("BurnDate").max()
        v = HA.updateMask(img.gt(0)).reduceRegion(ee.Reducer.sum(), basin, 500, maxPixels=1e10).get("area")
        return ee.Feature(None, {"year": y, "value": v})
    fc = ee.FeatureCollection(ee.List([y for y in YEARS if y >= 2001]).map(per_year))
    return pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])


# %%
# ONI de NOAA: promedio anual de la anomalia trimestral
oni = pd.read_csv("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt", sep=r"\s+")
oni = oni.groupby("YR")["ANOM"].mean().rename("oni").reset_index().rename(columns={"YR": "year"})

# %%
bodies, series, suspects = [], [], []
for body_id, name, lat, lon, radius, ctrl, dept in BODIES:
    print("Procesando", name)
    pt = ee.Geometry.Point([lon, lat])
    area = pt.buffer(radius)
    basin = basin_for(pt)

    w = water_series(area)
    # anos con muchos huecos subestiman el agua: se descartan y se interpolan
    w.loc[w.nodata_pct > 20, "water_ha"] = None
    w["water_ha"] = w["water_ha"].interpolate(limit_direction="both")

    s = w.merge(climate_series(basin), on="year").merge(oni, on="year")
    s.insert(0, "body_id", body_id)
    series.append(s)

    for sus_name, fn in [("forest_loss_ha", forest_loss_series), ("burned_ha", burned_series)]:
        d = fn(basin)
        d = d.set_index("year").reindex(YEARS, fill_value=0).reset_index()  # antes de 2001 = 0
        d.insert(0, "body_id", body_id)
        d.insert(2, "suspect", sus_name)
        suspects.append(d)

    bodies.append(dict(body_id=body_id, name=name, lat=lat, lon=lon, kind="natural",
                       control_id=ctrl, department=dept))

pd.DataFrame(bodies).to_csv("bodies.csv", index=False)
pd.concat(series).to_csv("series.csv", index=False)
pd.concat(suspects).to_csv("suspects.csv", index=False)
print("Listo: descargar bodies.csv, series.csv, suspects.csv y ponerlos en data/real/")

# %% [markdown]
# ## Siguientes sospechosos (sabado 17:00-22:00)
# - Agricultura con riego: NDVI de Landsat/HLS en epoca seca (jul-sep) sobre la cuenca -> `dry_crop_ha`
# - Mineria y agua artificial: assets de MapBiomas Bolivia en Earth Engine -> `mining_ha`, `artificial_water_ha`
# - Urbano: GHSL o VIIRS Black Marble -> `urban_ha`
# Cada uno es solo otra funcion que devuelve (year, value) y se agrega a la lista de arriba.
