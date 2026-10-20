import hashlib
import json

import pytest

from scripts.check_vendor_dependencies import audit_vendor, check_vendor


@pytest.fixture
def vendor(tmp_path):
    library = tmp_path / 'static/vendor/pdfjs'
    library.mkdir(parents=True)
    (library / 'pdf.min.mjs').write_text('synthetic library')
    manifest = {'package': 'pdfjs-dist', 'version': '4.10.38', 'source': 'npm',
                'integrity': 'synthetic-integrity', 'files': {
                    'pdf.min.mjs': hashlib.sha256(b'synthetic library').hexdigest()}}
    target = tmp_path / 'docs/dependencies'
    target.mkdir(parents=True)
    (target / 'pdfjs-manifest.json').write_text(json.dumps(manifest))
    return tmp_path


@pytest.mark.parametrize('fault', ['changed', 'missing', 'extra'])
def test_vendor_rejects_changed_missing_and_extra_files(vendor, fault):
    assert check_vendor(vendor)['package'] == 'pdfjs-dist'
    source = vendor / 'static/vendor/pdfjs/pdf.min.mjs'
    if fault == 'changed':
        source.write_text('changed library')
    elif fault == 'missing':
        source.unlink()
    else:
        (source.parent / 'unreviewed.mjs').write_text('extra library')
    with pytest.raises(ValueError, match='differ'):
        check_vendor(vendor)


@pytest.mark.parametrize('result,passes', [({}, True), ({'pdfjs-dist': [{'id': 'synthetic'}]}, False), ([], False)])
def test_vendor_scan_rejects_advisories_and_malformed_results(vendor, monkeypatch, result, passes):
    import io
    monkeypatch.setattr('urllib.request.urlopen', lambda *args, **kwargs: io.BytesIO(json.dumps(result).encode()))
    report = vendor / 'report.json'
    if passes:
        audit_vendor(check_vendor(vendor), report)
        assert json.loads(report.read_text())['advisories'] == {}
    else:
        with pytest.raises(ValueError, match='advisory scan'):
            audit_vendor(check_vendor(vendor), report)
