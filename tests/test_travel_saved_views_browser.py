"""Real native saved-view forms across responsive themes and JavaScript absence."""
import csv
import io
import pytest
from playwright.sync_api import expect
from tests.test_travel_grid import claims
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_travel_grid_browser import claims_page


@pytest.mark.parametrize('width',[320,390,1440])
@pytest.mark.parametrize('theme',['light','dark','contrast'])
def test_private_native_save_open_replace_delete_and_csv(claims_page,width,theme):
    page,context,base,state=claims_page
    page.set_viewport_size({'width':width,'height':900});context.add_init_script(f"localStorage.setItem('theme','{theme}')")
    page.goto(base+'/travel/table?q=Visit+035&sort=ref_code&dir=desc')
    page.locator('#claims-saved-views summary').click()
    page.get_by_label('New saved view name').fill('My review')
    page.get_by_role('button',name='Save current selection',exact=True).click()
    expect(page.get_by_role('status',exact=False).filter(has_text='Saved views updated')).to_be_visible()
    expect(page.get_by_label('Reference or activity')).to_have_value('Visit 035')
    page.get_by_label('Reference or activity').fill('Visit 034')  # draft is not yet applied
    page.get_by_role('link',name='Open saved view: My review',exact=True).click()
    expect(page.get_by_label('Reference or activity')).to_have_value('Visit 035')
    expect(page.locator('#claims-native')).to_contain_text('TF-2610-0035')
    page.get_by_role('button',name='Open interactive table').click()
    expect(page.locator('#claims-status')).to_contain_text('1 matching filings')
    with page.expect_download() as capture:page.get_by_role('link',name='Export current selection (CSV)').click()
    rows=list(csv.reader(io.StringIO(capture.value.path().read_text(encoding='utf-8-sig'))))
    assert len(rows)==2 and rows[1][0]=='TF-2610-0035'
    page.get_by_label('Reference or activity').fill('Visit 034')
    page.get_by_role('button',name='Apply selection').click()
    page.locator('#claims-saved-views summary').click()
    page.get_by_role('button',name='Replace saved selection: My review',exact=True).click()
    page.get_by_role('link',name='Open saved view: My review',exact=True).click()
    expect(page.get_by_label('Reference or activity')).to_have_value('Visit 034')
    page.locator('#claims-saved-views summary').click()
    page.get_by_role('button',name='Delete saved view: My review',exact=True).click()
    expect(page.locator('#claims-saved-views')).to_contain_text('No saved claims views yet')
    page.wait_for_load_state('load')
    page.evaluate('document.fonts.ready')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), page.evaluate("Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,12).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().width])")
    assert not state['errors'] and state['posts']==['/travel/table/views']*3


def test_no_javascript_and_untrusted_names_are_plain_text(claims_page):
    page,context,base,state=claims_page
    context.new_cdp_session(page).send('Emulation.setScriptExecutionDisabled',{'value':True})
    page.goto(base+'/travel/table?status=open')
    page.locator('#claims-saved-views summary').click()
    name='<img src=x onerror=alert(1)>'
    page.get_by_label('New saved view name').fill(name)
    page.get_by_role('button',name='Save current selection',exact=True).click()
    expect(page.locator('#claims-saved-views h3')).to_have_text(name)
    assert page.locator('#claims-saved-views img').count()==0
    page.get_by_role('link',name='Open saved view: '+name,exact=True).click()
    expect(page.get_by_role('combobox',name='Filing status',exact=True)).to_have_value('open')
    assert not state['errors'] and state['posts']==['/travel/table/views']


def test_second_tab_cannot_overwrite_stale_revision(claims_page):
    page,context,base,state=claims_page
    page.goto(base+'/travel/table')
    page.locator('#claims-saved-views summary').click()
    page.get_by_label('New saved view name').fill('Two tabs')
    page.get_by_role('button',name='Save current selection',exact=True).click()
    second=context.new_page()
    try:
        second.goto(base+'/travel/table?q=Visit+035')
        second.locator('#claims-saved-views summary').click()
        second.get_by_role('button',name='Replace saved selection: Two tabs',exact=True).click()
        page.get_by_role('button',name='Delete saved view: Two tabs',exact=True).click()
        expect(page.get_by_role('alert')).to_contain_text('changed in another tab')
        second.get_by_role('link',name='Open saved view: Two tabs',exact=True).click()
        expect(second.get_by_label('Reference or activity')).to_have_value('Visit 035')
    finally:second.close()
