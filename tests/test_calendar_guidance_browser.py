"""Real local HTTP calendar reads, decisions, form POSTs and saved results."""
import json
from datetime import date

import pytest
from playwright.sync_api import expect

import storage as st
import recurrence
from tests.test_calendar_entry_pages import conn
from tests.test_document_guidance_browser import browser
# Reuse the local HTTP adapter (actual TestClient requests/303s; external hosts blocked).
from tests.test_rooms_guidance_browser import room_page as calendar_page, room_writes as writes

DAY='2026-10-25'


def make(conn, title='CALEP Browser', **kw):
    return st.cal_create(conn,title,DAY,audience='bureau',**kw)


def next_step(scope):
    """The next-step guidance sits in a collapsed "Schedule status and next steps"
    card (9.44); open it without moving focus, then return the guidance region."""
    scope.locator('details.cal-work-card:has(.cal-guidance)').evaluate('d=>{d.open=true}')
    return scope.get_by_role('region',name='Calendar next step')


def open_item(page,eid):
    page.goto('/calendar?day='+DAY)
    link=page.locator(f'.cal-tt[href="/calendar/entries/{eid}"]').first
    link.focus();link.press('Enter')
    expect(page.get_by_role('dialog',name='CALEP Browser',exact=True)).to_be_visible()
    return link


@pytest.mark.parametrize('width,theme',[(390,'light'),(1440,'dark')])
def test_sheet_guidance_focus_and_cancellation_review_then_actual_save(calendar_page,width,theme):
    page,state,c,context=calendar_page
    page.set_viewport_size({'width':width,'height':900})
    context.add_init_script('localStorage.setItem("theme",'+json.dumps(theme)+')')
    eid=make(c,status='tentative')
    link=open_item(page,eid)
    sheet=page.locator('#cal-sheet')
    expect(next_step(sheet)).to_contain_text('Tentative')
    close=sheet.get_by_role('button',name='Close',exact=True)
    close.focus()
    # Native dialog confines focus and Escape returns to the actual item link.
    first=sheet.get_by_role('link',name='Open full page')
    first.focus();first.press('Shift+Tab')
    expect(sheet.locator('.cal-history > summary')).to_be_focused()
    page.keyboard.press('Tab');expect(first).to_be_focused()
    page.keyboard.press('Escape');expect(link).to_be_focused()
    expect(sheet).not_to_be_visible()
    link.press('Enter')
    expect(next_step(sheet)).to_be_visible()
    assert not writes(state)
    sheet.get_by_role('link',name='Cancel item — review first').click()
    expect(page.get_by_role('heading',name='Review calendar cancellation')).to_be_visible()
    assert st.cal_get(c,eid)['status']=='tentative' and not writes(state)
    page.get_by_role('link',name='Keep item and go back').click()
    assert st.cal_get(c,eid)['status']=='tentative'
    page.get_by_role('link',name='Cancel item — review first').click()
    page.get_by_role('button',name='Confirm cancellation').click()
    expect(next_step(page)).to_contain_text('Cancelled on the office calendar')
    assert writes(state)==[f'/calendar/entries/{eid}/cancel']
    assert st.cal_get(c,eid)['status']=='cancelled'
    page.get_by_role('button',name='Restore',exact=True).click()
    expect(next_step(page)).to_contain_text('Tentative')
    assert st.cal_get(c,eid)['status']=='tentative'
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_sheet_failed_read_explicit_retry_and_closed_stale_success_are_harmless(calendar_page):
    page,state,c,context=calendar_page
    eid=make(c)
    path=f'**/calendar/entries/{eid}'
    fail=lambda route:route.fulfill(status=503,body='Unavailable')
    page.route(path,fail)
    page.goto('/calendar?day='+DAY)
    link=page.locator(f'.cal-tt[href="/calendar/entries/{eid}"]').first
    link.click()
    sheet=page.locator('#cal-sheet')
    expect(sheet.get_by_role('alert')).to_contain_text('Nothing was changed')
    expect(sheet.get_by_role('link',name='Open full page')).to_have_attribute('href',f'/calendar/entries/{eid}')
    page.unroute(path,fail)
    sheet.get_by_role('button',name='Try loading again').click()
    expect(next_step(sheet)).to_contain_text('Confirmed on')
    page.keyboard.press('Escape');expect(sheet).not_to_be_visible()
    # A delayed read cannot reopen the sheet after native Escape dismissal.
    delayed=[]
    page.route(path,lambda route:delayed.append(route))
    link.click()
    expect(sheet.get_by_role('status')).to_contain_text('Loading')
    page.keyboard.press('Escape');expect(sheet).not_to_be_visible()
    assert delayed
    delayed[0].fulfill(status=200,body='<article class="cal-detail"><h1>Late result</h1></article>',content_type='text/html')
    page.wait_for_timeout(80)
    expect(sheet).not_to_be_visible()
    assert 'Late result' not in page.locator('[data-sheet-body]').inner_text()
    assert not writes(state) and st.cal_get(c,eid)['sequence']==0


