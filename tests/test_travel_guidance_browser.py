"""A17 travel uses real local HTTP/form/SQLite journeys and recording external relays."""
import json
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

import storage as st
import travel
import travel_rules as rules
from tests.conftest import join_admin_section
from tests.test_document_guidance_browser import browser
from tests.test_rooms_guidance_browser import room_page as travel_page
from tests.test_travel_generate import conn, relay, mk
from tests.test_travel_relay import fake, env, ai_clean, PDF
from tests.test_travel_guidance import complete, LINK


def mutations(state):
    return [p for p in state['posts'] if p!='/telemetry' and not p.endswith('/rates')]


@pytest.mark.parametrize('width,theme',[(390,'light'),(1440,'dark')])
def test_next_step_link_reveals_focusses_and_saves_the_actual_checklist_row(travel_page,viewer,width,theme):
    page,state,c,context=travel_page
    ref=mk(viewer)
    page.set_viewport_size({'width':width,'height':900})
    context.add_init_script('localStorage.setItem("theme",'+json.dumps(theme)+')')
    page.goto(f'/travel/f/{ref}')
    target=page.locator('#item-dpo details')
    target.evaluate('(el)=>el.open=false')
    page.get_by_role('region',name='Travel next step').get_by_role('link',name='Add Department Personnel Order (DPO)').click()
    expect(target.locator('summary')).to_be_focused()
    assert target.locator('summary').evaluate('(el)=>el.tabIndex')==0
    target.get_by_role('textbox',name='Drive link for Department Personnel Order (DPO)').fill(LINK)
    target.get_by_role('button',name='Save link',exact=True).click()
    expect(page.locator('#item-dpo')).to_contain_text('Added')
    f=travel.get_by_ref(c,ref)
    assert next(i for i in travel.view_items(c,f) if i['code']=='dpo')['drive_url']==LINK
    assert mutations(state)==[f'/travel/f/{ref}/item/dpo']
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_rejected_link_and_answers_keep_entered_values_and_focus_the_error(travel_page,viewer):
    page,state,c,context=travel_page
    ref=mk(viewer)
    page.goto(f'/travel/f/{ref}')
    item=page.locator('#item-dpo')
    item.get_by_role('textbox',name='Drive link for Department Personnel Order (DPO)').fill('https://example.test/wrong')
    item.get_by_role('button',name='Save link',exact=True).click()
    expect(page.locator('#travel-form-error')).to_be_focused()
    expect(page.locator('#item-dpo input[name=drive_url]')).to_have_value('https://example.test/wrong')
    assert not next(i for i in travel.view_items(c,travel.get_by_ref(c,ref)) if i['code']=='dpo')['drive_url']
    page.locator('#item-dpo input[name=drive_url]').fill(LINK)
    page.locator('#item-dpo').get_by_role('button',name='Save link',exact=True).click()
    page.locator('#travel-answers > summary').click()
    page.locator('#dpo_no').fill('Draft DPO')
    page.locator('#advance_amount').fill('bad amount')
    page.locator('#travel-answers').get_by_role('button',name='Save answers',exact=True).click()
    expect(page.locator('#travel-form-error')).to_be_focused()
    expect(page.locator('#dpo_no')).to_have_value('Draft DPO')
    expect(page.locator('#advance_amount')).to_have_value('bad amount')
    assert travel.get_by_ref(c,ref)['dpo_no']=='2026-100'


def test_waiting_flag_and_supervisor_review_retain_note_then_unblock_the_filer(travel_page,viewer):
    page,state,c,context=travel_page
    ref=mk(viewer);f=complete(c,travel.get_by_ref(c,ref))
    travel.sync_flags(c,f,[rules.FlagSpec('participant_only','role','Participant-only travel')])
    flag=travel.flags_of(c,f['id'])[0]
    join_admin_section(c,st.get_admin_user(c,'viewer@test.local')['id'])
    page.goto(f'/travel/f/{ref}')
    guidance=page.get_by_role('region',name='Travel next step')
    expect(guidance).to_contain_text('Administrative Section')
    guidance.get_by_role('link',name='Open flag review queue').click()
    row=page.locator(f"#flag-{flag['id']}")
    row.get_by_role('textbox',name='Note (needed to reject)').fill('Draft supervisor note')
    row.get_by_role('button',name='Verified',exact=True).click()
    expect(page.locator('#travel-form-error')).to_be_focused()
    expect(row.get_by_role('textbox',name='Note (needed to reject)')).to_have_value('Draft supervisor note')
    assert travel.flags_of(c,f['id'])[0]['state']=='open'
    row.get_by_role('checkbox').check()
    row.get_by_role('button',name='Verified',exact=True).click()
    assert travel.flags_of(c,f['id'])[0]['state']=='verified'
    page.goto(f'/travel/f/{ref}')
    expect(page.get_by_role('region',name='Travel next step')).to_contain_text('Checklist complete')
    assert travel.get_by_ref(c,ref)['status']=='open'  # recording a flag review is separate from readiness/handover


