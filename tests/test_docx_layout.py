"""Use a tiny OOXML package so measurement tests need no office files or SDK."""
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

from tools.docx_layout import measure

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


@pytest.fixture
def docx(tmp_path):
    path = tmp_path / 'blank.docx'
    with ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', f'''<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>
        <w:p><w:pPr><w:jc w:val="both"/><w:ind w:left="720" w:hanging="360"/>
        <w:spacing w:before="240" w:after="240" w:line="288" w:lineRule="auto"/>
        <w:sectPr><w:pgSz w:w="11906" w:h="16838"/>
        <w:pgMar w:top="1440" w:bottom="1440" w:left="1440" w:right="1440" w:header="720" w:footer="432"/>
        <w:titlePg/><w:headerReference w:type="first" r:id="header"/>
        <w:footerReference w:type="first" r:id="footer"/></w:sectPr></w:pPr>
        <w:r><w:rPr><w:rFonts w:ascii="Times New Roman"/><w:sz w:val="24"/></w:rPr>
        <w:t>PRIVATE NAME AND BODY</w:t></w:r></w:p>
        <w:tbl><w:tblPr><w:tblInd w:w="-540" w:type="dxa"/>
        <w:tblBorders><w:top w:val="single" w:sz="4"/></w:tblBorders></w:tblPr>
        <w:tblGrid><w:gridCol w:w="2445"/><w:gridCol w:w="8475"/></w:tblGrid>
        <w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/><w:tcBorders><w:bottom w:val="nil"/></w:tcBorders></w:tcPr><w:p/></w:tc></w:tr></w:tbl>
        <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:titlePg w:val="0"/></w:sectPr>
        </w:body></w:document>''')
        z.writestr('word/_rels/document.xml.rels', '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="header" Target="header1.xml"/><Relationship Id="footer" Target="footer1.xml"/>
        <Relationship Id="custom" Target="../customXml/item1.xml"/>
        <Relationship Id="external" Target="https://example.invalid/ignored" TargetMode="External"/>
        </Relationships>''')
        z.writestr('word/header1.xml', f'''<w:hdr xmlns:w="{W}" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
        <w:p><w:r><w:t>DEPARTMENT OF HEALTH</w:t><w:drawing><wp:anchor><wp:extent cx="952500" cy="952500"/></wp:anchor></w:drawing></w:r></w:p></w:hdr>''')
        z.writestr('word/footer1.xml', f'<w:ftr xmlns:w="{W}"><w:p><w:r><w:t>Trunk Line 8651-7800</w:t></w:r></w:p></w:ftr>')
        z.writestr('word/styles.xml', f'''<w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial"/><w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults>
        <w:style w:type="paragraph" w:styleId="Normal"><w:pPr><w:spacing w:line="240"/></w:pPr></w:style></w:styles>''')
        z.writestr('word/settings.xml', f'<w:settings xmlns:w="{W}"><w:evenAndOddHeaders/></w:settings>')
    return path


def test_section_measurements_and_inherited_headers(docx):
    data = measure(docx)
    assert data['sections'][0]['paper_twips'] == {'w': '11906', 'h': '16838'}
    assert data['sections'][0]['margins_twips']['footer'] == '432'
    assert data['sections'][0]['different_first_page'] is True
    assert data['sections'][1]['different_first_page'] is False
    assert data['sections'][1]['effective_references'] == data['sections'][0]['effective_references']
    assert data['even_and_odd_headers'] is True
    assert data['header_footer_parts']['word/footer1.xml']['text'] == ['Trunk Line 8651-7800']
    assert data['header_footer_parts']['word/header1.xml']['images'][0]['extent_emu'] == {'cx': '952500', 'cy': '952500'}


def test_formatting_and_tables_without_body_text(docx):
    data = measure(docx)
    encoded = json.dumps(data)
    assert 'PRIVATE NAME' not in encoded
    assert 'Times New Roman' in encoded and 'Arial' in encoded
    p = next(p['properties'] for p in data['body']['paragraph_profiles'] if p['properties'])
    assert next(x['attributes'] for x in p if x['tag'] == 'spacing')['line'] == '288'
    table = data['body']['tables'][0]
    assert table['grid_twips'] == [2445, 8475]
    assert table['properties'][0]['attributes']['w'] == '-540'
    assert table['rows'][0][0][0]['attributes']['val'] == '2'
    assert table['rows'][0][0][1]['children'][0]['attributes']['val'] == 'nil'
    assert data['styles'][0]['id'] == 'Normal'
    assert measure(docx) == data


def test_cli_is_standalone_and_can_omit_header_footer_text(docx):
    script = Path(__file__).resolve().parents[1] / 'tools' / 'docx_layout.py'
    result = subprocess.run([sys.executable, '-S', str(script), '--omit-header-footer-text', str(docx)], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)['blank']
    assert 'text' not in data['header_footer_parts']['word/footer1.xml']
    assert 'PRIVATE NAME' not in result.stdout
    assert data['sections'][0]['paper_twips']['w'] == '11906'
    assert subprocess.run([sys.executable, '-S', str(script), str(docx.with_name('missing.docx'))], capture_output=True).returncode == 2


def test_minimal_package_and_bad_zip(tmp_path):
    path = tmp_path / 'minimal.docx'
    with ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', f'<w:document xmlns:w="{W}"><w:body><w:p/></w:body></w:document>')
    data = measure(path)
    assert data['sections'] == []
    assert data['styles'] == []
    assert data['numbering'] == []
    assert data['body']['paragraph_profiles'] == [{'properties': [], 'count': 1}]
    path.write_text('not a zip')
    script = Path(__file__).resolve().parents[1] / 'tools' / 'docx_layout.py'
    result = subprocess.run([sys.executable, '-S', str(script), str(path)], capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'docx_layout:' in result.stderr
