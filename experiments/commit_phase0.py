raise SystemExit("Historical commit script disabled after relocation; use the new repository workflow.")
"""Create the explicitly requested local Step 1 Git commit; exclude all old projects."""
from pathlib import Path
import json
from dulwich import porcelain
from dulwich.repo import Repo
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'.git').exists():porcelain.init(str(ROOT))
repo=Repo(str(ROOT))
paths=[Path('.gitignore'),Path('docs/phase0_report.md')]
for p in (ROOT/'experiments').rglob('*'):
 if not p.is_file():continue
 rel=p.relative_to(ROOT)
 if any(part.startswith('.venv-') or part in ('.cache','__pycache__') for part in rel.parts):continue
 paths.append(rel)
assert all(p.as_posix().startswith(('docs/','experiments/')) or p==Path('.gitignore') for p in paths)
porcelain.add(repo,paths=[p.as_posix() for p in paths])
oid=porcelain.commit(repo,message=b'Complete phase 0 reference audit and fixture experiments',author=b'Codex <codex@openai.com>',committer=b'Codex <codex@openai.com>')
status=porcelain.status(repo)
assert not status.staged['add'] and not status.staged['modify'] and not status.staged['delete']
assert not status.unstaged
print(json.dumps({'commit':oid.decode(),'tracked_files':len(repo.open_index()),'tracked_bytes':sum((ROOT/p).stat().st_size for p in paths),'status_untracked':len(status.untracked),'old_directories_tracked':False}))
