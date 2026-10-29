// Office Connect travel documents relay.
// Deploy: Web app, Execute as: Me, Who has access: Anyone. Every request is HMAC-signed, so the
// "Anyone" endpoint only does work for the Space. Setup: docs/TRAVEL_DOCS_RELAY_SETUP.md.
// A template may be a Google Doc or a Google Sheet; the script checks which.
// Script Properties: SHARED_SECRET, ROOT_FOLDER_ID, ALLOWED_DOMAIN (doh.gov.ph),
// TPL_appendix_a, TPL_appendix_b, TPL_mc114_justification, TPL_jo_cert, TPL_travel_report,
// TPL_cenrr, TPL_rer.
const P = PropertiesService.getScriptProperties();

function doPost(e) {
  try {
    const env = JSON.parse(e.postData.contents);               // {ts, payload, sig}
    if (!verify_(env)) return reply_({ ok: false, error: 'unauthorized' });
    const req = JSON.parse(env.payload);
    if (String(req.action || '').indexOf('document_') === 0 && typeof documentOperation_ === 'function') {
      return reply_(documentOperation_(req, ['inspect','preview','extract','text','sign','status','intake_list','intake_check','intake_file']));
    }
    switch (req.action) {
      case 'ping': return reply_({ ok: true, version: 2 });
      case 'check_link': return reply_(checkLink_(req));
      case 'generate_doc': return reply_(generateDoc_(req));
      case 'upload_file': return reply_(uploadFile_(req));
      case 'trash_file': return reply_(trashFile_(req));
      default: return reply_({ ok: false, error: 'unknown_action' });
    }
  } catch (err) { return reply_({ ok: false, error: String(err) }); }
}

function verify_(env) {
  if (!env || !env.ts || !env.payload || !env.sig) return false;
  if (Math.abs(Date.now() - Number(env.ts)) > 5 * 60 * 1000) return false;
  const raw = Utilities.computeHmacSha256Signature(env.ts + '.' + env.payload, P.getProperty('SHARED_SECRET'));
  const hex = raw.map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
  return hex.length === String(env.sig).length && hex === String(env.sig);
}

function reply_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
function esc_(s) { return String(s).replace(/\\/g, '\\\\').replace(/\$/g, '\\$'); }

function checkLink_(req) {
  const m = /[-\w]{25,}/.exec(String(req.url || '')); if (!m) return { ok: false, error: 'bad_link' };
  try { const f = DriveApp.getFileById(m[0]); return { ok: true, id: m[0], name: f.getName(), mime: f.getMimeType() }; }
  catch (err) { return { ok: false, error: 'not_accessible' }; }
}

function generateDoc_(req) {
  // Allow-list: the template must be one of the TPL_ properties, the folder name a plain slug.
  if (!/^[a-z0-9_]{1,40}$/.test(String(req.template_key))) return { ok: false, error: 'template_not_set' };
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(String(req.folder_key))) return { ok: false, error: 'bad_folder' };
  if (!/^[A-Za-z0-9:_-]{1,80}$/.test(String(req.request_id))) return { ok: false, error: 'bad_request_id' };
  const tpl = P.getProperty('TPL_' + req.template_key); if (!tpl) return { ok: false, error: 'template_not_set' };
  const root = DriveApp.getFolderById(P.getProperty('ROOT_FOLDER_ID'));
  const it = root.getFoldersByName(req.folder_key);
  const folder = it.hasNext() ? it.next() : root.createFolder(req.folder_key);
  const files = folder.getFiles();
  while (files.hasNext()) { const f = files.next(); if (f.getDescription() === 'request_id=' + req.request_id) return doc_(f); }
  const tplFile = DriveApp.getFileById(tpl);
  const isSheet = tplFile.getMimeType() === 'application/vnd.google-apps.spreadsheet';
  const copy = tplFile.makeCopy(String(req.title).slice(0, 120), folder);
  copy.setDescription('request_id=' + req.request_id);
  let extras = '';
  if (isSheet) {
    SpreadsheetApp.openById(copy.getId()).getSheets().forEach(function (sh) {
      applyRowsSheet_(sh, req.rows || {}); applyFieldsSheet_(sh, req.fields || {}); formatSheet_(sh);
    });
    SpreadsheetApp.flush();
  } else {
    const doc = DocumentApp.openById(copy.getId()), body = doc.getBody();
    applyRows_(body, req.rows || {});
    if (req.template_key === 'travel_report') dropEmptyReportSections_(body, req.blocks || {});
    if (req.extras && req.extras.addressees) applyAddressees_(body, req.extras.addressees);
    applyBlocks_(body, req.blocks || {}); applyFields_(body, req.fields || {});
    // Bind the office-format marker to this template ID, so restoring an old TPL_ also restores formatting.
    if (P.getProperty('TPLF_' + req.template_key) !== tpl) formatDoc_(body);
    if (req.template_key === 'travel_report') { reportLetterhead_(doc); formatReport_(body); }
    if (SIGNATORY_FIELDS_[req.template_key]) alignSignatory_(body, req.fields || {}, SIGNATORY_FIELDS_[req.template_key]);
    doc.saveAndClose();
    if (req.extras && req.extras.file_copy) extras = addFileCopy_(copy.getId(), req.extras);
  }
  (req.share_with || []).forEach(function (a) {
    if (String(a).toLowerCase().endsWith('@' + P.getProperty('ALLOWED_DOMAIN'))) shareQuietly_(copy, a, 'writer');
  });
  const out = doc_(copy);
  if (extras) out.extras = extras;                  // 'ok' or why the file-copy page was not added; the draft itself is fine
  return out;
}

