"""Fail-closed release metadata and JUnit checks, using only the standard library."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET


def version_key(value: str) -> tuple[int, int]:
    # Compare recorded legacy versions too; new releases are checked more
    # strictly below. Two-digit minors include .00 and .01 without floats.
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.([0-9]{2}|0|[1-9][0-9]*)", value):
        raise ValueError(f"Invalid application version: {value!r}")
    return tuple(map(int, value.split(".")))


def metadata(source: str) -> dict:
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"APP_VERSION", "CHANGELOG"}:
                    if target.id in result:
                        raise ValueError(f"Duplicate {target.id}")
                    result[target.id] = ast.literal_eval(node.value)
    return result


def check_release(root: Path, base_source: str) -> str:
    current = metadata((root / "version.py").read_text())
    version = current["APP_VERSION"]
    previous = metadata(base_source)["APP_VERSION"]
    if not isinstance(version, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.[0-9]{2}", version):
        raise ValueError("New application versions must have exactly two digits after the decimal")
    if version_key(version) <= version_key(previous):
        raise ValueError(f"Version {version} must increase from {previous}")
    latest = current["CHANGELOG"][0]
    if latest["version"] != version or not latest.get("summary") or not latest.get("changes"):
        raise ValueError("Latest in-app changelog must describe the current version")
    changelog = (root / "CHANGELOG.md").read_text()
    first = re.search(r"^## (\d+\.\d+)(?:\s|$)", changelog, re.MULTILINE)
    if first is None or first.group(1) != version:
        raise ValueError("First CHANGELOG.md release must match APP_VERSION")
    cache = re.findall(r'^const CACHE_VERSION = "([^"]+)";', (root / "static/js/sw.js").read_text(), re.MULTILINE)
    if len(cache) != 1 or not re.fullmatch(rf"v{re.escape(version)}-[a-z0-9]+", cache[0]):
        raise ValueError("Service-worker cache version must match APP_VERSION")
    return version


def check_junit(path: Path) -> int:
    root = ET.parse(path).getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("Unrecognized JUnit report")
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("JUnit report contains no tests")
    for tag in ("failure", "error", "skipped"):
        if next(root.iter(tag), None) is not None:
            raise ValueError(f"JUnit report contains {tag} results")
    for suite in root.iter("testsuite"):
        for field in ("failures", "errors", "skipped"):
            if int(suite.get(field, "0")) != 0:
                raise ValueError(f"JUnit suite reports {field}")
    return len(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    release = sub.add_parser("release")
    release.add_argument("--base", required=True, help="Trusted base Git commit")
    sub.add_parser("junit").add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "release":
            # Resolve first: do not allow an untrusted argument to become a Git option.
            base = subprocess.check_output(
                ["git", "rev-parse", "--verify", "--end-of-options", args.base + "^{commit}"],
                text=True,
            ).strip()
            source = subprocess.check_output(["git", "show", f"{base}:version.py"], text=True)
            print(f"Release metadata OK: {check_release(Path.cwd(), source)}")
        else:
            print(f"JUnit gate OK: {check_junit(args.path)} tests, no failures or skips")
    except (ValueError, KeyError, IndexError, TypeError, SyntaxError, OSError,
            ET.ParseError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Release gate failed: {exc}\n")


if __name__ == "__main__":
    main()
