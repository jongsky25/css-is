"""Actor-bound preview and atomic receipt contract.

Trusted adapters implement
prepare/revalidate/apply/check_receipt, with domain authorization on every call.
apply runs under BEGIN IMMEDIATE and MUST NOT commit or perform network I/O.
"""
from datetime import timedelta
import base64
import hmac
import auth
import hashlib
import json
import re
import secrets
import time
from uuid import uuid4

from documents_storage import rows,transaction
import telegram_groups as groups
import telegram_links as links
import telegram_storage as switches
import telegram_transport as transport

ADAPTERS = {}
ACTIONS = {'calendar.create':'calendar_create','rooms.request':'rooms_request'}
TTL = 300
CONTEXT = {'connection_id','generation','sender_id','chat_id','topic_id','registration_id','registration_generation'}


class Unavailable(ValueError):
    pass


def packed(value):
    try:
        body=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        if len(body.encode())>16384:
            raise ValueError()
        return body
    except (ValueError,TypeError,RecursionError):
        raise Unavailable('Action fields are invalid or too large.') from None


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def binding(context):
    if not isinstance(context,dict) or set(context)!=CONTEXT:
        raise Unavailable('Action context unavailable.')
    if (any(type(context[k]) is not int or context[k]<=0 for k in ('connection_id','sender_id'))
            or type(context['chat_id']) is not int or not -(2**63)<context['chat_id']<2**63 or context['chat_id']==0
            or not isinstance(context['generation'],str) or not re.fullmatch('[a-f0-9]{32}',context['generation'])):
        raise Unavailable('Action context unavailable.')
    if context['chat_id']>0:
        if context['chat_id']!=context['sender_id'] or any(context[k] is not None for k in ('topic_id','registration_id','registration_generation')):
            raise Unavailable('Action context unavailable.')
    elif (type(context['registration_id']) is not int or context['registration_id']<=0
          or not isinstance(context['registration_generation'],str)
          or not re.fullmatch('[a-f0-9]{32}',context['registration_generation'])
          or (context['topic_id'] is not None and (type(context['topic_id']) is not int or context['topic_id']<=0))):
        raise Unavailable('Action context unavailable.')
    return context


def authority(conn,context,action):
    binding(context)
    adapter=ADAPTERS.get(action);bot=transport.config()
    if (adapter is None or action not in ACTIONS or not bot or not switches.enabled('inbound')
            or not switches.enabled('link') or not switches.enabled(ACTIONS[action])
            or not links.available()):
        raise Unavailable('This action is unavailable.')
    found=rows(conn,'''SELECT c.account_id AS id,u.username,u.role FROM telegram_connection c
        JOIN admin_user u ON u.id=c.account_id JOIN telegram_grant g ON g.connection_id=c.id AND g.account_id=c.account_id
        WHERE c.id=? AND c.generation=? AND c.telegram_user_id=? AND c.private_chat_id=? AND c.state='active'
        AND c.bot_identity=? AND c.bot_fingerprint=? AND u.active=1 AND u.must_change=0
        AND u.role IN ('viewer','encoder','section_manager','admin')
        AND g.generation=c.generation AND g.action=? AND g.revoked_at IS NULL AND g.bot_identity=? AND g.bot_fingerprint=?''',
        (context['connection_id'],context['generation'],context['sender_id'],context['sender_id'],bot[0],bot[2],action,bot[0],bot[2]))
    if not found:
        raise Unavailable('This action is unavailable.')
    if context['chat_id']<0:
        group=groups.route(conn,context['chat_id'],context['topic_id'],bot)
        if not group or group['id']!=context['registration_id'] or group['generation']!=context['registration_generation']:
            raise Unavailable('Group context unavailable.')
    if not links.authorized(conn,found[0]['id'],'calendar.read' if action=='calendar.create' else 'rooms.read'):
        raise Unavailable('Current read consent is required for this action.')
    if action=='rooms.request' and not links.authorized(conn,found[0]['id'],'calendar.read'):
        raise Unavailable('Calendar read consent is required for a linked room request.')
    return found[0],adapter,bot


def fingerprint(action,fields,expected,summary):
    return digest(packed([action,fields,expected,summary]))