// Gives a person access WITHOUT Google's "shared with you" email: the app already shows the link on the page, so a mail for
// every draft only clutters the inbox (spot feedback #146). Uses the Drive advanced service, which this project already has
// switched on for the template copy; if it is somehow missing, fall back to the plain share so access is never lost.
function shareQuietly_(item, email, role) {
  try {
    Drive.Permissions.create({ type: 'user', role: role, emailAddress: email }, item.getId(),
                             { sendNotificationEmail: false, supportsAllDrives: true });
  } catch (e) {
    if (role === 'writer') item.addEditor(email); else item.addViewer(email);
  }
}

// Uploaded documents (version 2). A file lands in ROOT/<folder_key>/<item_key>/, one sub-folder per checklist
// row, so a row with several files links to one folder. A retry with the same request_id finds the file it
// already made. trash_file only touches something that sits under the root folder.
const UPLOAD_MIMES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
const UPLOAD_MAX_BYTES = 7 * 1024 * 1024;

function childFolder_(parent, name) {
  const it = parent.getFoldersByName(name);
  return it.hasNext() ? it.next() : parent.createFolder(name);
}

function uploadFile_(req) {
  const slug = /^[A-Za-z0-9_-]{1,40}$/;
  if (!slug.test(String(req.folder_key)) || !slug.test(String(req.item_key))) return { ok: false, error: 'bad_folder' };
  if (!/^[A-Za-z0-9:_-]{1,80}$/.test(String(req.request_id))) return { ok: false, error: 'bad_request_id' };
  if (UPLOAD_MIMES.indexOf(String(req.mime)) < 0) return { ok: false, error: 'bad_type' };
  const name = String(req.name || 'file').replace(/[^A-Za-z0-9._ -]/g, '_').slice(0, 100) || 'file';
  const bytes = Utilities.base64Decode(String(req.data_b64 || ''));
  if (!bytes.length || bytes.length > UPLOAD_MAX_BYTES) return { ok: false, error: 'bad_size' };
  const root = DriveApp.getFolderById(P.getProperty('ROOT_FOLDER_ID'));
  const folder = childFolder_(childFolder_(root, req.folder_key), req.item_key);
  let file = null;
  const files = folder.getFiles();
  while (files.hasNext()) { const f = files.next(); if (f.getDescription() === 'request_id=' + req.request_id) file = f; }
  if (!file) {
    file = folder.createFile(Utilities.newBlob(bytes, String(req.mime), name));
    file.setDescription('request_id=' + req.request_id);
  }
  (req.share_with || []).forEach(function (a) {
    if (String(a).toLowerCase().endsWith('@' + P.getProperty('ALLOWED_DOMAIN'))) shareQuietly_(folder, a, 'reader');
  });
  let count = 0; const all = folder.getFiles(); while (all.hasNext()) { all.next(); count++; }
  return { ok: true, id: file.getId(), url: file.getUrl(), name: file.getName(),
           folder_id: folder.getId(), folder_url: folder.getUrl(), count: count };
}