def test_stale_failure_cannot_replace_new_item_or_navigate(calendar_page):
    page,state,c,context=calendar_page
    first=make(c); second=make(c,title='CALEP Second',status='postponed')
    delayed=[]
    page.route(f'**/calendar/entries/{first}',lambda route:delayed.append(route))
    page.goto('/calendar?day='+DAY)
    page.locator(f'.cal-tt[href="/calendar/entries/{first}"]').first.click()
    expect(page.locator('#cal-sheet')).to_be_visible()
    page.keyboard.press('Escape')
    page.locator(f'.cal-tt[href="/calendar/entries/{second}"]').first.click()
    expect(page.locator('#cal-sheet')).to_contain_text('Postponed — a new schedule needs checking')
    delayed[0].fulfill(status=503,body='Old failure')
    page.wait_for_timeout(80)
    expect(page.locator('#cal-sheet')).to_contain_text('Postponed — a new schedule needs checking')
    assert '/calendar?' in page.url and not writes(state)


def test_edit_conflict_focuses_message_retains_draft_and_saves_only_explicit_replacement(calendar_page):
    page,state,c,context=calendar_page
    eid=make(c)
    page.set_viewport_size({'width':390,'height':900})
    page.goto(f'/calendar/entries/{eid}/edit')
    page.locator('input[name=venue]').fill('My draft venue')
    c.execute("UPDATE calendar_entry SET venue='Other edit',updated_at='2099-01-01T00:00:00' WHERE id=?",(eid,));c.commit()
    page.get_by_role('button',name='Save changes',exact=True).click()
    expect(page.locator('#cal-form-message')).to_be_focused()
    expect(page.locator('input[name=venue]')).to_have_value('My draft venue')
    expect(page.get_by_role('link',name='View current item in a new tab')).to_have_attribute('target','_blank')
    assert st.cal_get(c,eid)['venue']=='Other edit'
    assert writes(state)==[f'/calendar/entries/{eid}/edit']
    page.get_by_role('button',name='Replace with my changes').click()
    expect(next_step(page)).to_be_visible()
    assert st.cal_get(c,eid)['venue']=='My draft venue'


def test_cancelled_during_edit_keeps_details_and_no_save_control(calendar_page):
    page,state,c,context=calendar_page
    eid=make(c)
    page.goto(f'/calendar/entries/{eid}/edit')
    page.locator('input[name=title]').fill('CALEP Draft after cancellation')
    st.cal_cancel(c,eid)
    page.get_by_role('button',name='Save changes',exact=True).click()
    expect(page.locator('#cal-form-message')).to_be_focused()
    expect(page.locator('input[name=title]')).to_have_value('CALEP Draft after cancellation')
    expect(page.get_by_role('button',name='Save changes',exact=True)).to_have_count(0)
    expect(page.get_by_role('link',name='Review cancelled item in a new tab')).to_be_visible()
    assert st.cal_get(c,eid)['status']=='cancelled'


def test_server_validation_focuses_error_and_preserves_all_draft_fields(calendar_page):
    page,state,c,context=calendar_page
    page.goto('/calendar/new?day='+DAY)
    page.locator('input[name=title]').fill('CALEP Kept draft')
    page.locator('select[name=audience]').select_option('bureau')
    page.locator('input[name=end_date]').fill('2026-10-01')
    page.get_by_role('button',name='Add to the calendar',exact=True).click()
    expect(page.locator('#cal-form-message')).to_be_focused()
    expect(page.locator('input[name=title]')).to_have_value('CALEP Kept draft')
    expect(page.locator('input[name=end_date]')).to_have_value('2026-10-01')
    assert not c.execute("SELECT 1 FROM calendar_entry WHERE title='CALEP Kept draft'").fetchone()


