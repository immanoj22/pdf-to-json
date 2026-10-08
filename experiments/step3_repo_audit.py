"""Read-only old-project hash/status audit and new-repository change inventory."""
import json
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo
from step2b_housekeeping import protected
from reference_paths import reference_path

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/"docs/step2b_move_manifest.json").read_text("utf-8"))
before=manifest["protected_before"]
after=protected()
differences=[name for name in sorted(set(before)|set(after)) if before.get(name)!=after.get(name)]
old=Repo(str(reference_path("old_root")))
new=Repo(str(root))
result={"protected_files":len(before),"changed_protected_files":differences,
        "old_head":old.head().decode(),"old_status":str(porcelain.status(old)),
        "new_head":new.head().decode(),"new_status":str(porcelain.status(new)),
        "audit_scope":manifest["audit_scope"]}
(root/"experiments/out/step3/old_project_verification.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
assert not differences,differences
assert old.head().decode()==manifest["old_head"]
print(json.dumps({"protected_files":len(before),"changed":len(differences),"new_status":result["new_status"]}))
