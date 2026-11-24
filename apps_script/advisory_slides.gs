// Office Connect advisory Slides companion (docs/ADVISORY_SLIDES_SETUP.md).
// Add this file to the same Apps Script project as travel_docs.gs. travel_docs.gs's doPost hands every
// `advisory_*` action here after checking the signature, so it shares that project's secret and folders.
//
// Script Properties used: ROOT_FOLDER_ID and ALLOWED_DOMAIN (already set for travel), and
// TPL_advisory: the id of the advisory master presentation. Each slide of the master is one template
// variant (slide 1 = variant 1). makeAdvisoryTemplate() makes the master from the office template.
//
// Actions (all signed; all files live under ROOT/advisories/<folder_key>/):
//   advisory_info      -> which variants exist and which {{placeholders}} each one holds
//   advisory_create    -> copy the master, keep one variant, fill placeholders and the QR code, share it
//   advisory_snapshot  -> PDF + PNG + Drive version + open comments of a file, for review records
//   advisory_access    -> set exactly who may edit / comment / view the file (no notification emails)
//   advisory_version   -> the file's current Drive version (to spot edits after approval)
const ADVISORY_VERSION = 1;
const ADV_SLUG = /^[A-Za-z0-9_-]{1,40}$/;
const ADV_REQUEST = /^[A-Za-z0-9:_-]{1,80}$/;
const ADV_KEY = /^[a-z][a-z0-9_]{0,30}$/;
const ADV_MAX_FIELD = 2000;
const ADV_MAX_PEOPLE = 200;
const ADV_MAX_QR_BYTES = 512 * 1024;
const ADV_PLACEHOLDER = /\{\{([a-z][a-z0-9_]{0,30})\}\}/g;

function advisoryOperation_(req) {
  switch (String(req.action)) {
    case 'advisory_info': return advInfo_(req);
    case 'advisory_create': return advLocked_(function () { return advCreate_(req); });
    case 'advisory_snapshot': return advSnapshot_(req);
    case 'advisory_access': return advLocked_(function () { return advAccess_(req); });
    case 'advisory_version': return advVersion_(req);
    default: return { ok: false, error: 'unknown_action' };
  }
}

function advLocked_(fn) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) return { ok: false, error: 'busy' };
  try { return fn(); } finally { lock.releaseLock(); }
}

function advDomainOk_(email) {
  const domain = String(P.getProperty('ALLOWED_DOMAIN') || '').toLowerCase();
  const e = String(email || '').trim().toLowerCase();
  return !!domain && /^[^@\s]+@[^@\s]+$/.test(e) && e.endsWith('@' + domain);
}

function advPeople_(list) {
  if (!Array.isArray(list) || list.length > ADV_MAX_PEOPLE) return null;
  const out = [];
  for (let i = 0; i < list.length; i++) {
    const e = String(list[i] || '').trim().toLowerCase();
    if (!advDomainOk_(e)) return null;
    if (out.indexOf(e) < 0) out.push(e);
  }
  return out;
}

function advRoot_() { return childFolder_(DriveApp.getFolderById(P.getProperty('ROOT_FOLDER_ID')), 'advisories'); }

// A file the relay will touch must sit under ROOT/advisories/.
function advFile_(id) {
  if (!/^[-\w]{20,80}$/.test(String(id || ''))) return null;
  let file;
  try { file = DriveApp.getFileById(id); } catch (e) { return null; }
  return underRoot_(file, advRoot_().getId()) ? file : null;
}

function advDigest_(bytes) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes)
    .map(function (b) { return ('0' + (b & 255).toString(16)).slice(-2); }).join('');
}

function advPlaceholders_(slide) {
  const found = [];
  slide.getPageElements().forEach(function (el) {
    if (el.getPageElementType() !== SlidesApp.PageElementType.SHAPE) return;
    const text = el.asShape().getText().asString();
    let m; ADV_PLACEHOLDER.lastIndex = 0;
    while ((m = ADV_PLACEHOLDER.exec(text)) !== null) if (found.indexOf(m[1]) < 0) found.push(m[1]);
  });
  return found;
}

function advInfo_(req) {
  const tpl = P.getProperty('TPL_advisory');
  if (!tpl) return { ok: false, error: 'template_not_set' };
  const slides = SlidesApp.openById(tpl).getSlides();
  return {
    ok: true, version: ADVISORY_VERSION,
    variants: slides.map(function (s, i) {
      const v = { variant: i + 1, slide_id: s.getObjectId(), placeholders: advPlaceholders_(s) };
      if (req.thumbnails === true) {
        const png = advSlidePng_(tpl, s.getObjectId());
        if (png) v.png_b64 = Utilities.base64Encode(png);
      }
      return v;
    })
  };
}

