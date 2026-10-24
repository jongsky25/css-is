"""Download and inspect actual editable OOXML from the real browser libraries."""
import io
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from tests.test_document_registry_grid_browser import grid_browser
from tests.test_supplies_grid_browser import inventory_page
from tests.test_supplies_stock import receive
import supplies

NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}


def export(page):
    with page.expect_download() as result:
        page.get_by_role('button',name='Export PowerPoint report',exact=True).click()
    download=result.value
    assert download.suggested_filename=='office-connect-supplies-stock-report.pptx'
    return zipfile.ZipFile(io.BytesIO(Path(download.path()).read_bytes()))


def test_editable_complete_presentation_fresh_applied_scope_and_exact_values(inventory_page,tmp_path):
    page,state,c=inventory_page
    c.execute('UPDATE supply_item SET critical_level=50,target_level=NULL');c.commit()
    page.goto('http://office.test/supplies/stock-dashboard?unit=Ream&page=2')
    page.get_by_role('button',name='Export PowerPoint report',exact=True).wait_for(state='visible')
    # Unsaved draft filters must not replace the scope of the displayed dashboard.
    page.get_by_label('Dashboard unit',exact=True).select_option('Box')
    # A stock change after page load must be reflected in the downloaded snapshot.
    item_id=c.execute("SELECT id FROM supply_item WHERE code='INV-000'").fetchone()[0]
    receive(c,state['user'],supplies.get_item(c,state['user'],item_id),quantity='1')
    with export(page) as archive:
        (tmp_path/'stock-report.pptx').write_bytes(archive.fp.getvalue())
        assert archive.testzip() is None
        slides=[n for n in archive.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
        text='\n'.join(' '.join(ET.fromstring(archive.read(n)).itertext()) for n in slides)
        assert '31 matching catalog items' in text and '31 below critical level' in text
        assert 'Unit: Ream' in text and 'Unit: Box' not in text
        assert 'INV-000' in text and 'INV-030' in text and 'INV-031' not in text
        normalized=' '.join(text.split())
        assert '<img src=x onerror=' in normalized and 'Not set' in normalized
        assert len(slides)>4 # native table auto-pagination across every matching list page
        charts=[n for n in archive.namelist() if n.startswith('ppt/charts/chart') and n.endswith('.xml')]
        assert len(charts)==2
        for n in charts:
            chart=ET.fromstring(archive.read(n))
            assert chart.find('.//c:barChart',NS) is not None
            values=[int(v.text) for v in chart.findall('.//c:numCache/c:pt/c:v',NS)]
            assert sum(values)==31
        assert len([n for n in archive.namelist() if n.endswith('.xlsx')])==2
        # Parse every XML part, including chart workbooks' parent relationships.
        for n in archive.namelist():
            if n.endswith(('.xml','.rels')):ET.fromstring(archive.read(n))
        assert b'<a:t>1</a:t>' in archive.read('ppt/slides/slide4.xml')
    assert page.evaluate('window.inventoryInjected') is None
    assert 'downloaded' in page.locator('#stock-presentation-status').inner_text()


def test_presentation_empty_failed_request_assets_and_revoked_permission(inventory_page):
    page,state,c=inventory_page
    page.set_viewport_size({'width':390,'height':844})
    page.goto('http://office.test/supplies/stock-dashboard?q=NO-MATCH')
    with export(page) as archive:
        assert not any(n.startswith('ppt/charts/chart') for n in archive.namelist())
        assert b'No recorded active items' in archive.read('ppt/slides/slide4.xml')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    page.route('**/supplies/stock-dashboard/presentation-data?**',lambda route:route.fulfill(
        status=400,content_type='application/json',body='{"error":"Narrow the dashboard filters before exporting."}'))
    page.get_by_role('button',name='Export PowerPoint report',exact=True).click()
    page.wait_for_function("document.getElementById('stock-presentation-status').textContent.includes('Narrow the dashboard')")
    assert page.get_by_role('button',name='Export PowerPoint report',exact=True).is_enabled()
    page.unroute('**/supplies/stock-dashboard/presentation-data?**')
    page.goto('http://office.test/supplies/stock-dashboard?active=all')
    c.execute("UPDATE supply_role_grant SET revoked_at='2026-10-24',revoked_by=? WHERE id=?",(state['user']['id'],state['grant']['id']));c.commit()
    with page.expect_response('**/supplies/stock-dashboard/presentation-data?**') as response:
        page.get_by_role('button',name='Export PowerPoint report',exact=True).click()
    assert response.value.status==403 and response.value.headers['cache-control']=='no-store'
    page.wait_for_function("!document.getElementById('stock-presentation-export').disabled")
    assert 'downloaded' not in page.locator('#stock-presentation-status').inner_text()
    page.route('**/static/vendor/pptxgenjs/**',lambda route:route.abort())
    page.goto('http://office.test/supplies/stock-dashboard')
    assert page.get_by_role('button',name='Export PowerPoint report',exact=True).is_disabled()
    assert 'could not load' in page.locator('#stock-presentation-status').inner_text()
    assert page.get_by_role('region',name='Physical stock counts').is_visible()
