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


def test_tabulator_gate_requires_matching_identity_and_files(vendor):
    source = vendor / 'static/vendor/tabulator'
    source.mkdir()
    (source / 'tabulator.min.js').write_text('synthetic table')
    manifest = {'package': 'tabulator-tables', 'version': '6.7.1', 'files': {
        'tabulator.min.js': hashlib.sha256(b'synthetic table').hexdigest()}}
    path = vendor / 'docs/dependencies/tabulator-manifest.json'
    path.write_text(json.dumps(manifest))
    assert check_vendor(vendor, name='tabulator', package='tabulator-tables')['version'] == '6.7.1'
    (source / 'tabulator.min.js').write_text('modified table')
    with pytest.raises(ValueError, match='differ'):
        check_vendor(vendor, name='tabulator', package='tabulator-tables')
    manifest['package'] = 'unexpected-package'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='identity'):
        check_vendor(vendor, name='tabulator', package='tabulator-tables')


def test_echarts_distribution_and_bundled_graph_are_verified():
    manifest=check_vendor(name='echarts',package='echarts')
    assert manifest['bundled_dependencies']=={'zrender':'6.1.0','tslib':'2.3.0'}
    assert {'LICENSE','NOTICE','licenses/zrender/LICENSE','licenses/tslib/LICENSE.txt'}<=set(manifest['files'])


def test_vendor_audit_submits_bundled_packages_and_rejects_transitive_advisory(tmp_path,monkeypatch):
    import io
    received=[]
    def request(req,**kwargs):
        received.append(json.loads(req.data))
        return io.BytesIO(json.dumps({'zrender':[{'id':'synthetic-transitive-advisory'}]}).encode())
    monkeypatch.setattr('urllib.request.urlopen',request)
    manifest=check_vendor(name='echarts',package='echarts')
    with pytest.raises(ValueError,match='advisory scan'):
        audit_vendor(manifest,tmp_path/'echarts-audit.json')
    assert received==[{'echarts':['6.1.0'],'zrender':['6.1.0'],'tslib':['2.3.0']}]


@pytest.mark.parametrize('fault',['missing_dependency','wrong_version'])
def test_echarts_gate_rejects_incomplete_or_inconsistent_bundle_provenance(tmp_path,fault):
    from pathlib import Path
    manifest=json.loads((Path(__file__).resolve().parents[1]/'docs/dependencies/echarts-manifest.json').read_text())
    if fault=='missing_dependency':del manifest['bundled_dependencies']['zrender']
    else:manifest['bundled_dependencies']['zrender']='0.0.0'
    target=tmp_path/'docs/dependencies';target.mkdir(parents=True)
    (target/'echarts-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='provenance'):
        check_vendor(tmp_path,name='echarts',package='echarts')
