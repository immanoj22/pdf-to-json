"""Step 7 Part 0: synthetic CPU smokes for the optional classical-ML packages.

Each candidate fits a tiny deterministic synthetic binary problem and predicts one held-out
synthetic sample. No PDF, gold, cache or book data is read. Results are runtime evidence only;
nothing is wired into the pipeline. Usage: python step7_smoke.py
"""

import hashlib
import json
import platform
import time
from importlib.metadata import distribution, version
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "experiments/out/step7"


def synthetic():
    rng = np.random.default_rng(7)
    x = rng.normal(size=(64, 2))
    y = (x[:, 0] + x[:, 1] > 0).astype(int)
    return x, y, np.array([[2.0, 2.0]]), 1


def licenses(name):
    dist = distribution(name)
    files = [
        f for f in dist.files or () if "LICEN" in f.name.upper() or "COPYING" in f.name.upper()
    ]
    return {
        str(f): hashlib.sha256(Path(dist.locate_file(f)).read_bytes()).hexdigest() for f in files
    }


def smoke(name, package, fit):
    x, y, sample, expected = synthetic()
    started = time.perf_counter()
    predicted = int(fit(x, y).predict(sample)[0])
    return {
        "candidate": name,
        "package": package,
        "version": version(package),
        "license_files_sha256": licenses(package),
        "python": platform.python_version(),
        "device": "cpu",
        "synthetic_sample": sample.tolist(),
        "expected": expected,
        "predicted": predicted,
        "passed": predicted == expected,
        "seconds_fit_and_predict": round(time.perf_counter() - started, 4),
        "note": "Runtime smoke only; no accuracy claim and no pipeline use.",
    }


def sklearn_fit(x, y):
    from sklearn.linear_model import LogisticRegression

    return LogisticRegression(random_state=0).fit(x, y)


def lightgbm_fit(x, y):
    import lightgbm

    model = lightgbm.LGBMClassifier(
        n_estimators=20, min_child_samples=2, random_state=0, n_jobs=1, verbose=-1
    )
    return model.fit(x, y)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = [
        smoke("scikit-learn", "scikit-learn", sklearn_fit),
        smoke("lightgbm", "lightgbm", lightgbm_fit),
    ]
    results.append(
        {
            "package": "scipy",
            "version": version("scipy"),
            **{"license_files_sha256": licenses("scipy")},
        }
    )
    (OUT / "smoke_classical_ml.json").write_text(json.dumps(results, indent=1) + "\n", "utf-8")
    for row in results[:2]:
        print(
            row["candidate"],
            row["version"],
            "passed" if row["passed"] else "FAILED",
            row["seconds_fit_and_predict"],
        )


if __name__ == "__main__":
    main()