function underRoot_(item, rootId) {
  let cur = item;
  for (let i = 0; i < 6; i++) {
    const ps = cur.getParents();
    if (!ps.hasNext()) return false;
    cur = ps.next();
    if (cur.getId() === rootId) return true;
  }
  return false;
}

function trashFile_(req) {
  const id = String(req.id || '');
  if (!/^[-\w]{20,}$/.test(id)) return { ok: false, error: 'bad_link' };
  const rootId = P.getProperty('ROOT_FOLDER_ID');
  if (id === rootId) return { ok: false, error: 'not_allowed' };
  let item = null;
  try { item = DriveApp.getFolderById(id); } catch (e1) {
    try { item = DriveApp.getFileById(id); } catch (e2) { return { ok: true, gone: true }; }   // already gone
  }
  if (!underRoot_(item, rootId)) return { ok: false, error: 'not_allowed' };
  item.setTrashed(true);
  return { ok: true };
}

// One look for every form (spot feedback #150-152): Times New Roman 12, body text justified, titles bold in Title Case.
// Done on each copy after it is filled, so the templates need no change. A formatting problem must never stop a form being made.
const FORM_FONT = 'Times New Roman', FORM_SIZE = 12, JUSTIFY_FROM = 60;      // paragraphs shorter than this stay as they are
const KEEP_CAPS_ = { DPO: 1, CENRR: 1, RER: 1, MC: 1, DOH: 1, JO: 1, OIC: 1, TNVS: 1, DM: 1, CESO: 1, MD: 1, MPA: 1, II: 1, III: 1, IV: 1, VI: 1, VII: 1, VIII: 1, IX: 1 };
// Titles that are always printed in capitals (spot feedback #164): the DPO heading is not Title Cased.
const KEEP_UPPER_TITLES_ = ['DEPARTMENT PERSONNEL ORDER', 'MEMORANDUM', 'CONCEPT NOTE',
  'NOTICE OF MEETING', 'MINUTES OF THE MEETING', 'EXECUTIVE BRIEFER'];
const SMALL_WORDS_ = { a: 1, an: 1, and: 1, as: 1, at: 1, by: 1, for: 1, from: 1, in: 1, of: 1, on: 1, or: 1, the: 1, to: 1, with: 1 };

// "CERTIFICATION OF EXPENSES" -> "Certification of Expenses". Initials and known acronyms keep their capitals.
function titleCase_(text) {
  let first = true;
  return String(text).replace(/[A-Za-z][A-Za-z'\u2019]*/g, function (w) {
    const isFirst = first; first = false;
    const up = w.toUpperCase(), low = w.toLowerCase();
    if (KEEP_CAPS_[up] || w.length === 1) return up;
    if (!isFirst && SMALL_WORDS_[low]) return low;
    return low.charAt(0).toUpperCase() + low.slice(1);
  });
}

// A short line with no sentence punctuation. Lines with a full stop, comma, colon or brackets are names, labels or sentences.
function looksLikeTitle_(text) {
  const t = String(text).trim();
  return t.length >= 3 && t.length <= 90 && /[A-Za-z]/.test(t) && !/[.,:;()\/]/.test(t);
}

function eachParagraph_(el, fn) {
  const type = el.getType();
  if (type === DocumentApp.ElementType.PARAGRAPH || type === DocumentApp.ElementType.LIST_ITEM) { fn(el); return; }
  if (typeof el.getNumChildren === 'function') for (let i = 0; i < el.getNumChildren(); i++) eachParagraph_(el.getChild(i), fn);
}

