"""Corre el motor sobre una carpeta de CSV y escribe results.json para la app.

Uso:
  python run_engine.py                 # datos de prueba (data/sample)
  python run_engine.py data/real 2005  # CSV reales, periodo base hasta 2005
"""
import json
import sys
from pathlib import Path

import pandas as pd

from uma import engine

root = Path(__file__).resolve().parent
src = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "data" / "sample"
baseline_end = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
note = sys.argv[3] if len(sys.argv) > 3 else ""

if src.name == "sample" and not (src / "series.csv").exists():
    from uma import synthetic
    synthetic.build(src)

bodies = pd.read_csv(src / "bodies.csv", dtype={"control_id": str}).fillna({"control_id": ""})
if (src / "basins.csv").exists():  # que cuerpos de agua reciben agua por rio de otro de la lista
    up = pd.read_csv(src / "basins.csv", dtype={"upstream_bodies": str}).fillna("")[["body_id", "upstream_bodies"]]
    bodies = bodies.merge(up, on="body_id", how="left").fillna({"upstream_bodies": ""})
series = pd.read_csv(src / "series.csv")
suspects = pd.read_csv(src / "suspects.csv") if (src / "suspects.csv").exists() else \
    pd.DataFrame(columns=["body_id", "year", "suspect", "value"])

results = engine.run(bodies, series, suspects, baseline_end)
(src / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")

from uma import audit
run_id = audit.record_run(src, results, baseline_end, note)

def yn(v):
    return "n/e" if v is None else ("si" if v else "no")


for r in results:
    t = r["tests"]
    print(f"{r['body_id']:8} {r['state']:16} confianza {r['confidence']:5} "
          f"clima={yn(t['clima']['pass'])} control={yn(t['control']['pass'])} "
          f"coincidencia={yn(t['coincidencia']['pass'])}  "
          f"cambio {r['trend']['change_pct']:+.0f}%  sospechoso: {r['suspects'][0]['label'] if r['suspects'] else '-'}")
print(f"\nEscrito {src / 'results.json'}")
