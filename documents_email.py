"""Gmail intake foundation. No mailbox reads, Drive writes, or sends here."""
from datetime import datetime
import hashlib
import hmac
import json
import os
import re
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import documents as d
import documents_permissions as permissions
from documents_operations import validate_drive_url
from documents_storage import transaction, event
import storage as st
import tzutil

MAX_BODY = 64 * 1024
PATH = '/integrations/gmail/documents'


def authenticate(body, timestamp, signature):
    secret = os.environ.get('CSS_GMAIL_INTAKE_SECRET', '')
    if (len(secret) < 32 or not re.fullmatch(r'[0-9]{10}', timestamp)
            or not re.fullmatch(r'[a-f0-9]{64}', signature)):
        return False
    if abs(time.time() - int(timestamp)) > 300:
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def normalize(payload):
    if not isinstance(payload, dict) or set(payload) not in ({'mailbox','message_id','subject','sender','received_at','attachments'}, {'mailbox','message_id','subject','sender','received_at','attachments','body_text'}):
        raise ValueError('Invalid intake fields.')
    for field, limit in [('mailbox',254),('message_id',128),('subject',500),('sender',500),('received_at',40)]:
        value = payload[field]
        if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 for c in value):
            raise ValueError('Invalid ' + field + '.')
    payload = dict(payload)
    payload['mailbox'] = payload['mailbox'].strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', payload['mailbox']):
        raise ValueError('Invalid mailbox.')
    if not re.fullmatch(r'[a-fA-F0-9]+',payload['message_id']):
        raise ValueError('Use the Gmail API message ID.')
    payload['message_id'] = payload['message_id'].lower()
    received = datetime.fromisoformat(payload['received_at'])
    if received.tzinfo is None:
        raise ValueError('Received date requires a timezone.')
    attachments = payload['attachments']
    if 'body_text' in payload:
        body=payload['body_text']
        if not isinstance(body,str) or not body.strip() or len(body)>16000 or any(ord(c)<32 and c not in '\r\n\t' for c in body):
            raise ValueError('Invalid email body.')
        if attachments:
            raise ValueError('Body capture is for emails without attachments.')
    if not isinstance(attachments,list) or not 0 <= len(attachments) <= 20 or (not attachments and not payload.get('body_text')):
        raise ValueError('Supply between 1 and 20 attachments.')
    clean, ids, files = [], set(), set()
    for item in attachments:
        if not isinstance(item,dict) or set(item) != {'attachment_id','drive_url'}:
            raise ValueError('Invalid attachment fields.')
        aid = item['attachment_id']
        if not isinstance(aid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,1024}',aid) or aid in ids:
            raise ValueError('Invalid or repeated attachment ID.')
        if not isinstance(item['drive_url'],str) or len(item['drive_url'])>2048:
            raise ValueError('Invalid Drive URL.')
        url, fid = validate_drive_url(item['drive_url'])
        if fid in files:
            raise ValueError('Repeated Drive file.')
        ids.add(aid); files.add(fid)
        clean.append({'attachment_id':aid,'drive_url':url,'file_id':fid})
    payload['attachments'] = sorted(clean,key=lambda a:a['attachment_id'])
    return payload


def ingest(conn, payload):
    payload = normalize(payload)
    digest = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with transaction(conn):
        d.writable(conn)
        if st.get_setting(conn,'documents.gmail_intake_enabled','0') != '1':
            raise permissions.Denied('Gmail intake is disabled.')
        mailbox = st.get_setting(conn,'documents.gmail_mailbox','').strip().lower()
        if not mailbox or mailbox != payload['mailbox']:
            raise permissions.Denied('Mailbox is not configured for intake.')
        actor_id = st.get_setting(conn,'documents.gmail_actor_id','')
        if not actor_id.isdigit():
            raise permissions.Denied('Intake account is not configured.')
        actor = permissions.actor(conn,{'id':int(actor_id)})
        if not permissions.has_role(conn,actor,'records'):
            raise permissions.Denied('Intake account requires a bureau-wide records grant.')
        # Staged messages retain their acknowledgement even after registration.
        staged = conn.execute('SELECT primary_intake_id,payload_hash FROM document_intake_email WHERE mailbox=? AND message_id=?',
                              (mailbox,payload['message_id'])).fetchone()
        if staged:
            if staged[1] != digest:
                raise d.Conflict('Message was already queued with different content.')
            return {'intake_id':staged[0],'state':'queued','duplicate':True}
        prior = conn.execute('SELECT document_id,payload_hash FROM document_email_import WHERE mailbox=? AND message_id=?',
                             (mailbox,payload['message_id'])).fetchone()
        if prior:
            if prior[1] != digest:
                raise d.Conflict('Message was already imported with different content.')
            return {'document_id':prior[0],'duplicate':True}
        if st.get_setting(conn,'documents.gmail_review_queue_enabled','0') == '1':
            from documents_intake import stage_email
            return stage_email(conn,actor,payload,digest)
        if not payload['attachments']:
            raise ValueError('Enable the email review queue for body-only correspondence.')
        doc = d.register_in_transaction(conn,actor,{
            'direction':'IN','subject':payload['subject'],'type':'Unclassified',
            'sender':payload['sender'],'received_at':payload['received_at'],
            'channel':'gmail','evidence':'Gmail message ' + payload['message_id'],
            'drive_url':payload['attachments'][0]['drive_url'],
        },suppress_assignments=True,defer_rules=True)
        for item in payload['attachments'][1:]:
            conn.execute('INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,actor_id,created_at) VALUES (?,?,?,?,?,?,?)',
                         (doc['id'],item['drive_url'],item['file_id'],'','reference',actor['id'],tzutil.now_iso()))
        conn.execute('INSERT INTO document_email_import(mailbox,message_id,payload_hash,document_id,received_at,attachments_json,created_at) VALUES (?,?,?,?,?,?,?)',
                     (mailbox,payload['message_id'],digest,doc['id'],payload['received_at'],json.dumps(payload['attachments']),tzutil.now_iso()))
        event(conn,doc['id'],actor,'gmail_imported',{'message_id':payload['message_id'],'attachment_count':len(payload['attachments'])})
        return {'document_id':doc['id'],'duplicate':False}


def make_router(get_conn):
    router = APIRouter()

    @router.post(PATH)
    async def intake(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>MAX_BODY:
                return JSONResponse({'error':'Request too large.'},status_code=413)
        if not authenticate(bytes(body),request.headers.get('x-css-timestamp',''),request.headers.get('x-css-signature','')):
            return JSONResponse({'error':'Invalid intake authentication.'},status_code=401)
        conn = get_conn()
        try:
            result = ingest(conn,json.loads(body))
            return JSONResponse(result,status_code=200 if result['duplicate'] else 201)
        except permissions.Denied as exc:
            return JSONResponse({'error':str(exc)},status_code=403)
        except d.Conflict as exc:
            return JSONResponse({'error':str(exc)},status_code=409)
        except (ValueError,TypeError,OverflowError):
            return JSONResponse({'error':'Invalid intake payload or Documents disabled.'},status_code=400)
        finally:
            conn.close()

    return router
