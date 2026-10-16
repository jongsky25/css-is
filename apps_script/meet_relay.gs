// Office Connect Google Meet relay. Its OWN Apps Script project, deployed while signed in as the
// shared organizer mailbox (blhsd@doh.gov.ph): every Meet link it makes belongs to that account.
// Enable the Calendar API advanced service (Services, +, Google Calendar API, v3).
// Script Properties: SHARED_SECRET (long random string), optional CALENDAR_ID (default 'primary'),
// optional TIME_ZONE (default 'Asia/Manila').
// Deploy: Web app, Execute as Me, Who has access: Anyone. Every request is HMAC-signed, so the open
// endpoint trusts nothing unsigned. No attendees are added and no Google invitation is sent: the
// Space already notifies people by its own calendar emails.
const MR_VERSION = 1;

function mrProp_(k, d) { return PropertiesService.getScriptProperties().getProperty(k) || d; }
function mrReply_(v) {
  return ContentService.createTextOutput(JSON.stringify(v)).setMimeType(ContentService.MimeType.JSON);
}
function mrSigned_(env, secret) {
  if (!secret || !env || !env.ts || !env.payload || !env.sig || !Number.isFinite(Number(env.ts))
      || Math.abs(Date.now() - Number(env.ts)) > 5 * 60 * 1000) return false;
  const bytes = Utilities.computeHmacSha256Signature(env.ts + '.' + env.payload, secret);
  const hex = bytes.map(function (b) { return ('0' + (b & 255).toString(16)).slice(-2); }).join('');
  return hex === String(env.sig);
}
function mrErr_(code) { const e = new Error(code); e.mrCode = code; throw e; }

// The entry's uid is the request id: it is stored on the event, so a retry (or an edit) finds the
// event it already made instead of creating a second link.
function mrFind_(uid) {
  const r = Calendar.Events.list(mrProp_('CALENDAR_ID', 'primary'), {
    privateExtendedProperty: 'cssUid=' + uid, showDeleted: false, maxResults: 1 });
  return (r.items && r.items.length) ? r.items[0] : null;
}
function mrTimes_(req) {
  const tz = mrProp_('TIME_ZONE', 'Asia/Manila');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(req.start_date || '')) mrErr_('bad_date');
  const endDate = /^\d{4}-\d{2}-\d{2}$/.test(req.end_date || '') ? req.end_date : req.start_date;
  if (req.start_time && /^\d{2}:\d{2}$/.test(req.start_time)) {
    const endTime = /^\d{2}:\d{2}$/.test(req.end_time || '') ? req.end_time : req.start_time;
    return { start: { dateTime: req.start_date + 'T' + req.start_time + ':00', timeZone: tz },
             end: { dateTime: endDate + 'T' + endTime + ':00', timeZone: tz }, timed: true };
  }
  const d = new Date(endDate + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 1);   // all-day end is exclusive
  return { start: { date: req.start_date }, end: { date: d.toISOString().slice(0, 10) }, timed: false };
}
function mrBody_(req) {
  const t = mrTimes_(req);
  return { summary: String(req.title || 'Meeting').slice(0, 200),
           description: String(req.note || '').slice(0, 2000),
           start: t.start, end: t.end };
}
function mrOut_(ev) { return { ok: true, event_id: ev.id, meet_url: ev.hangoutLink || '', version: MR_VERSION }; }

function mrCreate_(req) {
  if (!req.request_id) mrErr_('missing_request_id');
  const have = mrFind_(req.request_id);
  if (have) return mrOut_(have);
  const body = mrBody_(req);
  body.extendedProperties = { private: { cssUid: String(req.request_id) } };
  body.conferenceData = { createRequest: { requestId: String(req.request_id),
    conferenceSolutionKey: { type: 'hangoutsMeet' } } };
  const ev = Calendar.Events.insert(body, mrProp_('CALENDAR_ID', 'primary'),
    { conferenceDataVersion: 1, sendUpdates: 'none' });
  if (!ev.hangoutLink) mrErr_('no_meet_link');
  return mrOut_(ev);
}
function mrUpdate_(req) {
  const have = mrFind_(req.request_id);
  if (!have) mrErr_('not_found');
  const ev = Calendar.Events.patch(mrBody_(req), mrProp_('CALENDAR_ID', 'primary'), have.id,
    { conferenceDataVersion: 1, sendUpdates: 'none' });
  return mrOut_(ev);
}
function mrDelete_(req) {
  const have = mrFind_(req.request_id);
  if (have) Calendar.Events.remove(mrProp_('CALENDAR_ID', 'primary'), have.id, { sendUpdates: 'none' });
  return { ok: true, deleted: !!have };
}

function doPost(e) {
  try {
    const env = JSON.parse(e.postData.contents);
    if (!mrSigned_(env, mrProp_('SHARED_SECRET', ''))) return mrReply_({ ok: false, error: 'unauthorized' });
    const req = JSON.parse(env.payload);
    if (req.action === 'ping') return mrReply_({ ok: true, version: MR_VERSION, account: Session.getEffectiveUser().getEmail() });
    if (req.action === 'create_meet') return mrReply_(mrCreate_(req));
    if (req.action === 'update_meet') return mrReply_(mrUpdate_(req));
    if (req.action === 'delete_meet') return mrReply_(mrDelete_(req));
    return mrReply_({ ok: false, error: 'bad_action' });
  } catch (err) { return mrReply_({ ok: false, error: err.mrCode || 'meet_operation_failed' }); }
}
