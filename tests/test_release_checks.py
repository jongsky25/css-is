"""Regression coverage for fail-closed release gates."""
import pytest

from scripts.check_release import check_junit, check_release, metadata, version_key


@pytest.fixture
def release_tree(tmp_path):
    (tmp_path / "static/js").mkdir(parents=True)
    (tmp_path / "version.py").write_text(
        'APP_VERSION = "7.40"\n'
        'CHANGELOG = [{"version": "7.40", "summary": "Verified", "changes": ["Checks"]}]\n'
    )
    (tmp_path / "CHANGELOG.md").write_text("## 7.40 — October 20, 2026\n\n- Checks\n")
    (tmp_path / "static/js/sw.js").write_text('const CACHE_VERSION = "v7.40-a";\n')
    return tmp_path


def test_valid_release(release_tree):
    assert check_release(release_tree, 'APP_VERSION = "7.39"') == "7.40"
    assert version_key("7.40") > version_key("7.9")


@pytest.mark.parametrize("base", ["7.40", "7.41", "8.0"])
def test_requires_version_increase(release_tree, base):
    with pytest.raises(ValueError, match="must increase"):
        check_release(release_tree, f'APP_VERSION = "{base}"')


@pytest.mark.parametrize("value", ["v7.40", "7.040", "7", "7.40.1", "", None])
def test_rejects_malformed_version(value):
    with pytest.raises(ValueError):
        version_key(value)


@pytest.mark.parametrize(("path", "old", "new"), [
    ("version.py", '"version": "7.40"', '"version": "7.39"'),
    ("version.py", '"summary": "Verified"', '"summary": ""'),
    ("version.py", '["Checks"]', '[]'),
    ("CHANGELOG.md", "7.40", "7.39"),
    ("static/js/sw.js", "v7.40-a", "v7.39-a"),
])
def test_rejects_inconsistent_metadata(release_tree, path, old, new):
    target = release_tree / path
    target.write_text(target.read_text().replace(old, new))
    with pytest.raises(ValueError):
        check_release(release_tree, 'APP_VERSION = "7.39"')


def test_metadata_does_not_execute_code(tmp_path):
    marker = tmp_path / "executed"
    source = f'APP_VERSION = __import__("pathlib").Path({str(marker)!r}).touch()'
    with pytest.raises(ValueError):
        metadata(source)
    assert not marker.exists()


@pytest.mark.parametrize("content", [
    "<testsuites/>",
    '<testsuite><testcase><failure/></testcase></testsuite>',
    '<testsuite><testcase><error/></testcase></testsuite>',
    '<testsuite><testcase><skipped/></testcase></testsuite>',
    '<testsuite failures="1"><testcase/></testsuite>',
    '<testsuite errors="1"><testcase/></testsuite>',
    '<testsuite skipped="1"><testcase/></testsuite>',
])
def test_junit_rejects_missing_or_unsuccessful_tests(tmp_path, content):
    path = tmp_path / "results.xml"
    path.write_text(content)
    with pytest.raises(ValueError):
        check_junit(path)


def test_junit_accepts_passing_tests(tmp_path):
    path = tmp_path / "results.xml"
    path.write_text('<testsuites><testsuite tests="2"><testcase/><testcase/></testsuite></testsuites>')
    assert check_junit(path) == 2
