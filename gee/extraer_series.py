# %% [markdown]
# # Uma - extraccion en Google Colab
#
# Este cuaderno ya no tiene su propia version del codigo: usa el mismo extractor que el proyecto
# (uma/gee_extract.py), para que Colab y la computadora den exactamente los mismos datos.
# Pegar en Colab celda por celda (cada `# %%` es una celda).

# %%
# !git clone https://github.com/gustavoantequerat-del/Earth-System-Detective.git
# %cd Earth-System-Detective
# !pip install -q -r requirements.txt

# %%
import ee
ee.Authenticate()
PROJECT = "nasa-app-challenge-514714"  # o el proyecto de Earth Engine de quien lo corra

# %%
# 1. cuencas de aporte y clima NASA POWER promediado en cada cuenca
# !python -m uma.upstream --project {PROJECT}
# !python -m uma.nasa_power
# 2. agua (Landsat), validacion (JRC), sospechosos, imagenes
# !python -m uma.gee_extract --project {PROJECT}
# 3. sospechosos en la cuenca de aporte completa (misma area que el clima)
# !python -m uma.suspects_upstream --project {PROJECT} --only poopo,uru_uru,concepcion,titicaca_menor,chiquitania_este
# 4. alrededores: mapa de cambios y lugares de OpenStreetMap
# !python -m uma.context --project {PROJECT}
# 5. motor de atribucion (queda registrado en data/real/uma.db)
# !python run_engine.py data/real 2000 "nota de la corrida"
