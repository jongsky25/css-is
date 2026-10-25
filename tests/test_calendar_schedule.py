"""Time semantics, complete authorized snapshots, native views and preference reuse."""
from datetime import date, timedelta, timezone
import json
import re

import pytest
import calendar_schedule as sc
import storage as st
import tzutil as tz
from tests.conftest import in_the_directory

DAY = '2026-10-20'
START, END = date(2026,10,19), date(2026,10,25)


def item(**over):
    return dict(key='entry:1',title='Synthetic meeting',start=DAY,end=DAY,
                start_time='09:00',end_time='10:00',all_day=False,url='/calendar/entries/1',
                owner_label='Synthetic unit',status='confirmed',tone='blue',**over)


def payload(values):
    return sc.snapshot(values,START,END,date.fromisoformat(DAY),date.fromisoformat(DAY))


def test_real_times_office_offset_and_inclusive_all_day_dates():
    a=item();b={**a,'key':'entry:2','start_time':None,'end_time':None,'all_day':True,'end':'2026-10-22','time_note':'AM'}
    result=payload([a,b]);assert result['available']
    first,second=result['events']
    assert first['start']=='2026-10-20T09:00:00+08:00' and first['end']=='2026-10-20T10:00:00+08:00'
    assert not first['allDay'] and second['allDay'] and second['end']=='2026-10-23'
    assert second['extendedProps']['timeLabel']=='AM'
    assert result['end']=='2026-10-26' and len(result['days'])==7


def test_no_duration_is_invented_for_incomplete_times():
    result=payload([{**item(),'end_time':None}])['events'][0]
    assert result['allDay'] and result['start']==DAY and result['end']=='2026-10-21'
    assert result['extendedProps']['timeLabel']=='09:00 · End time not set'
    end_only=payload([{**item(),'start_time':None}])['events'][0]
    assert end_only['allDay'] and end_only['extendedProps']['timeLabel']=='Ends 10:00 · Start time not set'


def test_complete_overnight_interval_keeps_both_recorded_dates():
    result=payload([{**item(),'start_time':'23:30','end':'2026-10-21','end_time':'01:15'}])['events'][0]
    assert result['start']=='2026-10-20T23:30:00+08:00'
    assert result['end']=='2026-10-21T01:15:00+08:00' and not result['allDay']


def test_configured_office_timezone_is_respected(monkeypatch):
    monkeypatch.setattr(tz,'LOCAL_TZ',timezone(timedelta(hours=-5)))
    result=payload([item()]);assert result['zone']=='UTC-05:00'
    assert result['label']=='Office time (UTC-05:00)'
    assert result['events'][0]['start'].endswith('-05:00')


def test_payload_is_minimal_and_never_links_to_external_locations():
    source={**item(),'url':'//external.example/secret','note':'PRIVATE NOTE','meeting_url':'https://secret.example',
            'people':[{'name':'PRIVATE PERSON'}],'css':{'private':'PRIVATE SCORE'}}
    result=payload([source]);assert result['events'][0]['extendedProps']['href']==''
    assert 'PRIVATE' not in json.dumps(result) and 'secret' not in json.dumps(result)


def test_oversized_or_invalid_snapshot_keeps_full_list_without_partial_grid(monkeypatch):
    monkeypatch.setattr(sc,'MAX_ITEMS',1)
    result=payload([item(),item()]);assert not result['available'] and result['events']==[]
    monkeypatch.setattr(sc,'MAX_ITEMS',500)
    result=payload([item(),{**item(),'end_time':'08:00'}])
    assert not result['available'] and result['events']==[]


@pytest.fixture
def conn(app_mod):
    c=st.connect(app_mod.DB);yield c;c.close()


def seed(conn,title='CALSP Clock',**over):
    args={'audience':'bureau','start_time':'09:00','end_time':'10:00',**over}
    return st.cal_create(conn,title,DAY,**args)


@pytest.mark.parametrize('path',['/calendar?view=schedule','/?view=calendar&layout=schedule'])
def test_native_week_filter_scope_bounds_and_no_store(viewer,conn,path):
    eid=seed(conn);seed(conn,'CALSP Hidden',audience='unit')
    seed(conn,'CALSP Later',end_date='2026-10-28')
    st.cal_create(conn,'CALSP Outside','2026-10-27',audience='bureau')
    response=viewer.get(path+'&day='+DAY+'&q=CALSP')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    data=response.context['schedule'];assert data['start']=='2026-10-19' and data['end']=='2026-10-26'
    assert {e['title'] for e in data['events']}=={'CALSP Clock','CALSP Later'}
    assert f'/calendar/entries/{eid}' in response.text and 'CALSP Hidden' not in response.text
    assert 'CALSP Outside' not in response.text and 'Full week as a list' in response.text
    assert 'day=2026-10-12' in response.text and 'day=2026-10-26' in response.text
    form=response.text.split('<form id="cal-f"',1)[1].split('</form>',1)[0]
    assert form.count('name="q"')==1
    assert 'value="CALSP"' in response.text
    assert viewer.get(path+'&day='+DAY+'&q=CALSP&kind=travel').context['schedule']['events']==[]


def test_current_unit_visibility_applies_before_snapshot(app_mod,viewer,conn):
    with in_the_directory(app_mod,'viewer@test.local',path='CALSP/D1/S1'):
        unit=conn.execute("SELECT id FROM org_unit WHERE path='CALSP/D1/S1'").fetchone()[0]
        eid=seed(conn,'CALSP Team',audience='unit',owner_org_id=unit)
        try:
            response=viewer.get('/calendar?view=schedule&day='+DAY+'&scope=section&q=CALSP')
            assert [e['title'] for e in response.context['schedule']['events']]==['CALSP Team']
            assert response.context['scope']=='section'
        finally:st.cal_delete(conn,eid)


def test_preferred_schedule_and_empty_invalid_or_oversized_fallback(viewer,conn,monkeypatch):
    response=viewer.post('/calendar/preference',data={'layout':'schedule','scope':'bureau','next':'/calendar'},follow_redirects=False)
    assert response.status_code==303 and viewer.cookies.get('cal_pref')=='schedule:bureau'
    assert viewer.get('/calendar').context['layout']=='schedule'
    empty=viewer.get('/calendar?view=schedule&day=2031-01-06&q=CALSP')
    assert empty.context['schedule']['events']==[] and 'Nothing else planned for this week' in empty.text
    assert viewer.get('/calendar?view=schedule&day=bad',follow_redirects=False).status_code==303
    seed(conn,'CALSP One');seed(conn,'CALSP Two');monkeypatch.setattr(sc,'MAX_ITEMS',1)
    response=viewer.get('/calendar?view=schedule&day='+DAY+'&q=CALSP')
    assert 'CALSP One' in response.text and 'CALSP Two' in response.text
    assert not response.context['schedule']['available'] and 'fullcalendar-with-timezone.js' not in response.text


def test_untrusted_title_is_json_escaped_and_snapshots_have_no_business_writes(viewer,conn):
    seed(conn,'CALSP </script><img src=x onerror=alert(1)>')
    before=conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0]
    response=viewer.get('/calendar?view=schedule&day='+DAY+'&q=CALSP')
    data=re.search(r'id="cal-schedule-data" type="application/json">(.*?)</script>',response.text,re.S).group(1)
    assert '<img' not in data and '</script>' not in data and '\\u003c' in data
    assert len(json.loads(data)['events'])==1
    assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0]==before
