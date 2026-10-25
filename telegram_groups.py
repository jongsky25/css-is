"""Explicit group/topic registration and allowlisted shared routing."""
import json
import secrets
import time
from datetime import timedelta

from documents_storage import rows, transaction
import storage as st
import telegram_links as links
import telegram_storage as switches
import telegram_transport as transport
import telegram_group_reads as shared

POLICY = 'bureau_shared_v1'
# Shared calendar projections additionally require exact-version disclosure consent.
SHARED_FIELDS = {
    'calendar': ('title','date','start_time','end_time','timezone','venue','status','source_link'),
    'rooms': ('date','slots','availability'),
}
STATUS = 'Office Connect group connection is registered. Shared lookup commands: /group_calendar and /group_rooms when separately enabled and consented. Joining this group grants no Office Connect access.'


def integer(value, *, positive=False):
    if type(value) is not int or not -(2**63) <= value < 2**63 or (positive and value <= 0):
        raise ValueError('Invalid Telegram identifier.')
    return value


def lifecycle(value):
    """Extract only routing events, never roster names, chat titles or message text."""
    for key in ('my_chat_member','chat_member'):
        if key not in value:
            continue
        item=value[key]
        if not isinstance(item,dict) or not isinstance(item.get('chat'),dict):
            raise ValueError('Invalid membership update.')
        if item['chat'].get('type') not in ('group','supergroup'):
            return None
        chat=integer(item['chat'].get('id'))
        if chat>=0 or not isinstance(item.get('from'),dict) or not isinstance(item.get('new_chat_member'),dict):
            raise ValueError('Invalid membership update.')
        member=item['new_chat_member'];user=member.get('user')
        if not isinstance(user,dict) or member.get('status') not in ('creator','administrator','member','restricted','left','kicked'):
            raise ValueError('Invalid membership update.')
        return {'chat_id':chat,'sender_id':integer(item['from'].get('id'),positive=True),
                'group_event':key,'member_id':integer(user.get('id'),positive=True),'member_status':member['status']}
    message=value.get('message')
    if not isinstance(message,dict) or not isinstance(message.get('chat'),dict) or message['chat'].get('type') not in ('group','supergroup'):
        return None
    chat=integer(message['chat'].get('id'))
    if chat>=0:
        raise ValueError('Invalid group.')
    for key in ('migrate_to_chat_id','migrate_from_chat_id'):
        if key in message:
            target=integer(message[key])
            if target>=0:
                raise ValueError('Invalid migration.')
            return {'chat_id':chat,'group_event':'migration','migration_target':target,'sender_id':None}
    if 'forum_topic_closed' in message or 'forum_topic_reopened' in message:
        return {'chat_id':chat,'topic_id':integer(message.get('message_thread_id'),positive=True),
                'group_event':'topic_changed','sender_id':None}
    if 'left_chat_member' in message:
        member=message['left_chat_member']
        if not isinstance(member,dict):
            raise ValueError('Invalid member.')
        return {'chat_id':chat,'group_event':'departed','member_id':integer(member.get('id'),positive=True),
                'member_status':'left','sender_id':None}
    return None


def linked(conn, account_id, admin=False):
    found=rows(conn,'''SELECT c.*,u.role FROM telegram_connection c JOIN admin_user u ON u.id=c.account_id
        WHERE c.account_id=? AND c.state='active' AND u.active=1 AND u.must_change=0
        AND u.role IN ('viewer','encoder','section_manager','admin')''',(account_id,))
    bot=transport.config()
    if not found or (admin and found[0]['role']!='admin'):
        raise ValueError('A current linked administrator account is required.' if admin else 'An active private account link is required.')
    if not bot or found[0]['bot_identity']!=bot[0] or found[0]['bot_fingerprint']!=bot[2]:
        raise ValueError('Disconnect and link your private account to the current bot again before using groups.')
    return found[0]


def observe(conn, clean, bot, now):
    """Within the durable webhook transaction. No provider calls or group replies."""
    if not (switches.enabled('groups') and switches.enabled('link')):
        return
    found=rows(conn,'SELECT account_id FROM telegram_connection WHERE telegram_user_id=? AND state=\'active\'',(clean['sender_id'],))
    if not found:
        return
    try:
        owner=linked(conn,found[0]['account_id'],admin=True)
    except ValueError:
        return
    conn.execute('''INSERT INTO telegram_group_request
        (id,update_id,account_id,connection_id,connection_generation,chat_id,topic_id,bot_identity,bot_fingerprint,
         state,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,'observed',?,?)''',
        (secrets.token_hex(24),clean['update_id'],owner['account_id'],owner['id'],owner['generation'],
         clean['chat_id'],clean['topic_id'] or 0,bot[0],bot[2],links.stamp(now),links.stamp(now+timedelta(minutes=10))))


