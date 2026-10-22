set -x
cd /c/coeik/projects/pdf_book_converter
export OMP_THREAD_LIMIT=1
for b in art_therapy_index immigrant_children medical_anatomy spanish_us_history; do
  python experiments/step16_run.py run --book $b --out final
  python experiments/step16_run.py proof --book $b --out final
  python experiments/step16_run.py compare --book $b --out final
done
python experiments/step16_run.py run --book statistics --out final
python experiments/step16_run.py proof --book statistics --out final
python experiments/step16_archives.py
echo GATES_QUEUE_DONE