def test_generation_read_failure_has_explicit_get_retry_and_preserves_draft(travel_page,viewer,relay):
    page,state,c,context=travel_page
    ref=mk(viewer);pattern=f'**/travel/f/{ref}/status'
    fail=lambda route:route.fulfill(status=503,body='Unavailable')
    page.route(pattern,fail)
    page.goto(f'/travel/f/{ref}/prepare')
    expect(page.get_by_role('button',name='Make the forms',exact=True)).to_be_disabled()
    page.get_by_role('textbox',name='Purpose (completes "To …")').fill('Retained purpose')
    expect(page.get_by_role('button',name='Check form progress',exact=True)).to_be_visible()
    page.unroute(pattern,fail)
    page.get_by_role('button',name='Check form progress',exact=True).click()
    expect(page.get_by_role('button',name='Make the forms',exact=True)).to_be_enabled()
    expect(page.get_by_role('textbox',name='Purpose (completes "To …")')).to_have_value('Retained purpose')
    assert not relay.calls and not mutations(state)


def test_lost_generation_response_checks_saved_forms_without_replaying_the_write(travel_page,viewer,relay):
    page,state,c,context=travel_page
    ref=mk(viewer);posts=[]
    def lose(route):
        request=route.request
        response=viewer.post(f'/travel/f/{ref}/generate',content=request.post_data_buffer,
            headers={'Content-Type':'application/json'})
        assert response.status_code==200,response.text
        posts.append(1);route.abort('failed')
    page.route(f'**/travel/f/{ref}/generate',lose)
    page.goto(f'/travel/f/{ref}/prepare')
    go=page.get_by_role('button',name='Make the forms',exact=True)
    expect(go).to_be_enabled()
    go.click()
    expect(page.get_by_text('The make-forms response was not confirmed.',exact=False)).to_be_visible()
    expect(page.locator('.tv-docs a').first).to_be_visible()
    assert posts==[1] and len(relay.calls)==2
    assert travel.get_by_ref(c,ref)['gen_state']=='done'
    page.wait_for_timeout(100)
    assert posts==[1] and len(relay.calls)==2


def test_duplicate_make_events_are_one_write_and_failed_replacement_keeps_earlier_link(travel_page,viewer,relay):
    page,state,c,context=travel_page
    ref=mk(viewer)
    page.goto(f'/travel/f/{ref}/prepare')
    go=page.get_by_role('button',name='Make the forms',exact=True)
    expect(go).to_be_enabled()
    go.evaluate("el=>{el.click();el.dispatchEvent(new MouseEvent('click',{bubbles:true}));}")
    expect(page.get_by_text('Done. Open each form',exact=False)).to_be_visible()
    assert mutations(state)==[f'/travel/f/{ref}/generate']
    assert len(relay.calls)==2
    old=next(i for i in travel.view_items(c,travel.get_by_ref(c,ref)) if i['code']=='appendix_a')['doc_url']
    relay.fail['claim_liq']='template_not_set'
    page.locator('.tv-docs li').filter(has_text='Appendix A').get_by_role('button',name='Make this form again').click()
    expect(page.get_by_text('Some forms did not finish.',exact=False)).to_be_visible()
    row=page.locator('.tv-docs li').filter(has_text='Appendix A')
    expect(row.get_by_role('link',name='Open earlier copy')).to_have_attribute('href',old)
    page.get_by_role('link',name='Continue to checklist',exact=True).click()
    expect(page.locator('#item-appendix_a')).to_contain_text('Latest attempt failed')
    expect(page.locator('#item-appendix_a')).to_contain_text('Open the earlier form')