def pause(conn, chat, topic=None, *, reason):
    clause='chat_id=?'+(' AND topic_id=?' if topic is not None else '')
    args=(chat,topic) if topic is not None else (chat,)
    conn.execute("UPDATE telegram_group SET state='paused',generation=lower(hex(randomblob(16))),reason=?,updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE "+clause+" AND state<>'revoked'",(reason,*args))
    conn.execute("UPDATE telegram_group_request SET state='cancelled' WHERE "+clause+" AND state='observed'",args)


def handle_event(conn, clean, bot):
    kind=clean['group_event'];chat=clean['chat_id']
    if kind=='migration':
        pause(conn,chat,reason='migration')
        pause(conn,clean['migration_target'],reason='migration')
    elif kind=='topic_changed':
        pause(conn,chat,clean['topic_id'],reason='topic_changed')
    elif kind=='my_chat_member':
        if clean['member_id']==bot[0]:
            pause(conn,chat,reason='bot_membership_changed')
    elif clean['member_status'] not in ('creator','administrator'):
        if clean['member_id']==bot[0]:
            pause(conn,chat,reason='bot_removed')
        else:
            for topic, in conn.execute('''SELECT g.topic_id FROM telegram_group g JOIN telegram_connection c ON c.id=g.owner_connection_id
                WHERE g.chat_id=? AND c.telegram_user_id=? AND g.state<>'revoked' ''',(chat,clean['member_id'])).fetchall():
                pause(conn,chat,topic,reason='owner_membership_changed')


def proof(bot, chat, sender, *, admin):
    status=transport.member_status(bot[1],chat,sender)
    return status in (('creator','administrator') if admin else ('creator','administrator','member'))


def register(conn, payload, request_id, purpose, consent, now):
    if (not switches.enabled('groups') or not switches.enabled('link') or not links.available()
            or not isinstance(purpose,str) or not 1<=len(purpose.strip())<=200
            or any(ord(c)<32 for c in purpose) or consent!='yes'):
        raise ValueError('Confirm the audience policy, enter a purpose and enable the group pilot first.')
    # Read a snapshot, verify outside the writer lock, then recheck all authority at commit.
    started=time.monotonic()
    user=links.current(conn,payload);owner=linked(conn,user['id'],admin=True)
    found=rows(conn,'SELECT * FROM telegram_group_request WHERE id=? AND account_id=?',(request_id,user['id']))
    bot=transport.config()
    if not found or not bot:
        raise ValueError('That group request is unavailable. Send /register again in the exact group or topic.')
    request=found[0]
    def valid():
        return (request['state']=='observed' and request['expires_at']>links.stamp(now)
                and request['connection_id']==owner['id'] and request['connection_generation']==owner['generation']
                and request['bot_identity']==bot[0] and request['bot_fingerprint']==bot[2])
    if not valid():
        raise ValueError('That request expired or changed. Send /register again.')
    if not (proof(bot,request['chat_id'],owner['telegram_user_id'],admin=True) and proof(bot,request['chat_id'],bot[0],admin=True)):
        raise ValueError('Telegram administrator status could not be verified for you and the bot. No group was enabled.')
    now=now+timedelta(seconds=time.monotonic()-started)
    with transaction(conn):
        user=links.current(conn,payload);fresh=linked(conn,user['id'],admin=True)
        if (fresh['id']!=owner['id'] or fresh['generation']!=owner['generation'] or bot!=transport.config()
                or not switches.enabled('groups') or not links.available()):
            raise ValueError('Your connection changed during verification. Start again.')
        request=rows(conn,'SELECT * FROM telegram_group_request WHERE id=?',(request_id,))[0]
        if not valid():
            raise ValueError('That request expired or changed. Start again.')
        existing=rows(conn,'SELECT * FROM telegram_group WHERE chat_id=? AND topic_id=?',(request['chat_id'],request['topic_id']))
        if existing and existing[0]['owner_account_id']!=user['id'] and existing[0]['state']!='revoked':
            raise ValueError('Revoke the existing registration explicitly before changing its owner.')
        conn.execute('''INSERT INTO telegram_group
            (chat_id,topic_id,owner_account_id,owner_connection_id,owner_generation,bot_identity,bot_fingerprint,
             purpose,policy_version,state,created_at,updated_at,consented_at)
            VALUES (?,?,?,?,?,?,?,?,?,'active',?,?,?)
            ON CONFLICT(chat_id,topic_id) DO UPDATE SET owner_account_id=excluded.owner_account_id,
            owner_connection_id=excluded.owner_connection_id,owner_generation=excluded.owner_generation,
            bot_identity=excluded.bot_identity,bot_fingerprint=excluded.bot_fingerprint,purpose=excluded.purpose,
            policy_version=excluded.policy_version,state='active',generation=lower(hex(randomblob(16))),reason=NULL,
            updated_at=excluded.updated_at,consented_at=excluded.consented_at''',
            (request['chat_id'],request['topic_id'],user['id'],owner['id'],owner['generation'],bot[0],bot[2],
             purpose.strip(),POLICY,links.stamp(now),links.stamp(now),links.stamp(now)))
        conn.execute("UPDATE telegram_group_request SET state='consumed' WHERE id=?",(request_id,))
        registered=rows(conn,'SELECT * FROM telegram_group WHERE chat_id=? AND topic_id=?',(request['chat_id'],request['topic_id']))[0]
        st.audit(conn,user['username'],'telegram_group_register',target_type='telegram_group',target_id=registered['id'],
                 summary='Consented to exact Telegram group/topic shared-audience policy.',
                 after=json.dumps({'purpose':registered['purpose'],'owner_account_id':user['id'],
                     'policy_version':POLICY,'generation':registered['generation']}),commit=False)


