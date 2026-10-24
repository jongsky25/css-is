"""The A25 rehearsal must be isolated, repeatable and fail on broken recovery."""
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_percentiles_interpolate_without_inventing_samples():
    from scripts.assess_capacity import distribution

    assert distribution([])["samples"] == 0
    assert distribution([10, 20, 30, 40, 50])["p95_ms"] == 48


def test_synthetic_capacity_rehearsal_isolated_and_reconciled(tmp_path):
    output = tmp_path / "capacity.json"
    run = subprocess.run(
        [sys.executable, "scripts/assess_capacity.py", "--responses", "20",
         "--concurrency", "2", "--requests-per-worker", "2", "--output", str(output)],
        cwd=ROOT, capture_output=True, text=True, timeout=90,
    )
    assert run.returncode == 0, run.stderr[-2000:]
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["answers_seeded"] == 180
    assert result["first_use"]["errors"] == []
    assert result["mixed_workload"]["errors"] == {"dashboard": 0, "health": 0, "write": 0}
    assert result["mixed_workload"]["report_export"]["status"] == 200
    assert result["recovery"]["integrity"] == "ok"
    assert result["recovery"]["responses_reconciled"] == 25
    assert result["controlled_lock_wait"]["write_completion_ms"] >= 80
    assert not list(tmp_path.glob("*.db"))