function formatDoc_(body) {
  try {
    const H = DocumentApp.HorizontalAlignment, NORMAL = DocumentApp.ParagraphHeading.NORMAL;
    eachParagraph_(body, function (p) {
      const text = p.getText();
      p.setFontFamily(FORM_FONT); p.setFontSize(FORM_SIZE);
      if (!text.trim()) return;
      const align = p.getAlignment(), heading = p.getHeading ? p.getHeading() : NORMAL;
      const bold = p.editAsText().isBold() === true;
      if (KEEP_UPPER_TITLES_.indexOf(text.trim().toUpperCase()) >= 0) {
        if (text !== text.toUpperCase()) p.editAsText().setText(text.toUpperCase());
        p.editAsText().setBold(true);
        return;
      }
      if (looksLikeTitle_(text) && (heading !== NORMAL || (bold && (align === H.CENTER || text === text.toUpperCase())))) {
        const fixed = titleCase_(text);
        if (fixed !== text) p.editAsText().setText(fixed);
        p.editAsText().setBold(true);
        return;
      }
      if ((align === null || align === H.LEFT || align === H.JUSTIFY) && text.trim().length >= JUSTIFY_FROM) p.setAlignment(H.JUSTIFY);
    });
  } catch (err) { /* keep the form as it is */ }
}

// ---- The post travel report (spot feedback #168, #169) -----------------------------------------------------------------
// Same letterhead as the DPO ("Republic of the Philippines / DEPARTMENT OF HEALTH / Office of the Secretary", with the seal
// and the logo), put in the real header whatever the template carried. at_letterhead_ lives in activity_templates.gs, in this
// same Apps Script project; without it the template's own header stays.
function reportLetterhead_(doc) {
  try {
    if (typeof at_letterhead_ !== 'function') return;
    const header = doc.getHeader() || doc.addHeader();
    header.clear();
    at_letterhead_(header);
  } catch (err) { /* keep the template's header */ }
}

const REPORT_TITLES_ = ['overview', 'day-by-day highlights', 'key points raised', 'key contributions and observations',
                        'support needed', 'policy recommendations', 'conclusion'];

function isReportTitle_(text) {
  return REPORT_TITLES_.indexOf(String(text).trim().replace(/:$/, '').toLowerCase()) >= 0;
}

// Only the section titles are bold; every other paragraph is plain with one blank line's space (12 pt) after it, and a title
// gets that space before it from the paragraph above. Lines that are centred or all capitals (names, signatures) are left alone.
function formatReport_(body) {
  try {
    const H = DocumentApp.HorizontalAlignment, T = DocumentApp.ElementType;
    const kids = [];
    for (let i = 0; i < body.getNumChildren(); i++) kids.push(body.getChild(i));
    let lastTitle = -1;
    kids.forEach(function (el, i) { if (el.getType() === T.PARAGRAPH && isReportTitle_(el.asParagraph().getText())) lastTitle = i; });
    // empty paragraphs before the last title only added space by hand; the spacing below replaces them
    for (let i = lastTitle - 1; i >= 0; i--) {
      const el = kids[i];
      if (el.getType() === T.PARAGRAPH && el.asParagraph().getText().trim() === '' && body.getNumChildren() > 1) {
        try { body.removeChild(el); kids[i] = null; } catch (e) { /* a paragraph Docs will not drop stays */ }
      }
    }
    const live = kids.filter(function (el) { return el; });
    let started = false, ended = false;
    live.forEach(function (el) {
      if (ended || el.getType() !== T.PARAGRAPH) { if (started && el.getType() !== T.PARAGRAPH) ended = true; return; }
      const p = el.asParagraph(), text = p.getText();
      if (isReportTitle_(text)) {
        started = true;
        p.setLineSpacing(1); p.setBold(true); p.setSpacingBefore(0); p.setSpacingAfter(0);
        return;
      }
      if (!started || !text.trim()) return;
      // the signature block follows the conclusion: a short, centred, capitalised or colon-ended line ends the body text
      if (p.getAlignment() === H.CENTER || text === text.toUpperCase() || text.trim().length < 40 && /:$/.test(text.trim())) { ended = true; return; }
      p.setLineSpacing(1); p.setBold(false); p.setSpacingBefore(0); p.setSpacingAfter(12);
    });
  } catch (err) { /* keep the report as it is */ }
}

