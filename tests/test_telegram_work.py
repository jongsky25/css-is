"""Private interactive work lookup with real linking and mocked provider only."""
import json

import pytest

import backups
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_work as reads
import work
from tests.test_work import workspace, case, document, propose, advance
from tests.test_telegram_bot import setup, update, submit, NOW
from tests.test_telegram_links import linking, claimed


@pytest.fixture
def work_env(linking, monkeypatch):
    c, users, path, client, payload = linking
    monkeypatch.setenv('CSS_TELEGRAM_WORK_READ_ENABLED', '1')
    _, _, confirmation = claimed(linking, scopes=['work.read'])
    submit(client, update(2, text='/confirm ' + confirmation))
    bot.process_updates(c, NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'")
    c.commit()
    return linking


def seed(env, owner=0, title='Synthetic work'):
    c, users, *_ = env
    unit = c.execute("SELECT id FROM org_unit WHERE path='WORK/D1'").fetchone()[0]
    item = case(c, users[0], unit, title=title)
    task = propose(c, users[0], item, unit, users[owner]['id'], title='Synthetic task')
    task = advance(c, users[1], task, 'confirm', owner_id=users[owner]['id'])
    return item, task


def lookup(env, text='/my_tasks', number=10):
    c, _, _, client, _ = env
    response = submit(client, update(number, text=text))
    assert response.status_code == 200
    bot.process_updates(c, NOW)
    found = rows(c, "SELECT * FROM telegram_delivery WHERE state='queued' ORDER BY id DESC LIMIT 1")
    if not found:
        return None
    delivery = found[0]
    return reads.render(c, delivery, json.loads(delivery['projection_json']), bot.transport.config(), NOW)


def test_own_tasks_and_current_status_without_submission_content(work_env):
    c, users, *_ = work_env
    item, task = seed(work_env)
    _, other = seed(work_env, owner=3)
    text = lookup(work_env)
    assert 'Task ' + str(task['id']) in text
    assert 'Task ' + str(other['id']) + ' ·' not in text
    assert 'Status: todo' in text
    c.execute("UPDATE work_task SET status='for_review',submission='Never expose private submission' WHERE id=?", (task['id'],)); c.commit()
    text = lookup(work_env, f"/task_status {item['id']} {task['id']}", 11)
    assert 'for review' in text and 'private submission' not in text
    assert '/work/' + str(item['id']) in text
    assert 'Never expose' not in c.execute('SELECT projection_json FROM telegram_delivery ORDER BY id DESC').fetchone()[0]
    assert '1 for review' in lookup(work_env, '/work_status ' + str(item['id']), 12)


def test_unowned_unknown_and_hidden_details_share_denial(work_env):
    item, task = seed(work_env, owner=3)
    assert lookup(work_env, f"/task_status {item['id']} {task['id']}") == lookup(work_env, '/task_status 99999 99999', 11)
    assert 'unavailable' in lookup(work_env, '/work_status 99999', 12)


def test_hidden_linked_document_removes_work_and_owned_tasks(work_env):
    c, users, *_ = work_env
    item, task = seed(work_env)
    unit = item['unit_id']
    doc = document(c, users[0], unit)
    work.link_document(c, users[0], item['id'], item['revision'], doc['id'])
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?", (doc['id'],))
    c.execute('DELETE FROM document_access WHERE document_id=?', (doc['id'],)); c.commit()
    assert 'No items' in lookup(work_env)
    assert 'No items' in lookup(work_env, '/my_work', 11)
    assert 'unavailable' in lookup(work_env, '/work_status ' + str(item['id']), 12)


@pytest.mark.parametrize('command', ['/my_tasks', '/my_work'])
def test_bounded_pages_and_private_unicode_budget(work_env, command):
    for i in range(12):
        seed(work_env, title='Synthetic work ' + str(i))
    text = lookup(work_env, command)
    assert 'Next page: ' + command in text
    next_command = text.split('Next page: ')[1].splitlines()[0]
    second = lookup(work_env, next_command, 11)
    assert 'Next page:' not in second
    assert reads.common.units(text) <= 4096


@pytest.mark.parametrize('text', ['/my_tasks 0', '/my_tasks -1', '/my_work 9223372036854775808', '/task_status 1', '/work_status invalid', '/my_tasks 1 2'])
def test_bad_arguments_do_not_read_records(work_env, monkeypatch, text):
    monkeypatch.setattr(reads, 'owned_tasks', lambda *a: pytest.fail('Bad task read'))
    monkeypatch.setattr(work, 'get', lambda *a: pytest.fail('Bad work read'))
    assert lookup(work_env, text) == reads.USAGE


@pytest.mark.parametrize('change', ['switch', 'grant', 'disconnect', 'deactivate', 'documents', 'work', 'restore'])
def test_revoke_between_enqueue_and_send_suppresses_read(work_env, monkeypatch, change):
    c, users, path, client, payload = work_env
    seed(work_env)
    submit(client, update(10, text='/my_tasks')); bot.process_updates(c, NOW)
    if change == 'switch': monkeypatch.setenv('CSS_TELEGRAM_WORK_READ_ENABLED', '0')
    elif change == 'grant': c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='work.read'", (links.stamp(NOW),)); c.commit()
    elif change == 'disconnect': links.disconnect(c, payload, NOW)
    elif change == 'deactivate': c.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[0]['id'],)); c.commit()
    elif change == 'restore': backups.clear_restored_sessions(path)
    else: st.set_setting(c, change + '.enabled', '0')
    monkeypatch.setattr(reads, 'owned_tasks', lambda *a: pytest.fail('Revoked source read'))
    monkeypatch.setattr(bot.transport, 'send', lambda *a: pytest.fail('Revoked send'))
    assert bot.deliver(c, NOW) == 0


