"""Actual CSV downloads from native and interactive claims selections."""
import csv
import io
import pytest
from playwright.sync_api import expect
import travel_grid as grid
from tests.test_travel_grid import claims
from tests.test_travel_grid_browser import claims_page
from tests.test_document_registry_grid_browser import grid_browser


def downloaded(page):
    with page.expect_download() as capture:
        page.get_by_role('link',name='Export current selection (CSV)').click()
    download=capture.value
    assert download.suggested_filename=='travel-claims.csv' and download.failure() is None
    return list(csv.reader(io.StringIO(download.path().read_text(encoding='utf-8-sig'))))


@pytest.mark.parametrize('width',[320,390,1440])
@pytest.mark.parametrize('theme',['light','dark','contrast'])
def test_export_applied_selection_in_both_modes_and_ignores_draft_controls(claims_page,width,theme):
    page,context,base,state=claims_page
    page.set_viewport_size({'width':width,'height':900})
    context.add_init_script(f"localStorage.setItem('theme','{theme}')")
    page.goto(base+'/travel/table?sort=ref_code&dir=desc&page=2')
    assert len(downloaded(page))==36  # all pages, not just this five-row native page
    page.get_by_role('button',name='Open interactive table').click()
    expect(page.locator('#claims-status')).to_contain_text('Interactive page 2 of 2')
    page.get_by_label('Reference or activity').fill('Visit 035')
    rows=downloaded(page)
    assert len(rows)==36 and rows[1][0]=='TF-2610-0035' and rows[-1][0]=='TF-2610-0001'
    assert all('OTHER_PRIVATE_CLAIM' not in str(row) for row in rows)
    page.get_by_role('button',name='Apply selection').click()
    rows=downloaded(page)
    assert len(rows)==2 and rows[1][0]=='TF-2610-0035'
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not state['errors'] and not state['posts']


def test_no_javascript_native_download(claims_page):
    page,context,base,state=claims_page
    context.new_cdp_session(page).send('Emulation.setScriptExecutionDisabled',{'value':True})
    page.goto(base+'/travel/table?sort=ref_code&dir=asc')
    rows=downloaded(page)
    assert len(rows)==36 and rows[1][0]=='TF-2610-0001' and rows[-1][0]=='TF-2610-0035'
    assert not state['errors'] and not state['posts']


def test_refused_export_has_usable_return_link_and_no_partial_file(claims_page,monkeypatch):
    page,context,base,state=claims_page
    monkeypatch.setattr(grid,'MAX_EXPORT_ROWS',2)
    page.goto(base+'/travel/table?sort=ref_code&dir=asc&q=Visit')
    page.get_by_role('link',name='Export current selection (CSV)').click()
    expect(page.get_by_role('alert')).to_contain_text('Narrow the search or filters')
    page.get_by_role('link',name='Return to claims table').click()
    expect(page.get_by_label('Reference or activity')).to_have_value('Visit')
    assert page.get_by_label('Sort by').input_value()=='ref_code'
    assert not state['errors'] and not state['posts']