// ---- The file copy (spot feedback #158) --------------------------------------------------------------------------------
// A DPO can ask for "extras": {file_copy: true}: after the order, a second page with the same content but NO letterhead
// or address footer, followed by the routing tables (BLHSD / Initials / Date, and Keywords / Related issuances). Google Docs
// shows a header on every page of a section, so the copy starts a new section with its own empty header and footer; the
// Apps Script document service cannot make a section, so this uses the Docs advanced service (Services > Google Docs API).
// Best effort: when it is not switched on, or Google refuses, the order itself is already complete and the result says why.
const FILE_COPY_MARK = '[[FILE COPY]]';
// The two boxes (spot feedback #185/#186). Row 2 of the first box carries the reviewer's name and title, centred, when the app
// knows who it is; the second box carries the keywords and the related issuances the app read from the invitation.
const FILE_COPY_MINS = { slip: [0, 150], keys: [0, 180] };

// Pure: the cells of the two boxes for one DPO's "extras".
function fileCopyTables_(extras) {
  const rv = (extras && extras.reviewer) || {};
  const who = rv.name ? rv.name + (rv.title ? '\n' + rv.title : '') : '';
  return {
    slip: [['', 'BLHSD'], ['Initials', who], ['Date', '']],
    keys: [['Keywords', (extras && extras.keywords) || ''], ['Related issuances, laws, directives', (extras && extras.issuances) || '']]
  };
}

// Pure: where the paragraph holding `mark` starts in a Docs API document, or -1.
function findMarkIndex_(docJson, mark) {
  const content = (docJson && docJson.body && docJson.body.content) || [];
  for (let i = 0; i < content.length; i++) {
    const els = (content[i].paragraph && content[i].paragraph.elements) || [];
    for (let j = 0; j < els.length; j++) {
      if (els[j].textRun && String(els[j].textRun.content).indexOf(mark) >= 0) return els[j].startIndex || 0;
    }
  }
  return -1;
}

// Pure: where the last section break starts, or -1 when the document still has only its first section.
function lastSectionBreakIndex_(docJson) {
  const content = (docJson && docJson.body && docJson.body.content) || [];
  let found = -1, count = 0;
  content.forEach(function (c) { if (c.sectionBreak) { count++; found = c.startIndex || 0; } });
  return count > 1 ? found : -1;
}

function plainTable_(body, cells) {
  const t = body.appendTable(cells);
  t.editAsText().setBold(false);
  t.editAsText().setFontFamily(FORM_FONT); t.editAsText().setFontSize(FORM_SIZE);
  return t;
}

// Sizes a box to its text and centres a column (spot feedback #185). Best effort: a box left at the default size is fine.
function shapeFileCopyBox_(table, mins, centreColumn) {
  try {
    fitTable_(table, mins);
    if (centreColumn < 0) return;
    for (let r = 0; r < table.getNumRows(); r++) {
      const cell = table.getCell(r, centreColumn);
      for (let k = 0; k < cell.getNumChildren(); k++) {
        const ch = cell.getChild(k);
        if (ch.getType() === DocumentApp.ElementType.PARAGRAPH) ch.asParagraph().setAlignment(DocumentApp.HorizontalAlignment.CENTER);
      }
    }
  } catch (e) { /* keep the box as it is */ }
}

