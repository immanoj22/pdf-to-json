"""Inventory and move only provenance-verified Step 1/2 files."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
from dulwich.repo import Repo
from dulwich import porcelain

DEST = Path(__file__).resolve().parents[1]
from reference_paths import reference_path

OLD = reference_path("old_root")
OUT = DEST / "docs"
OUT.mkdir(parents=True, exist_ok=True)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stamp(p):
    st = p.stat()
    return {
        "created_utc": datetime.fromtimestamp(st.st_ctime, timezone.utc).isoformat(),
        "modified_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
    }


def tracked(repo):
    def walk(tree, prefix=""):
        for name, mode, oid in repo[tree].items():
            name = name.decode()
            rel = prefix + name
            if mode & 0o170000 == 0o040000:
                yield from walk(oid, rel + "/")
            else:
                yield rel, oid.decode()

    return list(walk(repo[repo.head()].tree))


def target(rel):
    if rel in {"pyproject.toml", "requirements-lock.txt"} or rel.startswith(
        ("src/", "tests/")
    ):
        return "backend/" + rel
    return rel


def protected():
    # Old application sources, configuration, docs, assets, tests and profile reference data.
    # Rebuildable runtimes/dependencies/builds are excluded; one .run .pth is OS-unreadable.
    excluded = {
        ".venv",
        ".venv-before-move",
        "node_modules",
        "dist",
        "build",
        ".runtime",
        ".vite-cache",
        "artifacts",
        "test-results",
        ".analysis-pytest-tmp",
        ".test-tmp",
        ".pytest_cache",
        ".ruff_cache",
        "book_xml_backend.egg-info",
    }
    roots = [
        OLD / name
        for name in ["README.md", "start.ps1", "docs.rar", "experiments/out.rar"]
    ]
    for name in ["book_xml_backend", "book_xml_frontend"]:
        base = OLD / name
        for child in base.iterdir():
            if child.name in excluded:
                continue
            roots.append(child / "profiles" if child.name == "data" else child)
    result = {}
    for p in roots:
        if not p.exists():
            continue
        paths = p.rglob("*") if p.is_dir() else [p]
        for f in paths:
            if f.is_file() and "__pycache__" not in f.parts:
                result[f.relative_to(OLD).as_posix()] = {"sha256": sha(f), **stamp(f)}
    return result


def inventory():
    repo = Repo(str(OLD))
    assert repo.head().decode() == "fccabe28b91f1e0ac9d48367424319aa2ab40f62"
    current = tracked(repo)
    # Both commits contain only new-project artifacts; README/start/old roots are absent.
    assert all(
        rel not in {"README.md", "start.ps1"}
        and not rel.startswith(("book_xml_backend/", "book_xml_frontend/"))
        for rel, _ in current
    )
    first = repo[b"fe34f82d9bf43c8c19be696c5da5be1c43455274"]

    def initial_paths(tree, prefix=""):
        for name, mode, oid in repo[tree].items():
            rel = prefix + name.decode()
            if mode & 0o170000 == 0o040000:
                yield from initial_paths(oid, rel + "/")
            else:
                yield rel

    phase0 = set(initial_paths(first.tree))
    entries = []
    for rel, oid in current:
        p = OLD / rel
        entries.append(
            {
                "source": rel,
                "destination": target(rel),
                "created_step": 1 if rel in phase0 else 2,
                "git_blob": oid,
                "sha256": sha(p),
                **stamp(p),
            }
        )
    cache = OLD / "experiments/out/step2/page_cache"
    for p in sorted(cache.rglob("*")):
        if p.is_file():
            rel = p.relative_to(OLD).as_posix()
            entries.append(
                {
                    "source": rel,
                    "destination": rel,
                    "created_step": 2,
                    "generated": True,
                    "sha256": sha(p),
                    **stamp(p),
                }
            )
    root_entries = [
        {
            "name": p.name,
            "tracked_new_project": p.name
            in {
                ".gitignore",
                "AGENTS.md",
                "CLAUDE.md",
                "pyproject.toml",
                "requirements-lock.txt",
                "docs",
                "experiments",
                "src",
                "tests",
            },
            **stamp(p),
        }
        for p in OLD.iterdir()
    ]
    evidence = {
        "old_head": repo.head().decode(),
        "old_status_before": str(porcelain.status(repo)),
        "move": entries,
        "root_entries": root_entries,
        "left_in_place": "Old roots, README.md, start.ps1, user archives, .git, prior venvs and transient caches",
        "audit_scope": "Old source/config/docs/assets/tests/profile references and user root files; "
        "rebuildable runtimes/dependencies/build outputs excluded.",
        "unreadable_runtime_file": ".run/production-repair-20261007-01/checks/build-site/distutils-precedence.pth",
        "protected_before": protected(),
    }
    (OUT / "step2b_move_manifest.json").write_text(
        json.dumps(evidence, indent=2) + "\n", "utf-8"
    )
    lines = [
        "# Exact Step 2b move list",
        "",
        "Each path below was created in Step 1 or Step 2, verified against Git history and timestamps. Generated per-page caches are also listed individually.",
        "",
        "Pre-existing root files left untouched: README.md and start.ps1 (2026-10-05). "
        "Old directories book_xml_backend/book_xml_frontend, .run and .ruff_cache predate Step 1. "
        "User archives docs.rar and experiments/out.rar are untracked and stay in place. "
        "Old .git and prior Python environments stay in place; a new repository and venv will be created.",
        "",
    ]
    lines.extend(f"- {e['source']} -> {e['destination']}" for e in entries)
    (OUT / "step2b_move_list.md").write_text("\n".join(lines) + "\n", "utf-8")
    print(
        json.dumps(
            {
                "tracked_files": len(current),
                "generated_cache_files": len(entries) - len(current),
                "protected_files": len(evidence["protected_before"]),
                "manifest": str(OUT / "step2b_move_list.md"),
            }
        )
    )


def move():
    evidence = json.loads((OUT / "step2b_move_manifest.json").read_text("utf-8"))
    for e in evidence["move"]:
        source = (OLD / e["source"]).resolve()
        dest = (DEST / e["destination"]).resolve()
        assert source.is_relative_to(OLD.resolve()) and dest.is_relative_to(
            DEST.resolve()
        )
        assert e["source"] not in {"README.md", "start.ps1"}
        assert sha(source) == e["sha256"], f"Source changed: {source}"
        assert not dest.exists()
    for e in evidence["move"]:
        source = OLD / e["source"]
        dest = DEST / e["destination"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))
    print("Moved listed artifacts only")


def verify():
    evidence = json.loads((OUT / "step2b_move_manifest.json").read_text("utf-8"))
    after = protected()
    before = evidence["protected_before"]
    differences = [p for p in set(before) | set(after) if before.get(p) != after.get(p)]
    result = {
        "protected_files": len(before),
        "changed_protected_files": differences,
        "old_status_after": str(porcelain.status(Repo(str(OLD)))),
        "audit_scope": evidence["audit_scope"],
        "unreadable_runtime_file": evidence["unreadable_runtime_file"],
        "note": "Old root Git tracks Step 1/2 only; its deletions are the authorized move.",
    }
    (OUT / "step2b_old_project_verification.json").write_text(
        json.dumps(result, indent=2) + "\n", "utf-8"
    )
    assert not differences, differences
    print(json.dumps({"protected_files": len(before), "changed": len(differences)}))


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("action", choices=["inventory", "move", "verify"])
    action = args.parse_args().action
    globals()[action]()