def test_webhook_reply_deduplicates_and_never_calls_outbound(work_env, monkeypatch):
    c, _, _, client, _ = work_env
    item, task = seed(work_env)
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT', 'webhook')
    monkeypatch.setattr(bot.transport, 'send', lambda *a: pytest.fail('Outgoing send'))
    message = update(10, text='/my_tasks')
    reply = submit(client, message).json()
    assert reply['method'] == 'sendMessage' and reply['chat_id'] == 101
    assert 'Synthetic task' in reply['text']
    assert 'method' not in submit(client, message).json()
    assert bot.deliver(c, NOW) == 0
    assert c.execute("SELECT count(*) FROM telegram_delivery WHERE error_code='webhook_response' AND state='uncertain'").fetchone()[0] == 1


def test_calendar_grant_does_not_allow_work_and_groups_are_ignored(work_env):
    c, _, _, client, _ = work_env
    seed(work_env)
    c.execute("UPDATE telegram_grant SET action='calendar.read' WHERE action='work.read'"); c.commit()
    assert lookup(work_env) is None
    message = update(11, text='/my_tasks')
    message['message']['chat'] = {'id': -100, 'type': 'group'}
    assert submit(client, message).status_code == 200
    assert c.execute('SELECT state FROM telegram_update WHERE update_id=11').fetchone()[0] == 'ignored'


def test_source_access_is_rechecked_after_enqueue(work_env, monkeypatch):
    c, users, _, client, _ = work_env
    item, task = seed(work_env)
    submit(client, update(10, text='/my_tasks')); bot.process_updates(c, NOW)
    doc = document(c, users[0], item['unit_id'])
    work.link_document(c, users[0], item['id'], item['revision'], doc['id'])
    c.execute("UPDATE document SET visibility='restricted' WHERE id=?", (doc['id'],))
    c.execute('DELETE FROM document_access WHERE document_id=?', (doc['id'],)); c.commit()
    sent = []
    monkeypatch.setattr(bot.transport, 'send', lambda token, chat, text: sent.append(text) or ('accepted', 1, None))
    assert bot.deliver(c, NOW) == 1
    assert 'No items' in sent[0] and 'Synthetic task' not in sent[0]


@pytest.mark.parametrize('command', ['/my_work', '/work_status 1', '/task_status 1 1'])
def test_all_lookup_commands_work_through_webhook(work_env, monkeypatch, command):
    seed(work_env)
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT', 'webhook')
    monkeypatch.setattr(bot.transport, 'send', lambda *a: pytest.fail('Outgoing send'))
    reply = submit(work_env[3], update(10, text=command)).json()
    assert reply['method'] == 'sendMessage'
    assert 'Synthetic' in reply['text']


def test_paging_filters_unauthorized_work_before_limit(work_env):
    c, users, *_ = work_env
    mine, task = seed(work_env)
    for i in range(12):
        case(c, users[3], mine['unit_id'], title='Hidden item ' + str(i))
    text = lookup(work_env, '/my_work')
    assert 'Synthetic work' in text and 'Hidden item' not in text
    assert 'Next page' not in text