function addFileCopy_(docId, extras) {
  if (typeof Docs === 'undefined') return 'docs_service_off';
  let placed = false;
  try {
    const doc = DocumentApp.openById(docId), body = doc.getBody(), n = body.getNumChildren();
    const mark = body.appendParagraph(FILE_COPY_MARK);
    mark.setBold(false);
    placed = true;
    const T = DocumentApp.ElementType;
    for (let i = 0; i < n; i++) {
      const el = body.getChild(i), t = el.getType();
      if (t === T.PARAGRAPH) body.appendParagraph(el.asParagraph().copy());
      else if (t === T.TABLE) body.appendTable(el.asTable().copy());
      else if (t === T.LIST_ITEM) body.appendListItem(el.asListItem().copy());
      else if (t === T.HORIZONTAL_RULE) body.appendHorizontalRule();
    }
    const cells = fileCopyTables_(extras);
    // Absent boxes keeps the DPO's two boxes; an explicit list selects the required boxes.
    const boxes = extras && Array.isArray(extras.boxes) ? extras.boxes : ['slip', 'keys'];
    ['slip', 'keys'].forEach(function (box) {
      if (boxes.indexOf(box) < 0) return;
      body.appendParagraph('').setBold(false);
      shapeFileCopyBox_(plainTable_(body, cells[box]), FILE_COPY_MINS[box], box === 'slip' ? 1 : -1);
    });
    doc.saveAndClose();

    const at = findMarkIndex_(Docs.Documents.get(docId), FILE_COPY_MARK);
    if (at < 0) throw new Error('mark not found');
    Docs.Documents.batchUpdate({ requests: [{ insertSectionBreak: { location: { index: at }, sectionType: 'NEXT_PAGE' } }] }, docId);
    const brk = lastSectionBreakIndex_(Docs.Documents.get(docId));
    if (brk < 0) throw new Error('section break not found');
    Docs.Documents.batchUpdate({ requests: [
      { createHeader: { type: 'DEFAULT', sectionBreakLocation: { index: brk } } },
      { createFooter: { type: 'DEFAULT', sectionBreakLocation: { index: brk } } },
      { updateSectionStyle: { range: { startIndex: brk + 1, endIndex: brk + 2 },
          sectionStyle: { useFirstPageHeaderFooter: false }, fields: 'useFirstPageHeaderFooter' } }
    ] }, docId);
    Docs.Documents.batchUpdate({ requests: [
      { replaceAllText: { containsText: { text: FILE_COPY_MARK, matchCase: true }, replaceText: '' } }
    ] }, docId);
    return 'ok';
  } catch (e) {
    if (placed) {                                    // never leave the marker text in the order
      try {
        Docs.Documents.batchUpdate({ requests: [
          { replaceAllText: { containsText: { text: FILE_COPY_MARK, matchCase: true }, replaceText: '' } }
        ] }, docId);
      } catch (e2) { /* nothing more to do */ }
    }
    return 'failed';
  }
}

// Sheets cannot justify text, so a sheet gets the font, the size and the titles.
function formatSheet_(sh) {
  try {
    const all = sh.getDataRange();
    all.setFontFamily(FORM_FONT).setFontSize(FORM_SIZE);
    const values = all.getValues(), formulas = all.getFormulas(), weights = all.getFontWeights();
    for (let r = 0; r < values.length; r++) for (let c = 0; c < values[r].length; c++) {
      const v = values[r][c];
      if (typeof v !== 'string' || formulas[r][c] || weights[r][c] !== 'bold' || !looksLikeTitle_(v)) continue;
      const cell = sh.getRange(r + 1, c + 1);
      cell.setValue(titleCase_(v)); cell.setFontWeight('bold');
    }
  } catch (err) { /* keep the form as it is */ }
}

function doc_(f) { return { ok: true, id: f.getId(), url: f.getUrl(), name: f.getName() }; }

// Google Sheets templates (the CENRR and RER forms are spreadsheets). Same {{placeholders}}; a repeated
// row is the one row that holds the marker, copied once per item.
function applyFieldsSheet_(sh, fields) {
  Object.keys(fields).forEach(function (k) {
    if (/^[a-z0-9_]+$/.test(k)) sh.createTextFinder('{{' + k + '}}').replaceAllWith(String(fields[k]));
  });
  sh.createTextFinder('\\{\\{[a-z0-9_]+\\}\\}').useRegularExpression(true).replaceAllWith('');   // never leave raw braces
}

function applyRowsSheet_(sh, rows) {
  Object.keys(rows).forEach(function (k) {
    const spec = rows[k], hit = sh.createTextFinder('{{' + spec.marker + '}}').findNext(); if (!hit) return;
    const r = hit.getRow(), lastCol = sh.getLastColumn(), data = spec.data.length ? spec.data : [{}];
    if (data.length > 1) {
      sh.insertRowsAfter(r, data.length - 1);
      for (let i = 1; i < data.length; i++) sh.getRange(r, 1, 1, lastCol).copyTo(sh.getRange(r + i, 1, 1, lastCol));
    }
    data.forEach(function (d, i) {
      const range = sh.getRange(r + i, 1, 1, lastCol);
      Object.keys(d).forEach(function (c) { range.createTextFinder('{{' + c + '}}').replaceAllWith(String(d[c])); });
    });
  });
}

