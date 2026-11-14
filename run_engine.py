"""Corre el motor sobre una carpeta de CSV y escribe results.json para la app.

Uso:
  python run_engine.py                 # datos de prueba (data/sample)
  python run_engine.py data/real 2005  # CSV reales, periodo base hasta 2005
"""
import json
import sys
import math
import shutil
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
series = pd.read_csv(src / "series.csv")
suspects = pd.read_csv(src / "suspects.csv") if (src / "suspects.csv").exists() else \
    pd.DataFrame(columns=["body_id", "year", "suspect", "value"])

results = engine.run(bodies, series, suspects, baseline_end)
def safe_json(value):
    if isinstance(value, dict): return {k: safe_json(v) for k, v in value.items()}
    if isinstance(value, list): return [safe_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value): return None
    return value
results = safe_json(results)
previous = src / "history" / "results_pre_validation_v2.json"
if (src / "results.json").exists() and not previous.exists():
    previous.parent.mkdir(exist_ok=True)
    shutil.copy2(src / "results.json", previous)
(src / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")

from uma import audit
run_id = audit.record_run(src, results, baseline_end, note)
from uma import report
report.write(src, bodies, series, suspects, results, baseline_end)

for r in results:
    t = r["tests"]
    print(f"{r['body_id']:8} {r['state']:16} confianza {r['confidence']:5} "
          f"clima={'si' if t['clima']['pass'] else 'no'} control={'si' if t['control']['pass'] else 'no'} "
          f"coincidencia={'si' if t['coincidencia']['pass'] else 'no'}  "
          f"cambio {r['trend']['change_pct']:+.0f}%  sospechoso: {r['suspects'][0]['label'] if r['suspects'] else '-'}")
print(f"\nEscrito {src / 'results.json'}")
