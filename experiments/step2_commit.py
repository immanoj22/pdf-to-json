raise SystemExit("Historical commit script disabled after relocation; use the new repository workflow.")
"""Commit the reviewed Step 2 scope once; never include user archives or old projects."""

import json
from pathlib import Path
from dulwich import porcelain
from dulwich.repo import Repo

root = Path(__file__).resolve().parents[1]
repo = Repo(str(root))
assert repo.head().decode() == "fe34f82d9bf43c8c19be696c5da5be1c43455274", (
    "Step 2 already committed or HEAD changed"
)
full = json.loads((root / "experiments/out/step2/full_book.json").read_text("utf-8"))
tests = json.loads((root / "experiments/out/step2/test_run.json").read_text("utf-8"))
assert full["passing"] and tests["exit_code"] == 0
assert (root / "docs/step2_report.md").exists()
files = [
    root / name
    for name in [
        ".gitignore",
        "AGENTS.md",
        "CLAUDE.md",
        "pyproject.toml",
        "requirements-lock.txt",
        "docs/dependencies.md",
        "docs/step2_report.md",
    ]
]
for directory in [root / "src", root / "tests"]:
    files.extend(
        p
        for p in directory.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and not any(part.endswith(".egg-info") for part in p.parts)
    )
files.extend(
    root / "experiments" / name
    for name in [
        "step2_dependencies.py",
        "step2_snapshot.py",
        "step2_diagnose.py",
        "step2_segmentation_probe.py",
        "step2_final_checks.py",
        "step2_validate.py",
        "step2_report.py",
        "step2_commit.py",
    ]
)
files.extend(
    root / "experiments/out/step2" / name
    for name in [
        "dependencies.json",
        "benchmark_deviation.json",
        "fixture_gate.json",
        "old_cached_totals.json",
        "full_book.json",
        "test_run.json",
        "pytest.log",
        "pytest.xml",
    ]
)
relative = [p.relative_to(root).as_posix() for p in files]
assert all((root / name).is_file() for name in relative)
assert all(not name.startswith(("book_xml_backend/", "book_xml_frontend/")) for name in relative)
assert all(not name.endswith(".rar") for name in relative)
status = porcelain.status(repo)
assert not any(status.staged.values()), "Unexpected pre-staged changes"
porcelain.add(repo, paths=relative)
staged = porcelain.status(repo).staged
actual = {path.decode().replace("\\", "/") for names in staged.values() for path in names}
assert actual == set(relative), (actual - set(relative), set(relative) - actual)
commit = porcelain.commit(
    repo,
    message=b"Step 2: universal models, lossless evidence and token ledger",
    author=b"Codex <codex@openai.com>",
    committer=b"Codex <codex@openai.com>",
)
print("Commit:", commit.decode())
print("Files:", len(relative))
print("Remaining status:", porcelain.status(repo))