function applyFields_(body, fields) {
  Object.keys(fields).forEach(function (k) {
    if (/^[a-z0-9_]+$/.test(k)) body.replaceText('\\{\\{' + k + '\\}\\}', esc_(fields[k]));
  });
  body.replaceText('\\{\\{[a-z0-9_]+\\}\\}', '');   // never leave raw braces
}

// Spot feedback #200: the sections of the travel report from "Key points" on are optional. One the traveller left empty is taken out
// of the document, its title as well as its text, and its block is dropped so applyBlocks_ does not look for it.
const OPTIONAL_REPORT_SECTIONS_ = { key_points: 'key points raised', contributions: 'key contributions and observations',
  support_needed: 'support needed', recommendations: 'policy recommendations', conclusion: 'conclusion' };

// Pure: true when a block has no text in any of its lines.
function blockIsEmpty_(lines) {
  return !(lines || []).some(function (l) { return String(l).trim() !== ''; });
}

function dropEmptyReportSections_(body, blocks) {
  Object.keys(OPTIONAL_REPORT_SECTIONS_).forEach(function (k) {
    if (!(k in blocks) || !blockIsEmpty_(blocks[k])) return;
    try {
      const hit = body.findText('\\{\\{' + k + '\\}\\}');
      if (!hit) return;
      const para = hit.getElement().getParent().asParagraph(), parent = para.getParent();
      const idx = parent.getChildIndex(para), title = OPTIONAL_REPORT_SECTIONS_[k];
      const prev = idx > 0 ? parent.getChild(idx - 1) : null;
      parent.removeChild(para);
      if (prev && prev.getType() === DocumentApp.ElementType.PARAGRAPH &&
          prev.asParagraph().getText().trim().replace(/:$/, '').toLowerCase() === title) parent.removeChild(prev);
      delete blocks[k];
    } catch (err) { /* leave the section as it is rather than fail the document */ }
  });
}

// Spot feedback #201: the head's name and designation start at the 3-inch mark of the ruler (216 pt) on the documents the
// Director signs alone: the MC 114 justification and the Job Order certification. The name and its title keep their lines.
const SIGNATORY_FIELDS_ = { mc114_justification: ['approver_name', 'approver_title'], jo_cert: ['signatory_name', 'signatory_title'] };
const SIGNATORY_INDENT_PT_ = 216;

function alignSignatory_(body, fields, keys) {
  try {
    const name = String(fields[keys[0]] || '').trim(), title = String(fields[keys[1]] || '').trim();
    if (!name) return;
    const T = DocumentApp.ElementType;
    for (let i = 0; i < body.getNumChildren(); i++) {
      const el = body.getChild(i);
      if (el.getType() !== T.PARAGRAPH) continue;
      const p = el.asParagraph(), text = p.getText().trim();
      if (text.indexOf(name) !== 0) continue;
      const lines = [p];
      for (let j = i + 1; j < body.getNumChildren() && j <= i + 2; j++) {
        const nx = body.getChild(j);
        if (nx.getType() === T.PARAGRAPH && title && nx.asParagraph().getText().trim().indexOf(title) === 0) { lines.push(nx.asParagraph()); break; }
      }
      lines.forEach(function (q) {
        q.setAlignment(DocumentApp.HorizontalAlignment.LEFT);
        q.setIndentStart(SIGNATORY_INDENT_PT_); q.setIndentFirstLine(SIGNATORY_INDENT_PT_);
      });
      return;
    }
  } catch (err) { /* keep the signature block where the template put it */ }
}

