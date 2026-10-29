"""Measure DOCX layout without third-party packages or body text.

Usage: python3 tools/docx_layout.py blank.docx [other.docx ...] > layout.json
Numbers are OOXML values: twips for page/paragraph/table lengths, half-points
for font sizes, EMUs for images. Missing properties remain absent: Word may
inherit them from styles or defaults. This reports XML, not rendered pagination.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import sys
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
}


def local(name):
    return name.rsplit('}', 1)[-1]


def attrs(element):
    return {} if element is None else {local(k): v for k, v in sorted(element.attrib.items())}


def properties(element):
    """Keep structural properties, never document text or embedded content."""
    if element is None:
        return []
    return [dict(tag=local(child.tag), attributes=attrs(child), children=properties(child))
            for child in element if local(child.tag) not in {'sectPr', 'rPrChange', 'pPrChange'}]


def profiles(elements, path):
    counts = Counter(json.dumps(properties(e.find(path, NS)), sort_keys=True) for e in elements)
    return [{'properties': json.loads(key), 'count': count} for key, count in sorted(counts.items())]


def on(element):
    return element is not None and element.get(f"{{{NS['w']}}}val", 'true') not in {'0', 'false', 'off'}


def summarize(root, include_text=False):
    paragraphs = list(root.iter(f"{{{NS['w']}}}p"))
    runs = list(root.iter(f"{{{NS['w']}}}r"))
    tables = []
    for table in root.iter(f"{{{NS['w']}}}tbl"):
        rows = []
        for row in table.findall('w:tr', NS):
            rows.append([properties(cell.find('w:tcPr', NS)) for cell in row.findall('w:tc', NS)])
        tables.append({
            'grid_twips': [int(c.get(f"{{{NS['w']}}}w")) for c in table.findall('w:tblGrid/w:gridCol', NS)],
            'properties': properties(table.find('w:tblPr', NS)),
            'rows': rows,
        })
    images = []
    for kind in ('anchor', 'inline'):
        for image in root.iter(f"{{{NS['wp']}}}{kind}"):
            images.append({'kind': kind, 'attributes': attrs(image),
                           'extent_emu': attrs(image.find('wp:extent', NS))})
    result = {
        'paragraph_profiles': profiles(paragraphs, 'w:pPr'),
        'run_profiles': profiles(runs, 'w:rPr'),
        'tables': tables, 'images': images,
    }
    if include_text:
        result['text'] = [''.join(t.text or '' for t in p.iter(f"{{{NS['w']}}}t")) for p in paragraphs]
    return result


def measure(path: Path, *, include_header_footer_text=True):
    """Return deterministic measurements; relationship targets are ZIP members only."""
    with ZipFile(path) as package:
        def read(member):
            return ET.fromstring(package.read(member))

        document = read('word/document.xml')
        relationships = {}
        if 'word/_rels/document.xml.rels' in package.namelist():
            for rel in read('word/_rels/document.xml.rels'):
                if rel.get('TargetMode') == 'External':
                    continue
                target = rel.get('Target', '')
                member = posixpath.normpath(posixpath.join('word', target)) if not target.startswith('/') else target.lstrip('/')
                relationships[rel.get('Id')] = member
        sections, parts = [], {}
        inherited = {}
        for section in document.iter(f"{{{NS['w']}}}sectPr"):
            refs = []
            for kind in ('header', 'footer'):
                for ref in section.findall(f'w:{kind}Reference', NS):
                    member = relationships.get(ref.get(f"{{{NS['r']}}}id"))
                    if member is None:
                        raise ValueError('Missing internal header/footer relationship')
                    if not member.startswith('word/') or '..' in PurePosixPath(member).parts:
                        raise ValueError('Header/footer relationship leaves the word package')
                    variant = ref.get(f"{{{NS['w']}}}type", 'default')
                    inherited[(kind, variant)] = member
                    refs.append({'kind': kind, 'type': variant, 'part': member})
                    if member not in parts:
                        parts[member] = summarize(read(member), include_header_footer_text)
            sections.append({
                'paper_twips': attrs(section.find('w:pgSz', NS)),
                'margins_twips': attrs(section.find('w:pgMar', NS)),
                'different_first_page': on(section.find('w:titlePg', NS)),
                'references': refs,
                'effective_references': [{'kind': k, 'type': t, 'part': p}
                                         for (k, t), p in sorted(inherited.items())],
            })
        styles = read('word/styles.xml') if 'word/styles.xml' in package.namelist() else None
        settings = read('word/settings.xml') if 'word/settings.xml' in package.namelist() else None
        numbering = read('word/numbering.xml') if 'word/numbering.xml' in package.namelist() else None
        return {
            'schema_version': 1,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'units': {'length': 'twips', 'font_size': 'half-points', 'image_extent': 'EMU',
                      'line_spacing': '240ths of a line when lineRule is auto; otherwise twips'},
            'even_and_odd_headers': on(settings.find('w:evenAndOddHeaders', NS)) if settings is not None else False,
            'sections': sections,
            'body': summarize(document),
            'header_footer_parts': parts,
            'style_defaults': properties(styles.find('w:docDefaults', NS)) if styles is not None else [],
            'styles': [{'id': s.get(f"{{{NS['w']}}}styleId"), 'attributes': attrs(s),
                        'properties': properties(s)} for s in styles.findall('w:style', NS)] if styles is not None else [],
            'numbering': properties(numbering),
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', type=Path, nargs='+')
    parser.add_argument('--omit-header-footer-text', action='store_true',
                        help='Keep measurements only, for a reference without document wording')
    args = parser.parse_args(argv)
    try:
        output = {path.stem: measure(path, include_header_footer_text=not args.omit_header_footer_text)
                  for path in args.files}
        if len(output) != len(args.files):
            raise ValueError('Input files must have distinct stems')
    except (OSError, BadZipFile, ET.ParseError, KeyError, ValueError) as exc:
        parser.exit(2, f'docx_layout: {exc}\n')
    json.dump(output, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
