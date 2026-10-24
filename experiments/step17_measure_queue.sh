#!/usr/bin/env bash
# Step 17 measurements on the final runs (after step17_final_queue.sh).
set -u
cd "$(dirname "$0")"
PY=../.venv/Scripts/python
LOG=out/step17/final_logs
export PYTHONIOENCODING=utf-8
run() {
  local name
  name=$(echo "${*:2}" | tr ' /\.' '____' | cut -c1-80)
  echo "== ${*:2} $(date +%H:%M)" | tee -a "$LOG/measure.log"
  "$@" >> "$LOG/$name.log" 2>&1
  echo "   exit $?" | tee -a "$LOG/measure.log"
}
mkdir -p out/step17/final/lossless
for b in spanish_us_history immigrant_children art_therapy_index medical_anatomy statistics; do
  A=$($PY -c "import json;print(json.load(open('out/step17/final/performance/$b.json'))['run']['output'])")
  J=$($PY -c "import json;print(json.load(open('out/step17/final/performance/$b.json'))['run']['book_json'])")
  run $PY step17_lossless.py --json "$J/book.json" --archive "$A" --out out/step17/final/lossless/$b.json
  run $PY step17_json_eval.py --book $b --json "$J/book.json" --archive "$A"
  run $PY step17_cleanup_counts.py --book $b --json "$J/book.json"
done
run $PY step17_source_gates.py
run $PY step17_parity.py
run $PY step17_workers.py
run $PY step17_report_data.py --out final