// A memo addressee is a three-paragraph group: bold name, plain title and office.
// Keep each prototype's formatting when repeating the group; FOR appears only once.
function applyAddressees_(body, groups) {
  const keys = ['for_name', 'for_title', 'for_office'];
  const hit = body.findText('\\{\\{for_name\\}\\}');
  if (!hit) return;
  const name = hit.getElement().getParent().asParagraph(), parent = name.getParent();
  const index = parent.getChildIndex(name), prototypes = [];
  for (let i = 0; i < keys.length; i++) {
    const para = parent.getChild(index + i).asParagraph();
    if (para.getText().indexOf('{{' + keys[i] + '}}') < 0) throw new Error('incomplete addressee group');
    prototypes.push(para.copy());
  }
  const data = groups.length ? groups : [{}];
  data.forEach(function (group, n) {
    keys.forEach(function (key, i) {
      const para = n === 0 ? parent.getChild(index + i).asParagraph()
        : parent.insertParagraph(index + n * keys.length + i, prototypes[i].copy());
      if (n > 0 && i === 0) para.replaceText('^FOR:', '');
      para.replaceText('\\{\\{' + key + '\\}\\}', esc_(group[key] || ''));
    });
  });
}

function applyBlocks_(body, blocks) {
  Object.keys(blocks).forEach(function (k) {
    const hit = body.findText('\\{\\{' + k + '\\}\\}'); if (!hit) return;
    const element = hit.getElement().getParent();
    const isList = element.getType() === DocumentApp.ElementType.LIST_ITEM;
    const para = isList ? element.asListItem() : element.asParagraph(), parent = para.getParent();
    const lines = blocks[k].length ? blocks[k] : [''];
    para.setText(lines[0]);
    const idx = parent.getChildIndex(para);
    for (let i = 1; i < lines.length; i++) {
      if (isList) {
        // Copy glyph, nesting and paragraph attributes, and join the original list.
        parent.insertListItem(idx + i, para.copy()).setText(lines[i]).setListId(para);
      } else parent.insertParagraph(idx + i, lines[i]).setAttributes(para.getAttributes());
    }
  });
}

// Column widths that fit the text (spot feedback #181): each column as wide as its longest line needs, within the 468 pt
// between the margins, in Times New Roman 12 with single spacing and no space between rows.
function fitTable_(table, mins) {
  const n = table.getRow(0).getNumCells(), longest = [];
  for (let c = 0; c < n; c++) longest.push(0);
  for (let r = 0; r < table.getNumRows(); r++) {
    for (let c = 0; c < n; c++) {
      table.getCell(r, c).getText().split('\n').forEach(function (line) { longest[c] = Math.max(longest[c], line.length); });
    }
  }
  const want = longest.map(function (len, c) { return Math.max(60, (mins && mins[c]) || 0, len * 6.4 + 16); });
  const total = want.reduce(function (a, b) { return a + b; }, 0), scale = total > 468 ? 468 / total : 1;
  want.forEach(function (w, c) { table.setColumnWidth(c, Math.floor(w * scale)); });
  const text = table.editAsText();
  text.setFontFamily('Times New Roman');
  text.setFontSize(12);
  for (let r = 0; r < table.getNumRows(); r++) {
    for (let c = 0; c < n; c++) {
      const cell = table.getCell(r, c);
      for (let k = 0; k < cell.getNumChildren(); k++) {
        const ch = cell.getChild(k);
        if (ch.getType() === DocumentApp.ElementType.PARAGRAPH) {
          ch.asParagraph().setLineSpacing(1).setSpacingBefore(0).setSpacingAfter(0);
        }
      }
    }
  }
}

function applyRows_(body, rows) {
  Object.keys(rows).forEach(function (k) {
    const spec = rows[k], hit = body.findText('\\{\\{' + spec.marker + '\\}\\}'); if (!hit) return;
    let el = hit.getElement();
    while (el && el.getType() !== DocumentApp.ElementType.TABLE_ROW) el = el.getParent();
    if (!el) return;
    const row = el.asTableRow(), table = row.getParent().asTable(), idx = table.getChildIndex(row);
    if (spec.remove) {          // e.g. one person on a DPO: the Name | Position table is not wanted at all
      const parent = table.getParent();
      if (parent.getNumChildren() > 1) parent.removeChild(table);
      return;
    }
    const data = spec.data.length ? spec.data : [{}];
    for (let i = 1; i < data.length; i++) table.insertTableRow(idx + i, row.copy());
    data.forEach(function (d, i) {
      const r = table.getRow(idx + i);
      Object.keys(d).forEach(function (c) { r.replaceText('\\{\\{' + c + '\\}\\}', esc_(d[c])); });
    });
    if (spec.fit) fitTable_(table);
  });
}