def issue(conn,context,action,client_key,fields,now):
    if not isinstance(client_key,str) or not re.fullmatch('[A-Za-z0-9_-]{16,80}',client_key):
        raise Unavailable('Use a unique action key.')
    if not isinstance(fields,dict):
        raise Unavailable('Action fields must be structured.')
    packed(fields)
    with transaction(conn):
        user,adapter,bot=authority(conn,context,action)
        # Adapter supplies normalized fields, exact user-facing preview and expected revisions.
        clean,summary,expected=adapter.prepare(conn,user,fields)
        if not all(isinstance(v,dict) for v in (clean,summary,expected)):
            raise Unavailable('Action preview unavailable.')
        encoded=[packed(v) for v in (clean,summary,expected)]
        hash_=fingerprint(action,clean,expected,summary)
        old=rows(conn,'SELECT * FROM telegram_operation WHERE actor_id=? AND client_key=?',(user['id'],client_key))
        if old:
            if old[0]['input_hash']!=hash_ or old[0]['connection_id']!=context['connection_id'] or old[0]['generation']!=context['generation'] or old[0]['context_hash']!=digest(packed(context)):
                raise Unavailable('This action key was already used. Start a new preview.')
            # Never mint a second token for the same operation. Recover by operation ID.
            result={'operation_id':old[0]['operation_id'],'token':None,'preview':None}
            if old[0]['state']!='pending':
                result['receipt']=receipt(conn,user,adapter,old[0])
            return result
        operation_id=uuid4().hex;nonce=secrets.token_hex(32)
        token=derive_token(operation_id,nonce)
        conn.execute('''INSERT INTO telegram_operation
            (operation_id,actor_id,connection_id,generation,action,client_key,input_hash,context_hash,state,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,'pending',?,?)''',
            (operation_id,user['id'],context['connection_id'],context['generation'],action,client_key,hash_,digest(packed(context)),links.stamp(now),links.stamp(now)))
        conn.execute('''INSERT INTO telegram_preview
            (token_hash,operation_id,actor_id,connection_id,generation,bot_identity,bot_fingerprint,chat_id,topic_id,
             registration_id,registration_generation,action,input_hash,fields_json,summary_json,expected_json,state,created_at,expires_at,token_nonce)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?,?)''',
            (digest(token),operation_id,user['id'],context['connection_id'],context['generation'],bot[0],bot[2],context['chat_id'],context['topic_id'],
             context['registration_id'],context['registration_generation'],action,hash_,*encoded,links.stamp(now),links.stamp(now+timedelta(seconds=TTL)),nonce))
        if hasattr(adapter,'queue_preview'):
            adapter.queue_preview(conn,user,operation_id,context,now)
        return {'operation_id':operation_id,'token':token,'preview':summary}


def receipt(conn,user,adapter,operation):
    if operation['result_code']=='retained_key':
        raise Unavailable('Receipt details expired; this operation key cannot be reused.')
    adapter.check_receipt(conn,user,operation)
    return {k:operation[k] for k in ('operation_id','action','state','result_entry_id','result_room_id','result_code')}


def recover(conn,context,action,operation_id):
    with transaction(conn):
        user,adapter,_=authority(conn,context,action)
        found=rows(conn,'SELECT * FROM telegram_operation WHERE actor_id=? AND operation_id=? AND action=? AND connection_id=? AND generation=? AND context_hash=?',
                   (user['id'],operation_id,action,context['connection_id'],context['generation'],digest(packed(context))))
        if not found:
            raise Unavailable('Receipt unavailable.')
        return receipt(conn,user,adapter,found[0])


