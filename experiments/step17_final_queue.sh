#!/usr/bin/env bash
# Step 17 final runs and measurements, in order; each step logs to out/step17/final_logs.
set -u
cd "$(dirname "$0")"
PY=../.venv/Scripts/python
LOG=out/step17/final_logs
mkdir -p "$LOG"
export PYTHONIOENCODING=utf-8
run() {
  local name
  name=$(echo "${*:2}" | tr ' /\\.' '____' | cut -c1-80)
  echo "== ${*:2} $(date +%H:%M)" | tee -a "$LOG/queue.log"
  "$@" >> "$LOG/$name.log" 2>&1
  echo "   exit $?" | tee -a "$LOG/queue.log"
}

# Runs: continuity (equation input), final archive, book JSON; book 2 with its cover OCR'd.
for b in art_therapy_index medical_anatomy spanish_us_history; do
  run $PY step17_run.py run --book $b --out final
done
run $PY step17_run.py run --book statistics --out final
run $PY step17_ocr_cover.py run --out final

# Gates: I1-I7 and line ownership; stage comparison with Step 16.
for b in art_therapy_index medical_anatomy spanish_us_history; do
  run $PY step17_run.py proof --book $b --out final
  run $PY step17_run.py compare --book $b --out final
done
run $PY step17_run.py proof --book statistics --out final
run $PY step17_ocr_cover.py proof --out final
