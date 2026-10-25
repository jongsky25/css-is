"""Verify vendored browser dependencies and, optionally, their npm advisories."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SERVICE = 'https://registry.npmjs.org/-/npm/v1/security/advisories/bulk'


def check_vendor(root=ROOT, *, name='pdfjs', package='pdfjs-dist'):
    manifest = json.loads((root / f'docs/dependencies/{name}-manifest.json').read_text())
    if manifest.get('package') != package or not re.fullmatch(r'\d+\.\d+\.\d+', manifest.get('version', '')):
        raise ValueError(f'Invalid {name} manifest identity')
    dependencies = manifest.get('bundled_dependencies', {})
    if not isinstance(dependencies, dict) or any(
            not isinstance(name, str) or not re.fullmatch(r'(?:@[a-z0-9._-]+/)?[a-z0-9._-]+', name)
            or not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version)
            for name, version in dependencies.items()):
        raise ValueError(f'Invalid {name} bundled dependency identities')
    expected = {'echarts': {'zrender', 'tslib'},
                'pptxgenjs': {'jszip','lie','immediate','pako','setimmediate'},
                'fullcalendar': {'@fullcalendar/core', '@fullcalendar/interaction',
                                 '@fullcalendar/daygrid', '@fullcalendar/timegrid',
                                 '@fullcalendar/list', '@fullcalendar/multimonth',
                                 '@fullcalendar/luxon3', 'luxon', 'preact'}}
    if package in expected:
        provenance = manifest.get('dependency_provenance', {})
        if (set(dependencies) != expected[package] or not isinstance(provenance, dict)
                or set(provenance) != set(dependencies)
                or any(not isinstance(provenance[key], dict) or provenance[key].get('version') != version
                       for key, version in dependencies.items())):
            raise ValueError(f'Invalid {package} bundled dependency provenance')
    vendor = root / 'static/vendor' / name
    observed = {path.relative_to(vendor).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in vendor.rglob('*') if path.is_file() and path.name != 'README.txt'}
    if not observed or observed != manifest.get('files'):
        raise ValueError(f'Vendored {name} files differ from the reviewed upstream manifest')
    if package == 'fullcalendar':
        sources = ['luxon.min.js', 'fullcalendar.min.js', 'luxon3-plugin.min.js']
        if (manifest.get('bundle_sources') != sources or
                (vendor / 'fullcalendar-with-timezone.js').read_bytes() !=
                b'\n'.join((vendor / source).read_bytes() for source in sources)):
            raise ValueError('FullCalendar timezone bundle differs from its reviewed sources')
    return manifest


def audit_vendor(manifest, output):
    request = urllib.request.Request(SERVICE, method='POST',
        data=json.dumps({manifest['package']: [manifest['version']],
                         **{name:[version] for name,version in manifest.get('bundled_dependencies', {}).items()}}).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        advisories = json.loads(response.read(1024 * 1024))
    report = {key: manifest[key] for key in ('package', 'version', 'source', 'integrity')}
    report['bundled_dependencies'] = manifest.get('bundled_dependencies', {})
    report.update(service=SERVICE, checked_at=datetime.now(timezone.utc).isoformat(),
                  verified_files=len(manifest['files']), advisories=advisories)
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    # The bulk endpoint returns {} only when no submitted version is affected.
    # Unexpected schemas or an advisory must never silently pass.
    if advisories != {}:
        raise ValueError('Vendor advisory scan found issues or returned unexpected data')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-output', help='Also query npm and save the advisory receipt')
    args = parser.parse_args()
    manifest = check_vendor()
    tabulator = check_vendor(name='tabulator', package='tabulator-tables')
    echarts = check_vendor(name='echarts', package='echarts')
    pptxgenjs = check_vendor(name='pptxgenjs', package='pptxgenjs')
    fullcalendar = check_vendor(name='fullcalendar', package='fullcalendar')
    if args.audit_output:
        audit_vendor(manifest, args.audit_output)
        report = Path(args.audit_output)
        audit_vendor(tabulator, report.with_name(report.stem + '-tabulator' + report.suffix))
        audit_vendor(echarts, report.with_name(report.stem + '-echarts' + report.suffix))
        audit_vendor(pptxgenjs, report.with_name(report.stem + '-pptxgenjs' + report.suffix))
        audit_vendor(fullcalendar, report.with_name(report.stem + '-fullcalendar' + report.suffix))
    print(f"Vendor gate OK: PDF.js {manifest['version']}, {len(manifest['files'])} verified files")
    print(f"Vendor gate OK: Tabulator {tabulator['version']}, {len(tabulator['files'])} verified files")

    print(f"Vendor gate OK: ECharts {echarts['version']}, {len(echarts['files'])} verified files with bundled dependencies")

    print(f"Vendor gate OK: PptxGenJS {pptxgenjs['version']}, {len(pptxgenjs['files'])} verified files with JSZip browser dependencies")
    print(f"Vendor gate OK: FullCalendar {fullcalendar['version']}, {len(fullcalendar['files'])} verified files with timezone dependencies")
