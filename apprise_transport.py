"""Fixed-provider transport. Credentials are hosting secrets, never preferences/logs."""
import hashlib
import json
import logging
import os
import re
from urllib.parse import urlsplit

CHANNEL = 'telegram'
TOKEN = re.compile(r'[1-9][0-9]{4,19}:[A-Za-z0-9_-]{20,128}\Z')
CHAT = re.compile(r'[1-9][0-9]{0,18}\Z')
BINDING = re.compile(r'[0-9a-f]{32}\Z')


class _HideTelegram(logging.Filter):
    def filter(self,record):
        try:
            message=record.getMessage()
            return 'api.telegram.org' not in message and not re.search(r'/bot[0-9]+(?::|%3[aA])',message)
        except Exception:
            return False


# urllib3 debug request paths otherwise contain Telegram's bot token.
logging.getLogger('urllib3.connectionpool').addFilter(_HideTelegram())
for _logger_name in ('httpx', 'httpcore.connection', 'httpcore.http11', 'httpcore.http2',
                     'httpcore.proxy', 'httpcore.socks'):
    logging.getLogger(_logger_name).addFilter(_HideTelegram())


def enabled():
    return os.environ.get('CSS_APPRISE_TELEGRAM_ENABLED','0')=='1'


def target_check(binding):
    """Return only this account's validated target or a credential-free reason."""
    if not isinstance(binding,str) or not BINDING.fullmatch(binding):
        return None,'Save a Telegram preference to generate your personal setup code.'
    raw=os.environ.get('CSS_APPRISE_TELEGRAM_TARGETS','')
    if not raw:
        return None,'The hosting secret CSS_APPRISE_TELEGRAM_TARGETS is missing.'
    if len(raw)>65536:
        return None,'The hosting secret CSS_APPRISE_TELEGRAM_TARGETS exceeds the size limit.'
    try:
        values=json.loads(raw)
        if not isinstance(values,dict):
            return None,'CSS_APPRISE_TELEGRAM_TARGETS must be a JSON object keyed by personal setup code.'
        if binding not in values:
            return None,'Your current setup code has no entry in CSS_APPRISE_TELEGRAM_TARGETS. Ask the hosting administrator to match the code under Connect my private Telegram chat.'
        value=values[binding]
        if not isinstance(value,dict) or set(value)!={'bot_token','chat_id'}:
            return None,'Your Telegram configuration must contain exactly bot_token and chat_id string fields.'
        token=value['bot_token'];chat=value['chat_id']
        if not isinstance(token,str) or not TOKEN.fullmatch(token):
            return None,'Your configured bot_token has an invalid format. The hosting administrator must check the complete BotFather token.'
        if not isinstance(chat,str) or not CHAT.fullmatch(chat):
            return None,'Your configured chat_id must be a positive private chat ID enclosed in JSON quotation marks.'
        return {'bot_token':token,'chat_id':chat},''
    except (ValueError,TypeError,RecursionError):
        return None,'The hosting secret CSS_APPRISE_TELEGRAM_TARGETS is not valid JSON.'


def target(binding):
    return target_check(binding)[0]


def fingerprint(value,binding=''):
    return hashlib.sha256(json.dumps({'binding':binding,'target':value},sort_keys=True,separators=(',',':')).encode()).hexdigest()


def link(base):
    if not isinstance(base,str) or len(base)>512 or any(ord(c)<33 or c in '<>"\\' for c in base):return None
    try:
        parsed=urlsplit(base)
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):return None
        # Validate port syntax as well; no credentials/query fragments enter the message.
        parsed.port
        return base.rstrip('/')+'/work/updates'
    except ValueError:
        return None


def send(value,url):
    """One private chat, no attachments/previews/autodetection or service retries."""
    from apprise import AppriseAsset,NotifyFormat,PersistentStoreMode
    from apprise.plugins.telegram import NotifyTelegram
    quiet=logging.getLogger('office_connect.telegram.silent');quiet.disabled=True;quiet.propagate=False
    class PrivateTelegram(NotifyTelegram):
        logger=quiet
    try:
        provider=PrivateTelegram(bot_token=value['bot_token'],targets=[value['chat_id']],
            detect_owner=False,include_image=False,preview=False,retry=0,cto=3,rto=7,
            secure=True,verify=True,redirect=False,
            asset=AppriseAsset(async_mode=False,storage_mode=PersistentStoreMode.MEMORY,default_service_retry=0))
        return provider.notify(title='Office Connect',
            body='You have unread discussion updates in Office Connect.\nSign in to review: '+url,
            body_format=NotifyFormat.TEXT) is True
    except Exception:
        # Provider exceptions can contain credentials. Only an uncertain state is persisted.
        return False