def route(conn, chat, topic, bot):
    if not (switches.enabled('groups') and switches.enabled('link')):
        return None
    found=rows(conn,'SELECT * FROM telegram_group WHERE chat_id=? AND topic_id=? AND state=\'active\'',(chat,topic or 0))
    if not found:
        return None
    group=found[0]
    try:
        owner=linked(conn,group['owner_account_id'],admin=True)
    except ValueError:
        return None
    if (owner['id']!=group['owner_connection_id'] or owner['generation']!=group['owner_generation']
            or group['bot_identity']!=bot[0] or group['bot_fingerprint']!=bot[2] or group['policy_version']!=POLICY):
        return None
    return group


def authorize_delivery(conn, delivery, bot):
    """Local routing and separate current delegated read consent."""
    group=route(conn,delivery['chat_id'],delivery['topic_id'],bot)
    if not group or delivery['registration_id']!=group['id'] or delivery['registration_generation']!=group['generation']:
        return None
    try:
        projection=json.loads(delivery['projection_json'])
    except (ValueError,TypeError):
        return None
    business=shared.descriptor(projection,bot)
    if not business and projection!={'kind':'group_status','bot':bot[0],'fingerprint':bot[2]}:
        return None
    actor=rows(conn,'''SELECT c.*,u.username,u.role FROM telegram_connection c JOIN admin_user u ON u.id=c.account_id
        WHERE c.id=? AND c.generation=? AND c.state='active' AND u.active=1 AND u.must_change=0
        AND u.role IN ('viewer','encoder','section_manager','admin')''',(delivery['connection_id'],delivery['generation']))
    if business and (not actor or not links.authorized(conn,actor[0]['account_id'],shared.action(projection))
            or not links.origin() or len(links.origin())>200):
        return None
    return (group,actor[0]) if actor and actor[0]['bot_identity']==bot[0] and actor[0]['bot_fingerprint']==bot[2] else None


def verify_delivery(conn, delivery, bot):
    authorized=authorize_delivery(conn,delivery,bot)
    if not authorized:
        return False
    group,actor=authorized
    try:
        owner=linked(conn,group['owner_account_id'],admin=True)
    except ValueError:
        return False
    if not (proof(bot,group['chat_id'],owner['telegram_user_id'],admin=True) and proof(bot,group['chat_id'],bot[0],admin=True)):
        with transaction(conn):
            pause(conn,group['chat_id'],group['topic_id'],reason='provider_verification_failed')
        return False
    if actor['id']!=owner['id'] and not proof(bot,group['chat_id'],actor['telegram_user_id'],admin=False):
        return False
    return authorize_delivery(conn,delivery,bot) is not None


def manage(conn,payload,group_id,generation,action):
    with transaction(conn):
        user=links.current(conn,payload)
        found=rows(conn,'SELECT * FROM telegram_group WHERE id=?',(group_id,))
        if (not found or (user['role']!='admin' and found[0]['owner_account_id']!=user['id'])
                or found[0]['generation']!=generation or action not in ('pause','revoke')):
            raise ValueError('Registration unavailable or changed. Reload and try again.')
        conn.execute("UPDATE telegram_group SET state=?,generation=lower(hex(randomblob(16))),reason='operator',updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
                     ('paused' if action=='pause' else 'revoked',group_id))
        st.audit(conn,user['username'],'telegram_group_'+action,target_type='telegram_group',target_id=group_id,summary='Paused or revoked a Telegram group/topic registration.',commit=False)