function advCreate_(req) {
  if (!ADV_SLUG.test(String(req.folder_key))) return { ok: false, error: 'bad_folder' };
  if (!ADV_REQUEST.test(String(req.request_id))) return { ok: false, error: 'bad_request_id' };
  const variant = Number(req.variant);
  if (!Number.isInteger(variant) || variant < 1 || variant > 20) return { ok: false, error: 'bad_variant' };
  const fields = req.fields || {};
  const keys = Object.keys(fields);
  for (let i = 0; i < keys.length; i++) {
    if (!ADV_KEY.test(keys[i]) || keys[i] === 'qr' || String(fields[keys[i]]).length > ADV_MAX_FIELD) return { ok: false, error: 'bad_fields' };
  }
  const editors = advPeople_(req.editors || []);
  if (editors === null) return { ok: false, error: 'bad_people' };
  const tpl = P.getProperty('TPL_advisory');
  if (!tpl) return { ok: false, error: 'template_not_set' };

  const folder = childFolder_(advRoot_(), req.folder_key);
  const tag = 'request_id=' + req.request_id;
  const existing = folder.getFiles();
  while (existing.hasNext()) {
    const f = existing.next();
    if (f.getDescription() === tag) return advResult_(f, null);       // a retry: the copy already exists
  }
  const master = SlidesApp.openById(tpl);
  if (variant > master.getSlides().length) return { ok: false, error: 'bad_variant' };

  const copy = DriveApp.getFileById(tpl).makeCopy(String(req.title || 'Advisory').slice(0, 120), folder);
  copy.setDescription(tag);
  const deck = SlidesApp.openById(copy.getId());
  deck.getSlides().forEach(function (s, i) { if (i !== variant - 1) s.remove(); });
  keys.forEach(function (k) { deck.replaceAllText('{{' + k + '}}', String(fields[k])); });
  let qr = 'none';
  if (req.qr_png_b64) {
    const bytes = Utilities.base64Decode(String(req.qr_png_b64));
    if (!bytes.length || bytes.length > ADV_MAX_QR_BYTES) qr = 'bad_image';
    else qr = advPutQr_(deck, Utilities.newBlob(bytes, 'image/png', 'qr.png')) ? 'placed' : 'no_qr_box';
  }
  deck.saveAndClose();
  editors.forEach(function (e) { shareQuietly_(copy, e, 'writer'); });
  return advResult_(copy, qr);
}

// The QR code replaces every shape whose whole text is {{qr}}, keeping its size and place.
function advPutQr_(deck, blob) {
  let placed = false;
  deck.getSlides().forEach(function (slide) {
    slide.getPageElements().forEach(function (el) {
      if (el.getPageElementType() !== SlidesApp.PageElementType.SHAPE) return;
      const shape = el.asShape();
      if (shape.getText().asString().trim() !== '{{qr}}') return;
      shape.replaceWithImage(blob);
      placed = true;
    });
  });
  return placed;
}

function advMeta_(file) {
  const meta = Drive.Files.get(file.getId(), { fields: 'id,version,modifiedTime', supportsAllDrives: true });
  return { version: String(meta.version), modified_time: meta.modifiedTime };
}

function advVersion_(req) {
  const file = advFile_(req.file_id);
  if (!file) return { ok: false, error: 'not_allowed' };
  const meta = advMeta_(file);
  return { ok: true, id: file.getId(), version: meta.version, modified_time: meta.modified_time };
}

function advResult_(file, qr) {
  const deck = SlidesApp.openById(file.getId());
  const left = [];
  deck.getSlides().forEach(function (s) { advPlaceholders_(s).forEach(function (k) { if (left.indexOf(k) < 0) left.push(k); }); });
  const out = { ok: true, id: file.getId(), url: file.getUrl(), name: file.getName(), unfilled: left };
  const meta = advMeta_(file);
  out.version = meta.version; out.modified_time = meta.modified_time;
  if (qr) out.qr = qr;
  return out;
}

function advSnapshot_(req) {
  const file = advFile_(req.file_id);
  if (!file) return { ok: false, error: 'not_allowed' };
  const before = advMeta_(file);
  const pdf = file.getAs('application/pdf').getBytes();
  const deck = SlidesApp.openById(file.getId());
  const slide = deck.getSlides()[0];
  const png = advSlidePng_(file.getId(), slide.getObjectId());
  if (!png) return { ok: false, error: 'export_failed' };
  const after = advMeta_(file);
  // Someone edited while the copy was being taken: the PDF and image might not match. Ask the app to try again.
  if (before.version !== after.version) return { ok: false, error: 'changed_during_snapshot' };
  return {
    ok: true, id: file.getId(), version: after.version, modified_time: after.modified_time,
    slide_count: deck.getSlides().length,
    pdf_b64: Utilities.base64Encode(pdf), pdf_sha256: advDigest_(pdf),
    png_b64: Utilities.base64Encode(png), png_sha256: advDigest_(png),
    comments: advComments_(file.getId())
  };
}

// One slide as a PNG, through the presentation's export link with the script's own sign-in. null if it fails.
function advSlidePng_(presentationId, pageId) {
  const resp = UrlFetchApp.fetch('https://docs.google.com/presentation/d/' + presentationId + '/export/png?pageid=' +
    encodeURIComponent(pageId), { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() }, muteHttpExceptions: true });
  return resp.getResponseCode() === 200 ? resp.getBlob().getBytes() : null;
}