def derive_token(operation_id,nonce):
    raw=hmac.new(auth._secret(),('telegram-action:'+operation_id+':'+nonce).encode(),hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def confirm(conn,context,token,now):
    if not isinstance(token,str) or not re.fullmatch('[A-Za-z0-9_-]{43}',token):
        raise Unavailable('Confirmation unavailable.')
    return confirm_digest(conn,context,digest(token),now)


def confirm_digest(conn,context,token_hash,now):
    started=time.monotonic()
    clock=lambda:now+timedelta(seconds=time.monotonic()-started)
    binding(context)
    if not isinstance(token_hash,str) or not re.fullmatch('[a-f0-9]{64}',token_hash):
        raise Unavailable('Confirmation unavailable.')
    # Fresh membership proof outside the writer lock, followed by local generation rechecks.
    if context['chat_id']<0:
        pre=rows(conn,'SELECT action FROM telegram_preview WHERE token_hash=?',(token_hash,))
        if not pre:
            raise Unavailable('Confirmation unavailable.')
        _,_,bot=authority(conn,context,pre[0]['action'])
        check={**context,'projection_json':packed({'kind':'group_status','bot':bot[0],'fingerprint':bot[2]})}
        if not groups.verify_delivery(conn,check,bot):
            raise Unavailable('Group membership could not be verified.')
    with transaction(conn):
        found=rows(conn,'SELECT * FROM telegram_preview WHERE token_hash=?',(token_hash,))
        if not found:
            raise Unavailable('Confirmation unavailable.')
        preview=found[0];user,adapter,bot=authority(conn,context,preview['action'])
        if (preview['actor_id']!=user['id'] or preview['bot_identity']!=bot[0] or preview['bot_fingerprint']!=bot[2]
                or any(preview[k]!=context[k] for k in ('connection_id','generation','chat_id','topic_id','registration_id','registration_generation'))):
            raise Unavailable('Confirmation unavailable.')
        operation=rows(conn,'SELECT * FROM telegram_operation WHERE operation_id=?',(preview['operation_id'],))[0]
        if preview['state']=='consumed' and operation['state'] in ('committed','partial','failed'):
            return receipt(conn,user,adapter,operation)
        if preview['state']!='pending' or operation['state']!='pending' or preview['expires_at']<=links.stamp(clock()):
            raise Unavailable('Confirmation expired or changed. Start a new preview.')
        try:
            clean=json.loads(preview['fields_json']);expected=json.loads(preview['expected_json']);summary=json.loads(preview['summary_json'])
        except (ValueError,TypeError):
            raise Unavailable('Confirmation changed. Start a new preview.') from None
        if fingerprint(preview['action'],clean,expected,summary)!=preview['input_hash'] or operation['input_hash']!=preview['input_hash']:
            raise Unavailable('Confirmation changed. Start a new preview.')
        adapter.revalidate(conn,user,clean,expected)
        result=adapter.apply(conn,user,clean,operation['operation_id'])
        if not conn.in_transaction:
            raise RuntimeError('Action adapter committed outside the receipt transaction.')
        if (not isinstance(result,dict) or set(result)-{'state','result_entry_id','result_room_id','result_code'}
                or result.get('state') not in ('committed','partial','failed')
                or not isinstance(result.get('result_code'),str) or not re.fullmatch('[a-z_]{1,60}',result['result_code'])
                or any(result.get(k) is not None and (type(result[k]) is not int or result[k]<=0) for k in ('result_entry_id','result_room_id'))):
            raise Unavailable('Action receipt unavailable.')
        authority(conn,context,preview['action'])
        if preview['expires_at']<=links.stamp(clock()):
            raise Unavailable('Confirmation expired during the action.')
        if not conn.execute("SELECT 1 FROM telegram_preview WHERE token_hash=? AND state='pending'",(token_hash,)).fetchone():
            raise Unavailable('Confirmation was revoked during the action.')
        conn.execute('''UPDATE telegram_operation SET state=?,result_entry_id=?,result_room_id=?,result_code=?,updated_at=?
            WHERE operation_id=? AND state='pending' ''',
            (result['state'],result.get('result_entry_id'),result.get('result_room_id'),result['result_code'],links.stamp(now),operation['operation_id']))
        conn.execute("UPDATE telegram_preview SET state='consumed',fields_json=NULL,summary_json=NULL,expected_json=NULL,consumed_at=? WHERE token_hash=?",(links.stamp(now),token_hash))
        current=rows(conn,'SELECT * FROM telegram_operation WHERE operation_id=?',(operation['operation_id'],))[0]
        if hasattr(adapter,'queue_receipt'):
            adapter.queue_receipt(conn,user,current,context,clock())
        return receipt(conn,user,adapter,current)


def cleanup_in_transaction(conn,now):
    conn.execute('''UPDATE telegram_preview SET state='cancelled',fields_json=NULL,summary_json=NULL,expected_json=NULL
        WHERE token_hash IN (SELECT token_hash FROM telegram_preview WHERE state='pending' AND expires_at<=? LIMIT 20)''',(links.stamp(now),))
    conn.execute("DELETE FROM telegram_preview WHERE token_hash IN (SELECT token_hash FROM telegram_preview WHERE state<>'pending' AND expires_at<? LIMIT 20)",(links.stamp(now-timedelta(days=1)),))
    conn.execute('''UPDATE telegram_operation SET target_id=NULL,expected_revision=NULL,context_json=NULL,result_entry_id=NULL,result_room_id=NULL,result_code='retained_key'
        WHERE operation_id IN (SELECT operation_id FROM telegram_operation WHERE state<>'pending' AND updated_at<?
        AND (result_code IS NULL OR result_code<>'retained_key') LIMIT 20)''',(links.stamp(now-timedelta(days=180)),))