def test_subscription_settings_are_explicit_and_token_revocation_is_real(calendar_page):
    page,state,c,context=calendar_page
    page.set_viewport_size({'width':390,'height':900})
    page.goto('/me#calendar-feed')
    box=page.locator('#calendar-feed')
    expect(box).to_contain_text('No active subscription link')
    page.get_by_role('button',name='Create my calendar link').click()
    expect(box).to_contain_text('Subscription link active')
    old=st.feed_get(c,st.get_admin_user(c,'viewer@test.local')['id'])['token']
    box.locator('select[name=scope]').select_option('section')
    box.get_by_role('checkbox').check()
    box.get_by_role('button',name='Save subscription settings').click()
    expect(box).to_contain_text('Current selection: My section; birthdays included')
    box.get_by_text('How to subscribe and check missing updates',exact=True).click()
    expect(box).to_contain_text('Use a subscription, not a file import')
    page.get_by_role('button',name='Turn the link off',exact=True).click()
    expect(box).to_contain_text('No active subscription link')
    assert not st.feed_owner(c,old)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_native_no_script_review_cancel_and_restore(calendar_page):
    page,state,c,context=calendar_page
    eid=make(c)
    cdp=context.new_cdp_session(page)
    cdp.send('Emulation.setScriptExecutionDisabled',{'value':True})
    page.goto(f'/calendar/entries/{eid}')
    page.get_by_role('link',name='Cancel item — review first').click()
    expect(page.get_by_role('heading',name='Review calendar cancellation')).to_be_visible()
    assert not writes(state)
    page.get_by_role('button',name='Confirm cancellation').click()
    assert st.cal_get(c,eid)['status']=='cancelled'
    page.get_by_role('button',name='Restore',exact=True).click()
    assert st.cal_get(c,eid)['status']=='confirmed'


def test_bookmarked_preview_back_forward_and_quick_add_return_focus(calendar_page):
    page,state,c,context=calendar_page
    eid=make(c)
    page.goto(f'/calendar?day={DAY}&item={eid}')
    sheet=page.locator('#cal-sheet')
    expect(next_step(sheet)).to_be_visible()
    page.keyboard.press('Escape')
    expect(sheet).not_to_be_visible()
    page.wait_for_url(lambda url:'item=' not in str(url))
    link=page.locator(f'.cal-tt[href="/calendar/entries/{eid}"]').first
    link.click()
    expect(next_step(sheet)).to_be_visible()
    page.go_back();expect(sheet).not_to_be_visible()
    page.go_forward();expect(next_step(sheet)).to_be_visible()
    page.keyboard.press('Escape');expect(link).to_be_focused()
    quick=page.locator('.cal-dayadd').first
    quick.focus();quick.press('Enter')
    dialog=page.get_by_role('dialog',name='Quick add',exact=True)
    expect(dialog.get_by_role('textbox',name='What is it?')).to_be_focused()
    dialog.get_by_role('textbox',name='What is it?').fill('Draft for more options')
    dialog.get_by_role('link',name='More options').click()
    expect(page.locator('input[name=title]')).to_have_value('Draft for more options')
    assert not writes(state)


def test_recurring_occurrence_keeps_query_deep_link_and_single_date_controls(calendar_page):
    page,state,c,context=calendar_page
    eid=make(c,rrule=recurrence.build('weekly',date.fromisoformat(DAY),date(2026,11,29)))
    page.goto('/calendar?day=2026-11-01')
    link=page.locator(f'.cal-tt[href="/calendar/entries/{eid}?date=2026-11-01"]').first
    expect(link).to_be_visible()
    link.click()
    page.wait_for_url(f'**/calendar/entries/{eid}?date=2026-11-01')
    expect(page.get_by_role('link',name='Change just this one',exact=True)).to_have_attribute('href',f'/calendar/entries/{eid}/detach?date=2026-11-01')
    expect(next_step(page)).to_contain_text('only the selected occurrence')
    assert not writes(state)


def test_queued_close_event_cannot_clear_preview_reopened_by_history(calendar_page):
    page,state,c,context=calendar_page
    eid=make(c)
    page.goto(f'/calendar?day={DAY}&item={eid}')
    sheet=page.locator('#cal-sheet')
    expect(next_step(sheet)).to_be_visible()
    # Deterministically deliver the two traversal states in one task. The native
    # dialog close event is still queued when the second popstate reopens it.
    page.evaluate('''() => {
      const openURL=location.href;
      const closedURL=new URL(openURL);closedURL.searchParams.delete('item');
      history.replaceState(null,'',closedURL);dispatchEvent(new PopStateEvent('popstate'));
      history.replaceState(null,'',openURL);dispatchEvent(new PopStateEvent('popstate'));
    }''')
    expect(next_step(sheet)).to_be_visible()
    expect(sheet.get_by_role('button',name='Close',exact=True)).to_be_focused()
    assert page.locator('#cal-f').evaluate('(el)=>el.inert')
    assert not writes(state) and st.cal_get(c,eid)['sequence']==0
