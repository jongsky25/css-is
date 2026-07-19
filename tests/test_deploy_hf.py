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
import ast
import os
import re

import deploy_hf

REPO_ROOT = os.path.dirname(os.path.abspath(deploy_hf.__file__))


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


def _first_party_modules():
    """Names (without .py) of every module that lives in the repo root."""
    return {
        f[:-3]
        for f in os.listdir(REPO_ROOT)
        if f.endswith(".py") and not f.startswith("_")
    }


def _local_imports(pyfile, first_party):
    """Top-level first-party modules imported by pyfile (`import X` / `from X import`)."""
    tree = ast.parse(open(pyfile, encoding="utf-8").read())
    deps = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in first_party:
                    deps.add(root)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".")[0]
            if root in first_party:
                deps.add(root)
    return deps


def test_runtime_py_is_import_closed():
    """Every first-party module imported (transitively) by a shipped module must
    itself be in RUNTIME_PY — otherwise the Space receives a half-closure and
    crashes on startup with ModuleNotFoundError.

    This exact bug shipped once: ai_core.py imports qa_rules, but qa_rules.py
    was missing from RUNTIME_PY, so `import ai_core` aborted the whole uvicorn
    boot on the live Space ('No module named qa_rules'). version.py is uploaded
    via ALLOW, so it counts as shipped too."""
    first_party = _first_party_modules()
    shipped = {name[:-3] for name in deploy_hf.RUNTIME_PY if name.endswith(".py")}
    shipped.add("version")  # carried in ALLOW, not RUNTIME_PY

    missing = {}
    seen = set()
    stack = list(shipped)
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        path = os.path.join(REPO_ROOT, mod + ".py")
        if not os.path.exists(path):
            continue
        for dep in _local_imports(path, first_party):
            if dep not in shipped:
                missing.setdefault(dep, set()).add(mod)
            stack.append(dep)

    assert not missing, (
        "first-party modules imported by shipped code but absent from RUNTIME_PY "
        "(add each to deploy_hf.RUNTIME_PY): "
        + ", ".join(f"{m}.py (imported by {sorted(by)})" for m, by in sorted(missing.items()))
    )
