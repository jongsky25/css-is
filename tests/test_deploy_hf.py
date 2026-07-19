"""
deploy_hf.py — regression coverage for the build_info.json ordering bug.

This exact bug reached a live deploy: build_info.json was added to ALLOW (the
list of files the missing-files guard requires to exist) in the same PR that
introduced write_build_info() — but the guard ran BEFORE write_build_info()
was called, so every deploy hard-aborted with "ABORT — missing files:
['build_info.json']" (confirmed in the actual GitHub Actions run). Fixed by
moving write_build_info() ahead of the missing-files check in main().

main() itself talks to the real Hugging Face API and network, so it isn't
unit-tested end-to-end here — these two tests instead directly cover (1) that
write_build_info() does what it claims, and (2) the specific ordering
invariant that broke, so a future refactor can't silently reintroduce it.
"""
import re

import deploy_hf


def test_write_build_info_creates_expected_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    deploy_hf.write_build_info("9.99", "tester")
    path = tmp_path / "build_info.json"
    assert path.exists()
    import json
    info = json.loads(path.read_text(encoding="utf-8"))
    assert info["version"] == "9.99"
    assert info["deployed_by"] == "tester"
    assert info["deployed_at"]
    # commit/commit_short may be None outside a git checkout, but must be present.
    assert "commit" in info and "commit_short" in info


def test_build_info_written_before_missing_files_check():
    """Source-order regression guard: write_build_info(...) must appear before
    the missing-files check in main(), since build_info.json is in ALLOW and
    doesn't exist on disk until write_build_info() creates it."""
    src = open(deploy_hf.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    write_call = re.search(r"write_build_info\(", main_src)
    missing_check = re.search(r"missing = \[f for f in allow", main_src)
    assert write_call and missing_check, "expected both to appear in main()"
    assert write_call.start() < missing_check.start(), (
        "write_build_info() must run BEFORE the missing-files check — "
        "otherwise build_info.json (in ALLOW) is reported missing and every "
        "deploy aborts (this exact regression happened once already)")


def test_ai_core_is_in_runtime_py():
    """ai_core.py must ship to the Space, or ai_mode can never leave 'off'
    there (docs/AI_INTEGRATION_PLAN.md Phase 0 — 'every new .py module must
    be added to RUNTIME_PY or the Space silently runs without it')."""
    assert "ai_core.py" in deploy_hf.RUNTIME_PY
