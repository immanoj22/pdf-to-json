"""Append the Step 2b review section and create one fresh-repository commit."""

import json
from pathlib import Path
from xml.etree import ElementTree

from dulwich import porcelain
from dulwich.repo import Repo
from reference_paths import reference_path

root = Path(__file__).resolve().parents[1]
out = root / "experiments/out/step2b"
tests = json.loads((out / "test_run.json").read_text("utf-8"))
full = json.loads((out / "full_book.json").read_text("utf-8"))
fixtures = json.loads((out / "fixture_gate.json").read_text("utf-8"))
oldcheck = json.loads(
    (root / "docs/step2b_old_project_verification.json").read_text("utf-8")
)
manifest = json.loads((root / "docs/step2b_move_manifest.json").read_text("utf-8"))
assert tests["exit_code"] == 0 and full["passing"] and len(fixtures) == 9
assert all(
    case["passing"]
    and case["expected_missing_token_count"] == case["expected_extra_token_count"] == 0
    for case in fixtures
)
assert not oldcheck["changed_protected_files"]
assert full["node_token_count"] == 495751 and full["retained_line_count"] == 85034
suite = ElementTree.parse(out / "pytest.xml").getroot()[0]
assert (
    int(suite.attrib["errors"])
    == int(suite.attrib["failures"])
    == int(suite.attrib["skipped"])
    == 0
)
oldrepo = Repo(str(reference_path("old_root")))
assert oldrepo.head().decode() == manifest["old_head"]
oldstatus = porcelain.status(oldrepo)
expected_deleted = {e["source"] for e in manifest["move"] if "git_blob" in e}
actual = {p.decode().replace("\\", "/") for p in oldstatus.unstaged}
assert actual == expected_deleted, (
    actual - expected_deleted,
    expected_deleted - actual,
)
assert not any(oldstatus.staged.values())
checks = json.loads((out / "relocation_checks.json").read_text("utf-8"))
assert not checks["missing_links"]
text = f"""
## Step 2b - housekeeping and multilingual decision

Moved the 180 Git-identified Step 1/2 files and 1,520 generated cache files into the new project. Python package/tests/pyproject/lock are in backend/; frontend/ contains only a README placeholder. The new root has its own README, Git repository and fresh Python 3.14.8 venv. Existing environments, old root README/start.ps1, user archives and both old applications stayed in place. [Exact move list](step2b_move_list.md), [Git/timestamp/hash manifest](step2b_move_manifest.json).

External reference reads now use experiments/references.toml or BOOK_CONVERTER environment overrides; src has no absolute reference paths. Local links and package imports point to the new folder. Venvs, caches, bytecode and model weights are ignored.

Settings accepts OCR language codes per job (default spa/eng) and per region, with an empty language-pack registry. OcrEngine remains an interface. Spans and semantic nodes have optional script and text_direction (ltr/rtl/ttb), default None; no Latin/LTR inference is introduced. The Unicode benchmark regex is unchanged. [Ledger notes](ledger.md) record that CJK without spaces needs a different token rule later; none is implemented now.

| Fresh-venv gate | Result |
|---|---|
| pytest | **{suite.attrib["tests"]} passed**, zero skips/failures/errors |
| Seven Spanish + two regression fixtures | **0 missing / 0 extra on all nine** |
| Full 758-page book | **495,751 retained tokens**, 0 missing / 0 extra |
| Line accounting | **92,228 - 7,194 = 85,034** |
| Ruff / dependency check / local links | Pass |
| Old source/config/docs/assets/tests/profile references | **1,309 hashes unchanged** |

Old Git HEAD is unchanged; its only tracked differences are the 180 authorized moves. Source/reference hash comparison excludes rebuildable environments/build/cache outputs: the all-file attempt encountered an OS-unreadable .run build dependency (.pth). None of those runtime files was moved or modified. [Old-project verification](step2b_old_project_verification.json), [gate evidence](../experiments/out/step2b/fixture_gate.json).

**Step 2b only. Stop for review.**
"""
report = root / "docs/step2_report.md"
existing = report.read_text("utf-8")
assert "\n## Step 2b" not in existing, "Step 2b already documented"
report.write_text(existing + text, "utf-8")
assert not (root / ".git").exists(), "New repository unexpectedly initialized already"
porcelain.init(str(root))
repo = Repo(str(root))
paths = []
for p in root.rglob("*"):
    if not p.is_file():
        continue
    rel = p.relative_to(root)
    if any(
        part
        in {
            ".git",
            ".venv",
            ".cache",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            "page_cache",
        }
        or part.endswith(".egg-info")
        for part in rel.parts
    ):
        continue
    if p.suffix in {
        ".pyc",
        ".pyo",
        ".safetensors",
        ".pt",
        ".pth",
        ".ckpt",
        ".onnx",
        ".gguf",
    }:
        continue
    paths.append(rel.as_posix())
assert not any(p.startswith(("book_xml_backend/", "book_xml_frontend/")) for p in paths)
porcelain.add(repo, paths=paths)
commit = porcelain.commit(
    repo,
    message=b"Step 2b: separate project and configurable multilingual evidence",
    author=b"Codex <codex@openai.com>",
    committer=b"Codex <codex@openai.com>",
)
print("New-repo commit:", commit.decode())
print("Tracked files:", len(paths))
print("Status:", porcelain.status(repo))
