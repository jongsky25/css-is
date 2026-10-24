"""Real browser downloads: native charts/workbooks, full tables and current access."""
import io
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import documents as docs
import storage as st
from tests.test_document_registry_grid_browser import grid_browser,grid_page

NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}


def export(page):
    with page.expect_download() as result:
        page.get_by_role('button',name='Export PowerPoint report',exact=True).click()
    download=result.value
    assert download.suggested_filename=='office-connect-document-workload-report.pptx'
    return zipfile.ZipFile(io.BytesIO(Path(download.path()).read_bytes()))


def test_editable_workload_presentation_complete_leads_fresh_access_and_applied_scope(grid_page,app_mod,tmp_path):
    page,state=grid_page;c=st.connect(app_mod.DB)
    ids=[r[0] for r in c.execute('SELECT id FROM document ORDER BY id')]
    names=[]
    for index in range(26):
        name='<img src=x onerror="window.reportInjected=true">' if index==0 else f'Briefing lead {index:02}'
        names.append(name)
        uid=st.create_admin_user(c,name,'unused','unused','viewer',active=False)
        c.execute('UPDATE document SET lead_id=? WHERE id=?',(uid,ids[index]))
    admin=st.get_admin_user(c,'admin@test.local')
    secret=st.create_admin_user(c,'Private hidden lead','unused','unused','viewer',active=False)
    hidden=docs.register(c,admin,{'subject':'Register PRIVATE SUBJECT','type':'memo','direction':'OUT'})
    c.execute("UPDATE document SET visibility='restricted',lead_id=? WHERE id=?",(secret,hidden['id']));c.commit()
    page.goto('http://office.test/documents/dashboard?queue=OUT&q=Register')
    assert '35 matching records' in page.locator('#document-dashboard').inner_text()
    page.locator('[name=queue]').select_option('IN')
    page.get_by_role('searchbox',name='Search permitted records',exact=True).fill('PRIVATE')
    c.execute("UPDATE document SET visibility='restricted',creator_id=? WHERE id=?",(admin['id'],ids[25]));c.commit()
    with page.expect_response('**/documents/dashboard/presentation-data?**') as response:
        with export(page) as archive:
            (tmp_path/'workload-report.pptx').write_bytes(archive.fp.getvalue())
            assert archive.testzip() is None
            slides=[n for n in archive.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
            text=' '.join(' '.join(ET.fromstring(archive.read(n)).itertext()) for n in slides)
            normalized=' '.join(text.split())
            assert '34 matching documents' in normalized and '26 lead groups' in normalized
            assert 'Queue: Outgoing' in normalized and 'Applied search: Register' in normalized
            assert '2026-10-20' in normalized and '2026-10-23' in normalized
            assert 'Register item' not in normalized and 'PRIVATE SUBJECT' not in normalized
            assert 'Private hidden lead' not in normalized and names[25] not in normalized
            assert names[24] in normalized and names[0] in normalized
            assert 'largest 20 of 26 lead groups' in normalized
            charts=sorted(n for n in archive.namelist() if n.startswith('ppt/charts/chart') and n.endswith('.xml'))
            assert len(charts)==3
            totals=[]
            for n in charts:
                chart=ET.fromstring(archive.read(n));assert chart.find('.//c:barChart',NS) is not None
                totals.append(sum(int(v.text) for v in chart.findall('.//c:numCache/c:pt/c:v',NS)))
            assert totals==[34,34,28]
            assert len([n for n in archive.namelist() if n.endswith('.xlsx')])==3
            assert len(slides)>=8
            for n in archive.namelist():
                if n.endswith(('.xml','.rels')):ET.fromstring(archive.read(n))
    assert response.value.status==200 and response.value.headers['cache-control']=='no-store'
    fresh=response.value.json()
    assert sum(row['count'] for row in fresh['leads'])==34 and len(fresh['leads'])==26
    assert page.evaluate('window.reportInjected') is None
    assert 'downloaded' in page.locator('#workload-presentation-status').inner_text()
    c.close()


def test_workload_empty_mobile_failed_request_assets_and_forbidden_scope(grid_page):
    page,state=grid_page;page.set_viewport_size({'width':390,'height':844})
    page.goto('http://office.test/documents/dashboard?q=NO-MATCH')
    with export(page) as archive:
        assert not any(n.startswith('ppt/charts/chart') for n in archive.namelist())
        assert b'No matching documents' in archive.read('ppt/slides/slide4.xml')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    for query,expected in [('queue=instruction',403),('queue=invalid',400),('q='+('x'*121),400)]:
        result=page.evaluate("""async query => { const r=await fetch('/documents/dashboard/presentation-data?'+query);
            return {status:r.status,cache:r.headers.get('cache-control')}; }""",query)
        assert result=={'status':expected,'cache':'no-store'}
    page.route('**/documents/dashboard/presentation-data?**',lambda route:route.fulfill(
        status=400,content_type='application/json',body='{"error":"Narrow the dashboard queue or search before exporting."}'))
    page.get_by_role('button',name='Export PowerPoint report',exact=True).click()
    page.wait_for_function("document.getElementById('workload-presentation-status').textContent.includes('Narrow the dashboard')")
    assert page.get_by_role('button',name='Export PowerPoint report',exact=True).is_enabled()
    page.unroute('**/documents/dashboard/presentation-data?**')
    page.route('**/static/vendor/pptxgenjs/**',lambda route:route.abort())
    page.goto('http://office.test/documents/dashboard')
    assert page.get_by_role('button',name='Export PowerPoint report',exact=True).is_disabled()
    assert 'could not load' in page.locator('#workload-presentation-status').inner_text()
    assert page.get_by_role('region',name='Workflow stages counts').is_visible()
