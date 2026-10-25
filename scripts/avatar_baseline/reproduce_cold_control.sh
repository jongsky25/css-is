#!/usr/bin/env bash
# Five full-duration desktop-cold samples from immutable increment-0 source.
set -euo pipefail
avatar_repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
avatar_output=${1:-"$avatar_repo_root/docs/avatars/increment2b/reproduced-control"}
if [[ -e "$avatar_output/application/False-cold.json" ]]; then
  printf 'Existing control results: choose a fresh output directory.\n' >&2
  exit 1
fi
mkdir -p "$avatar_output"
avatar_output=$(cd "$avatar_output" && pwd)
avatar_control_root=$(mktemp -d "$avatar_repo_root/../css-is-avatar-control-XXXXXX")
rmdir "$avatar_control_root"
git -C "$avatar_repo_root" worktree add --detach "$avatar_control_root" 1c964dc
"$avatar_repo_root/.venv/bin/python" - "$avatar_repo_root" "$avatar_control_root" "$avatar_output" <<'PYFS'
import json,subprocess,sys
from pathlib import Path
current,control,out=sys.argv[1:]
fs=lambda path:subprocess.check_output(['stat','-f','-c','%T',path],text=True).strip()
record={'current_path':current,'control_path':control,'current_filesystem':fs(current),'control_filesystem':fs(control),'reference_commit':'1c964dc'}
assert record['current_filesystem']==record['control_filesystem'],record
Path(out,'filesystem.json').write_text(json.dumps(record,indent=2))
PYFS
(
  cd "$avatar_control_root"
  env -u CSS_AVATAR_KIND -u CSS_AVATAR_MATURE -u CSS_AVATAR_PLANTS \
    CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 \
    CSS_AVATAR_RUNS=5 CSS_AVATAR_SECONDS=30 \
    CSS_AVATAR_OUT="$avatar_output/application" \
    "$avatar_repo_root/.venv/bin/python" -m pytest tests/test_avatar_baseline_browser.py \
      -k 'real_application_baseline and cold and desktop' -s
) 2>&1 | tee "$avatar_output/control-tests.txt"
git -C "$avatar_repo_root" worktree remove "$avatar_control_root"
"$avatar_repo_root/.venv/bin/python" "$avatar_repo_root/scripts/avatar_baseline/summarize.py" "$avatar_output/application"
