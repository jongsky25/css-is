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
  if (isSheet) {
    SpreadsheetApp.openById(copy.getId()).getSheets().forEach(function (sh) {
      applyRowsSheet_(sh, req.rows || {}); applyFieldsSheet_(sh, req.fields || {}); formatSheet_(sh);
    });
    SpreadsheetApp.flush();
  } else {
    const doc = DocumentApp.openById(copy.getId()), body = doc.getBody();
    applyRows_(body, req.rows || {}); applyBlocks_(body, req.blocks || {}); applyFields_(body, req.fields || {});
    formatDoc_(body);
    doc.saveAndClose();
  }
  (req.share_with || []).forEach(function (a) {
    if (String(a).toLowerCase().endsWith('@' + P.getProperty('ALLOWED_DOMAIN'))) shareQuietly_(copy, a, 'writer');
  });
  return doc_(copy);
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

function applyBlocks_(body, blocks) {
  Object.keys(blocks).forEach(function (k) {
    const hit = body.findText('\\{\\{' + k + '\\}\\}'); if (!hit) return;
    const para = hit.getElement().getParent().asParagraph(), parent = para.getParent();
    const lines = blocks[k].length ? blocks[k] : [''];
    para.setText(lines[0]);
    const idx = parent.getChildIndex(para);
    for (let i = 1; i < lines.length; i++) parent.insertParagraph(idx + i, lines[i]).setAttributes(para.getAttributes());
  });
}

function applyRows_(body, rows) {
  Object.keys(rows).forEach(function (k) {
    const spec = rows[k], hit = body.findText('\\{\\{' + spec.marker + '\\}\\}'); if (!hit) return;
    let el = hit.getElement();
    while (el && el.getType() !== DocumentApp.ElementType.TABLE_ROW) el = el.getParent();
    if (!el) return;
    const row = el.asTableRow(), table = row.getParent().asTable(), idx = table.getChildIndex(row);
    const data = spec.data.length ? spec.data : [{}];
    for (let i = 1; i < data.length; i++) table.insertTableRow(idx + i, row.copy());
    data.forEach(function (d, i) {
      const r = table.getRow(idx + i);
      Object.keys(d).forEach(function (c) { r.replaceText('\\{\\{' + c + '\\}\\}', esc_(d[c])); });
    });
  });
}
