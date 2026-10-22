cd /c/coeik/projects/pdf_book_converter
export OMP_THREAD_LIMIT=1
C=experiments/out/step16/benchmark/config_tess.json
# Equivalence sample: two seeded pages per book, all degradations, re-run on the frozen producer.
python - <<'P' > experiments/out/step16/benchmark/equivalence_pages.txt
import json, random
m = json.load(open("experiments/out/step16/benchmark/sample_manifest.json"))
for book, row in m["books"].items():
    for p in random.Random(f"1600:equivalence:{book}").sample([r["page"] for r in row["selected"]], 2):
        print(book, p)
P
while read book page; do
  python experiments/step16_benchmark.py --config $C --book $book --page $page --workers 2
done < experiments/out/step16/benchmark/equivalence_pages.txt
python experiments/step16_benchmark.py --config $C --workers 2 --missing-only --overlays
python experiments/step16_benchmark.py --config experiments/out/step16/benchmark/config_main.json --workers 1 --limit 6 --degradation clean --degradation 200dpi --missing-only
echo BENCH_QUEUE_DONE