// Open (unresolved) Slides comments with their replies, so a review record shows what was raised.
function advComments_(id) {
  const out = [];
  let pageToken = null;
  do {
    const page = Drive.Comments.list(id, {
      fields: 'nextPageToken,comments(id,content,resolved,deleted,createdTime,author(displayName,emailAddress),' +
        'quotedFileContent(value),replies(content,deleted,createdTime,author(displayName,emailAddress)))',
      pageSize: 100, pageToken: pageToken || undefined, includeDeleted: false
    });
    (page.comments || []).forEach(function (c) {
      if (c.resolved || c.deleted) return;
      out.push({
        id: c.id, content: String(c.content || '').slice(0, 4000), created_time: c.createdTime,
        author: (c.author && c.author.displayName) || '', author_email: (c.author && c.author.emailAddress) || '',
        quoted: (c.quotedFileContent && String(c.quotedFileContent.value || '').slice(0, 500)) || '',
        replies: (c.replies || []).filter(function (r) { return !r.deleted; }).map(function (r) {
          return { content: String(r.content || '').slice(0, 4000), created_time: r.createdTime,
                   author: (r.author && r.author.displayName) || '' };
        })
      });
    });
    pageToken = page.nextPageToken;
  } while (pageToken && out.length < 500);
  return out;
}

// Make the file's people exactly: editors / commenters / readers. Anyone else with a personal permission
// (except the owner, the office mailbox) is removed. Nobody gets a "shared with you" email.
function advAccess_(req) {
  const file = advFile_(req.file_id);
  if (!file) return { ok: false, error: 'not_allowed' };
  const want = {};
  const lists = [['writer', req.editors], ['commenter', req.commenters], ['reader', req.readers]];
  for (let i = 0; i < lists.length; i++) {
    const people = advPeople_(lists[i][1] || []);
    if (people === null) return { ok: false, error: 'bad_people' };
    people.forEach(function (e) { if (!want[e]) want[e] = lists[i][0]; });   // the strongest listed role wins
  }
  const current = {};
  let pageToken = null;
  do {
    const page = Drive.Permissions.list(file.getId(), { fields: 'nextPageToken,permissions(id,type,role,emailAddress)',
                                                         supportsAllDrives: true, pageToken: pageToken || undefined });
    (page.permissions || []).forEach(function (p) {
      if (p.type === 'user' && p.role !== 'owner' && p.emailAddress) current[String(p.emailAddress).toLowerCase()] = p;
    });
    pageToken = page.nextPageToken;
  } while (pageToken);
  const changed = [];
  Object.keys(current).forEach(function (e) {
    if (want[e] === current[e].role) return;
    Drive.Permissions.remove(file.getId(), current[e].id, { supportsAllDrives: true });
    if (!want[e]) changed.push({ email: e, role: 'none' });
  });
  Object.keys(want).forEach(function (e) {
    if (current[e] && current[e].role === want[e]) return;
    shareQuietly_(file, e, want[e]);
    changed.push({ email: e, role: want[e] });
  });
  return { ok: true, id: file.getId(), changed: changed };
}

// ---- One-time setup, run by hand from the editor (not reachable from the web app) ----

// The office's advisory design (docs.google.com/presentation/d/<id>). Change if the office moves it.
const ADV_SOURCE_ID = '1T750K6cphrzOo6_-3GlP_9vdEt-fKXLWnZSjCGWbHY4';
// The sample number printed on the office template; it becomes {{number}}.
const ADV_SAMPLE_NUMBERS = ['2026-MMDD-001', '2026-1113-001'];

function makeAdvisoryTemplate() {
  if (P.getProperty('TPL_advisory')) {
    Logger.log('TPL_advisory is already set (%s). Delete the property first to make a new master.', P.getProperty('TPL_advisory'));
    return;
  }
  const root = DriveApp.getFolderById(P.getProperty('ROOT_FOLDER_ID'));
  const master = DriveApp.getFileById(ADV_SOURCE_ID).makeCopy('Advisory master (Office Connect)', childFolder_(root, '_templates'));
  const deck = SlidesApp.openById(master.getId());
  ADV_SAMPLE_NUMBERS.forEach(function (n) { deck.replaceAllText(n, '{{number}}'); });
  deck.saveAndClose();
  P.setProperty('TPL_advisory', master.getId());
  Logger.log('Master made: %s', master.getUrl());
  checkAdvisoryTemplate();
}

function checkAdvisoryTemplate() {
  const info = advInfo_({});
  if (!info.ok) { Logger.log('Not ready: %s', info.error); return; }
  const wanted = ADVISORY_PLACEHOLDERS_;
  info.variants.forEach(function (v) {
    const missing = wanted.filter(function (k) { return v.placeholders.indexOf(k) < 0; });
    Logger.log('Slide %s: has %s%s', String(v.variant), v.placeholders.join(', ') || '(none)',
               missing.length ? ' | missing: ' + missing.join(', ') : ' | complete');
  });
}

// The placeholders Office Connect fills. Keep in step with advisory_slides.py PLACEHOLDERS.
const ADVISORY_PLACEHOLDERS_ = ['number', 'title', 'dates', 'venue', 'message', 'attention', 'contact', 'link', 'qr'];