@pytest.mark.parametrize('confirmed_before',[0,1])
@pytest.mark.parametrize('failure',['fetch','body'])
def test_lost_upload_response_stops_batch_and_checks_saved_files(travel_page,viewer,fake,env,ai_clean,confirmed_before,failure):
    page,state,c,context=travel_page
    st.set_setting(c,'travel.relay_version','2')
    ref=mk(viewer);posts=[]
    def lose(route):
        request=route.request;parts=urlsplit(request.url)
        response=viewer.post(parts.path+'?'+parts.query,content=request.post_data_buffer,
            headers={'Content-Type':request.headers['content-type'],'X-Filename':request.headers['x-filename']})
        assert response.status_code==200,response.text
        posts.append(1)
        if len(posts)<=confirmed_before or failure=='body':
            route.fulfill(status=response.status_code,body=response.content,
                headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','set-cookie')})
        else:
            route.abort('failed')
    page.route(f'**/travel/f/{ref}/upload?*',lose)
    if failure=='body':
        page.add_init_script('''(function () {
          var original = window.fetch, uploads = 0;
          window.fetch = function (url, options) {
            return original.apply(this, arguments).then(function (response) {
              if (String(url).includes('/upload?') && ++uploads > CONFIRMED) {
                response.text = function () { return Promise.reject(new TypeError('Body read interrupted')); };
              }
              return response;
            });
          };
        })();'''.replace('CONFIRMED',str(confirmed_before)))
    page.goto(f'/travel/f/{ref}')
    page.locator('#item-dpo input[type=file]').set_input_files([
        {'name':f'file-{i}.pdf','mimeType':'application/pdf','buffer':PDF} for i in range(confirmed_before+2)])
    expect(page.locator('#item-dpo')).to_contain_text('upload result was not confirmed')
    page.wait_for_timeout(1800)  # The old automatic retry fired after 1500ms.
    assert len(posts)==len(fake.uploads)==confirmed_before+1
    assert next(i for i in travel.view_items(c,travel.get_by_ref(c,ref)) if i['code']=='dpo')['drive_source']=='upload'
    page.get_by_role('link',name='Check saved files',exact=True).click()
    expect(page.locator('#item-dpo').get_by_role('link',name='Open the folder')).to_be_visible()
    assert len(posts)==confirmed_before+1


def test_closed_during_edit_keeps_readonly_details_and_does_not_save(travel_page,viewer):
    page,state,c,context=travel_page
    ref=mk(viewer)
    page.goto(f'/travel/f/{ref}#travel-answers')
    page.locator('#dpo_no').fill('Unsaved after handover')
    f=complete(c,travel.get_by_ref(c,ref));travel.mark_submitted(c,travel.mark_ready(c,f))
    page.get_by_role('button',name='Save answers',exact=True).click()
    expect(page.locator('#travel-form-error')).to_be_focused()
    expect(page.get_by_role('region',name='Unsaved travel details')).to_contain_text('Unsaved after handover')
    expect(page.get_by_role('button',name='Save answers',exact=True)).to_have_count(0)
    assert travel.get_by_ref(c,ref)['dpo_no']=='2026-100'


def test_no_script_ready_and_paper_submission_use_actual_native_forms(travel_page,viewer):
    page,state,c,context=travel_page
    ref=mk(viewer);complete(c,travel.get_by_ref(c,ref))
    cdp=context.new_cdp_session(page);cdp.send('Emulation.setScriptExecutionDisabled',{'value':True})
    page.goto(f'/travel/f/{ref}/ready')
    page.get_by_role('button',name='Mark ready',exact=True).click()
    assert travel.get_by_ref(c,ref)['status']=='ready'
    page.get_by_role('button',name='Mark submitted',exact=True).click()
    assert travel.get_by_ref(c,ref)['status']=='submitted'
    expect(page.get_by_role('region',name='Travel next step')).to_contain_text('Paper submission recorded')
    assert mutations(state)==[f'/travel/f/{ref}/ready',f'/travel/f/{ref}/submit']


def test_admin_section_view_keeps_other_filing_controls_read_only(travel_page,viewer,encoder):
    page,state,c,context=travel_page
    ref=mk(encoder)
    join_admin_section(c,st.get_admin_user(c,'viewer@test.local')['id'])
    page.goto(f'/travel/f/{ref}')
    expect(page.get_by_role('region',name='Travel next step')).to_contain_text('traveller owns checklist changes')
    expect(page.get_by_role('button',name='Save link',exact=True)).to_have_count(0)
    expect(page.get_by_role('button',name='Save answers',exact=True)).to_have_count(0)
    assert not mutations(state)
