# Uma - detective de huella humana en el agua de Bolivia

NASA Space Apps 2026, reto *Be an Earth System Trend Detective*.
Compara la evolución del agua con referencias climáticas, detecta anomalías con incertidumbre
y evalúa indicios de presión humana. No asigna automáticamente una causa a un residuo.

La implementación conservadora y sus límites están documentados en [VALIDACION_MODELO.md](VALIDACION_MODELO.md).
Los resultados actuales están en [data/real/validation/REPORT.md](data/real/validation/REPORT.md).

## Estructura

| Carpeta | Quién | Qué |
|---|---|---|
| `gee/extraer_series.py` | P1 Datos | Celdas para Colab: Earth Engine → `bodies.csv`, `series.csv`, `suspects.csv` |
| `uma/engine.py` | P2 Modelo | Motor: tendencia, 3 pruebas, confianza, descomposición, sospechosos, estado |
| `uma/synthetic.py` | P2/P3 | Datos de prueba ficticios con el mismo formato |
| `run_engine.py` | P2 | CSV → `results.json` |
| `app/app.py` | P3 Interfaz | Streamlit: mapa, alertas, tarjeta, modo técnico |

## Arranque

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run_engine.py
.venv\Scripts\streamlit run app/app.py
```

## Datos de NASA

| Uso en Uma | Dataset NASA | Acceso | Estado |
|---|---|---|---|
| Lluvia y temperatura por laguna, 1985-2024 | NASA POWER (PRECTOTCORR, T2M de MERRA-2) | API sin clave: `python -m uma.nasa_power` | Extraído en `data/real/nasa_power.csv` |
| Superficie de agua, 1985-2024 | Landsat 5/7/8/9 C2 L2 (NASA/USGS), MNDWI en época seca | Earth Engine `LANDSAT/L*0*/C02/T1_L2` | Requiere proyecto GEE |
| Imágenes antes/después y capa en vivo | Landsat 5/7/8/9 | Earth Engine | Requiere proyecto GEE |
| Incendios por año en la cuenca | MODIS MCD64A1 | Earth Engine `MODIS/061/MCD64A1` | Requiere proyecto GEE |
| Focos de calor, casi tiempo real | FIRMS (MODIS y VIIRS) | Earth Engine `FIRMS` | Capa en vivo del mapa 3D |
| Riego (verde en época seca) | Landsat NDVI | Earth Engine | Requiere proyecto GEE |

Fuentes externas para validar y para lo que NASA no cubre: JRC Global Surface Water (validación del agua,
hasta 2021), Hansen GFC 2025 (desmonte, derivado de Landsat), GHSL (ciudad), HydroBASINS (cuencas), ONI de NOAA
(El Niño, extraído en `data/real/oni.csv`). Con `--climate chirps` se usa CHIRPS + ERA5-Land en lugar de NASA POWER.

Todos los IDs de Earth Engine se verificaron en el catálogo público el 2026-11-14.

## Enlaces para el equipo

**Imágenes NASA en tiempo real y antes/después (sin programar)**

- [NASA Worldview](https://worldview.earthdata.nasa.gov): imágenes diarias MODIS y VIIRS casi en tiempo real; el modo
  *Compare* pone dos fechas lado a lado con deslizador (antes/después).
- [FIRMS, mapa de incendios](https://firms.modaps.eosdis.nasa.gov/map/): focos de calor de las últimas horas.
  [Clave de la API](https://firms.modaps.eosdis.nasa.gov/api/) · [Ficha en Earthdata](https://www.earthdata.nasa.gov/data/tools/firms)
- [LandsatLook (USGS)](https://landsatlook.usgs.gov): todas las escenas Landsat desde 1972, para elegir el antes y el después.
- [EarthExplorer (USGS)](https://earthexplorer.usgs.gov): descarga de escenas Landsat completas.
- [Earthdata Search](https://search.earthdata.nasa.gov): buscador de todos los datos NASA ([cuenta Earthdata](https://urs.earthdata.nasa.gov)).
- [NASA GIBS](https://nasa-gibs.github.io/gibs-api-docs/): las mismas capas de Worldview como teselas para un mapa web.
- [OPERA DSWx](https://www.earthdata.nasa.gov/data/projects/opera): agua superficial casi en tiempo real (Landsat y Sentinel, desde 2023).
- [HLS](https://www.earthdata.nasa.gov/data/projects/hls): Landsat + Sentinel-2 armonizados, una imagen cada 2-3 días.

**Datasets que usa Uma (ficha en el catálogo de Earth Engine)**

| Uso | Dataset | Enlace |
|---|---|---|
| Agua, imágenes antes/después, capa en vivo | Landsat 5 | [LANDSAT/LT05/C02/T1_L2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LT05_C02_T1_L2) |
| | Landsat 7 | [LANDSAT/LE07/C02/T1_L2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LE07_C02_T1_L2) |
| | Landsat 8 | [LANDSAT/LC08/C02/T1_L2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2) |
| | Landsat 9 | [LANDSAT/LC09/C02/T1_L2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T1_L2) |
| Imágenes densas (opcional) | HLS Landsat / Sentinel | [HLSL30](https://developers.google.com/earth-engine/datasets/catalog/NASA_HLS_HLSL30_v002) · [HLSS30](https://developers.google.com/earth-engine/datasets/catalog/NASA_HLS_HLSS30_v002) |
| Focos de calor en vivo | FIRMS | [FIRMS](https://developers.google.com/earth-engine/datasets/catalog/FIRMS) |
| Incendios por año | MODIS MCD64A1 | [MODIS/061/MCD64A1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD64A1) |
| Lluvia y temperatura | NASA POWER | [Visor](https://power.larc.nasa.gov/data-access-viewer/) · [API](https://power.larc.nasa.gov/docs/services/api/) |
| Validación del agua | JRC Global Surface Water | [YearlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_YearlyHistory) · [visor](https://global-surface-water.appspot.com) |
| Desmonte | Hansen GFC 2025 | [catálogo](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13) · [visor](https://glad.earthengine.app/view/global-forest-change) |
| Ciudad | GHSL superficie construida | [catálogo](https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_S) |
| Cuencas | HydroBASINS | [catálogo](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_8) · [HydroSHEDS](https://www.hydrosheds.org/products/hydrobasins) |
| Relieve (opcional) | NASADEM | [NASA/NASADEM_HGT/001](https://developers.google.com/earth-engine/datasets/catalog/NASA_NASADEM_HGT_001) |
| El Niño | ONI de NOAA | [tabla](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php) · [texto](https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt) |
| Para programar | Earth Engine Code Editor | [code.earthengine.google.com](https://code.earthengine.google.com) |

## Datos reales (Earth Engine)

1. Registrar un proyecto en https://code.earthengine.google.com/register (uso no comercial).
2. Autenticar una vez: `.venv\Scripts\earthengine authenticate`
3. Revisar `config/bodies.csv` (cuerpos de agua, radio y gemela de control).
4. Extraer todo a `data/real/` (series, sospechosos, imágenes Landsat antes/después, ONI):

```bash
.venv\Scripts\python -m uma.gee_extract --project TU-PROYECTO
.venv\Scripts\python run_engine.py data/real 2000
```

5. Revisar `data/real/check.csv`: si la superficie máxima de agua de un área es 0 o absurda, corregir las
   coordenadas o el radio en `config/bodies.csv` y volver a correr con `--only <body_id>`.

La app usa `data/real` automáticamente cuando existe `results.json`. Para la capa Landsat en vivo sobre el mapa 3D:

```bash
set UMA_GEE_PROJECT=TU-PROYECTO && .venv\Scripts\streamlit run app/app.py
```

## Mapa 3D

Relieve real (AWS Terrain Tiles) con imagen satelital (Esri) o, con Earth Engine activo, el Landsat de época seca
del año elegido con el agua JRC encima, generado en vivo. Cada cuerpo de agua es una columna: color = estado,
altura = % de agua perdida. Clic en una columna → el mapa vuela hasta ahí y abajo aparece la tarjeta con el
comparador antes/después.

## Contrato de datos (P1 → P2)

`bodies.csv`: `body_id, name, lat, lon, kind, control_id, department`
(`control_id` = body_id de la gemela; vacío en las gemelas.)

`series.csv`: `body_id, year, water_ha, precip_mm, temp_c, oni` (una fila por año, sin huecos)

`suspects.csv`: `body_id, year, suspect, value`. Nombres de `suspect` reconocidos:
`forest_loss_ha, burned_ha, dry_crop_ha, pasture_ha, mining_ha, urban_ha, artificial_water_ha`.

## Cómo decide el motor

1. **Calidad y validación.** Excluye agua imputada del ajuste y compara climatología, OLS, Ridge y regresión con memoria residual AR(1), usando solo cortes dentro del período base. Si la calidad o la validación son insuficientes, lo comunica.
2. **Anomalía.** Contrasta tendencia residual y efecto material, exige persistencia bajo una banda bootstrap aproximada y corrige los contrastes entre cuerpos de agua. Publica la cobertura posterior de las bandas.
3. **Control.** Una gemela es candidata hasta documentar su elegibilidad independiente. Se revisan similitud previa, error y cobertura; si falla, su prueba no se habilita.
4. **Presión.** Exige crecimiento, antecedencia y signo negativo en la asociación de cambios anuales, con corrección de Holm y contrastes temporales exploratorios.
5. **Conclusión.** No basta con aprobar dos pruebas. Hay estados de evidencia insuficiente, pérdida no explicada e indicios; la evidencia reforzada exige documentación independiente revisada. La diferencia de tendencias no se reparte numéricamente como causa humana.

La política está en `config/evidence_policy.json`; sus umbrales son provisionales y configurables. Las revisiones de controles y los eventos documentados comienzan vacíos: no se inventan confirmaciones. Los placebos en controles candidatos son exploratorios y no constituyen una tasa confirmada de falsos positivos. No hay métricas de clasificación humana contra etiquetas independientes disponibles.

La evaluación posterior usa clima observado: es retrospectiva y condicional, no un pronóstico operativo de lluvia. Las bandas no se declaran calibradas. La documentación detalla qué datos y revisiones faltan para una atribución confirmatoria.
