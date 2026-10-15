// Office Connect: one-time travel template maker.
//
// Add this file to the SAME Apps Script project as travel_docs.gs (File > New > Script). It turns the
// office's Word and Excel travel forms into Google Docs / Sheets with {{placeholders}}, and saves their
// ids as the TPL_* Script Properties the relay reads. Run makeTravelTemplates() once, then read the
// Execution log: it lists every placeholder that did not land, so nothing is guessed.
//
// Setup: set TM_SOURCE_FOLDER_ID below to the id of the "Travel Reimbursement Template" folder (the part
// of its Drive address after /folders/). The office mailbox must be able to open that folder.
// Run it as the office mailbox. The first run asks for permission to use Drive, Docs, Sheets and the web.
// Converted templates are put in a "_templates" folder inside the ROOT_FOLDER_ID folder.
//
// A template whose TPL_ property is already set is skipped. To redo one, delete its property first.
// checkTravelTemplates() re-checks the placeholders in the templates that are already set.

const TM_SOURCE_FOLDER_ID = 'PUT-THE-TRAVEL-REIMBURSEMENT-TEMPLATE-FOLDER-ID-HERE';

const TM_DOC = 'application/vnd.google-apps.document';
const TM_SHEET = 'application/vnd.google-apps.spreadsheet';

const TM_TEMPLATES = [
  { key: 'appendix_a', source: 'Appendix A.docx', mime: TM_DOC, build: tm_appendixA_,
    expect: ['traveler_name', 'purpose', 'r_date', 'r_place', 'r_dep', 'r_arr', 'r_mode', 'r_allowance', 'r_perdiem',
             'r_total', 'grand_total', 'certifier_name', 'certifier_title', 'prepared_by', 'approver_name', 'approver_title'] },
  { key: 'appendix_b', source: 'Appendix B.docx', mime: TM_DOC, build: tm_appendixB_,
    expect: ['date', 'head_name', 'head_title', 'station', 'dpo_ref', 'chk_strict', 'chk_cut', 'chk_extended', 'chk_other',
             'refund_amount', 'refund_or_no', 'refund_or_date', 'explanation', 'evidence_list', 'traveler_name',
             'traveler_designation', 'approver_name', 'approver_title'] },
  { key: 'travel_report', source: 'Post Travel Report.docx', mime: TM_DOC, build: tm_report_,
    expect: ['name_designation', 'travel_dates', 'dpo_ref', 'overview', 'day_by_day', 'key_points', 'contributions',
             'support_needed', 'recommendations', 'conclusion', 'submitted_by_name', 'submitted_by_title',
             'reviewed_by_name', 'reviewed_by_title', 'approved_by_name', 'approved_by_title'] },
  { key: 'jo_cert', source: 'Certification for Job Order.docx', mime: TM_DOC, build: tm_joCert_,
    expect: ['date', 'traveler_name', 'activities', 'obligations', 'request_phrase', 'dm_citation', 'signatory_name',
             'signatory_title'] },
  { key: 'mc114_justification', source: 'JUSTIFICATION for MC 114.docx', mime: TM_DOC, build: tm_mc114_,
    expect: ['body', 'approver_name', 'approver_title'] },
  { key: 'cenrr', source: 'CENRR (Below 300).xlsx', mime: TM_SHEET, build: tm_cenrr_,
    expect: ['employee_name', 'employee_no', 'office', 'division', 'p_date', 'p_text', 'p_amount', 'total', 'purpose',
             'dates', 'dpo_ref', 'printed_name', 'designation', 'noted_by_name', 'noted_by_title'] },
  { key: 'rer', source: 'RER (Above 300).xlsx', mime: TM_SHEET, build: tm_rer_,
    expect: ['payee_name', 'payee_designation', 'amount_words', 'amount_figures', 'ride_from', 'ride_to', 'ride_date',
             'activity_title', 'dpo_ref'] }
];

// ------------------------------------------------------------------ entry points ---

function makeTravelTemplates() {
  const P = PropertiesService.getScriptProperties();
  if (TM_SOURCE_FOLDER_ID.indexOf('PUT-') === 0) throw new Error('Set TM_SOURCE_FOLDER_ID at the top of this file first.');
  const source = DriveApp.getFolderById(TM_SOURCE_FOLDER_ID);
  const out = tm_outFolder_(P);
  const report = [];
  TM_TEMPLATES.forEach(function (t) {
    if (P.getProperty('TPL_' + t.key)) { report.push(t.key + ': already set, skipped'); return; }
    try {
      const file = tm_find_(source, t.source);
      if (!file) throw new Error('could not find "' + t.source + '" under the source folder');
      const id = tm_convert_(file, t.mime, out.getId(), tm_title_(t));
      t.build(id);
      P.setProperty('TPL_' + t.key, id);
      const missing = tm_missing_(id, t);
      report.push(t.key + ': ' + (missing.length ? 'MISSING ' + missing.join(', ') : 'all placeholders present')
                  + '  https://drive.google.com/open?id=' + id);
    } catch (e) {
      report.push(t.key + ': FAILED - ' + e.message);
    }
  });
  Logger.log('\n' + report.join('\n'));
  return report.join('\n');
}

function checkTravelTemplates() {
  const P = PropertiesService.getScriptProperties(), report = [];
  TM_TEMPLATES.forEach(function (t) {
    const id = P.getProperty('TPL_' + t.key);
    if (!id) { report.push(t.key + ': no TPL_' + t.key + ' property'); return; }
    try {
      const missing = tm_missing_(id, t);
      report.push(t.key + ': ' + (missing.length ? 'MISSING ' + missing.join(', ') : 'all placeholders present'));
    } catch (e) { report.push(t.key + ': cannot open - ' + e.message); }
  });
  Logger.log('\n' + report.join('\n'));
  return report.join('\n');
}

// ------------------------------------------------------------------------ helpers ---

function tm_title_(t) { return 'Template - ' + t.key; }

function tm_outFolder_(P) {
  const root = DriveApp.getFolderById(P.getProperty('ROOT_FOLDER_ID'));
  const it = root.getFoldersByName('_templates');
  return it.hasNext() ? it.next() : root.createFolder('_templates');
}

function tm_find_(folder, name) {
  const files = folder.getFilesByName(name);
  if (files.hasNext()) return files.next();
  const subs = folder.getFolders();
  while (subs.hasNext()) { const f = tm_find_(subs.next(), name); if (f) return f; }
  return null;
}

// Convert a Word / Excel file into a Google Doc / Sheet (a copy with a Google type), in a folder.
function tm_convert_(file, mime, folderId, title) {
  const res = UrlFetchApp.fetch('https://www.googleapis.com/drive/v3/files/' + file.getId() + '/copy?supportsAllDrives=true', {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    payload: JSON.stringify({ name: title, mimeType: mime, parents: [folderId] })
  });
  if (res.getResponseCode() !== 200) throw new Error('conversion failed (' + res.getResponseCode() + '): ' + res.getContentText().slice(0, 200));
  return JSON.parse(res.getContentText()).id;
}

function tm_lit_(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

function tm_missing_(id, t) {
  const text = t.mime === TM_DOC ? tm_docText_(id) : tm_sheetText_(id);
  return t.expect.filter(function (k) { return text.indexOf('{{' + k + '}}') < 0; });
}

function tm_docText_(id) {
  const doc = DocumentApp.openById(id);
  return doc.getBody().getText() + '\n' + (doc.getFooter() ? doc.getFooter().getText() : '');
}

function tm_sheetText_(id) {
  let out = '';
  SpreadsheetApp.openById(id).getSheets().forEach(function (sh) {
    const r = sh.getDataRange();
    r.getValues().forEach(function (row) { out += row.join('\t') + '\n'; });
  });
  return out;
}

// Replace text anywhere in a document body (regex, RE2). Replacements here only ever hold {{placeholders}}.
function tm_rep_(body, pattern, repl) { body.replaceText(pattern, repl); }

// Replace a run of paragraphs with ONE plain paragraph holding `placeholder`.
//   start: text the first paragraph starts with (exact: whole text equals it)
//   end:   text the paragraph AFTER the run starts with (exact likewise), or null = up to the next table
//   opt.includeStart: the start paragraph itself is replaced too (otherwise it stays as the heading)
function tm_section_(body, start, end, placeholder, opt) {
  opt = opt || {};
  const n = body.getNumChildren();
  const textOf = function (el) { return el.asText().getText().replace(/\s+/g, ' ').trim(); };
  const isPara = function (el) {
    const ty = el.getType();
    return ty === DocumentApp.ElementType.PARAGRAPH || ty === DocumentApp.ElementType.LIST_ITEM;
  };
  const hit = function (el, want) { return opt.exact ? textOf(el) === want : textOf(el).indexOf(want) === 0; };
  let s = -1, e = -1;
  for (let i = 0; i < n; i++) {
    const el = body.getChild(i);
    if (s < 0) { if (isPara(el) && hit(el, start)) s = i; continue; }
    if (end === null ? el.getType() === DocumentApp.ElementType.TABLE : (isPara(el) && hit(el, end))) { e = i; break; }
  }
  if (s < 0 || e < 0) return false;
  const from = opt.includeStart ? s : s + 1;
  body.insertParagraph(from, placeholder);                      // old element j (>= from) is now j + 1
  for (let i = e; i >= from + 1; i--) body.removeChild(body.getChild(i));
  return true;
}

// Within a table row (found by text), replace text.
function tm_rowRep_(body, rowContains, pattern, repl) {
  const tables = body.getTables();
  for (let t = 0; t < tables.length; t++) {
    const table = tables[t];
    for (let r = 0; r < table.getNumRows(); r++) {
      const row = table.getRow(r);
      if (row.getText().indexOf(rowContains) >= 0) { row.replaceText(pattern, repl); return true; }
    }
  }
  return false;
}

function tm_removeRowsContaining_(body, texts) {
  body.getTables().forEach(function (table) {
    for (let r = table.getNumRows() - 1; r >= 0; r--) {
      const txt = table.getRow(r).getText();
      if (texts.some(function (x) { return txt.indexOf(x) >= 0; })) table.removeRow(r);
    }
  });
}

// ---------------------------------------------------------------------- the Docs ---

function tm_appendixA_(id) {
  const body = DocumentApp.openById(id).getBody();
  tm_rep_(body, 'Name: ELVIE JO ROBIS', 'Name: {{traveler_name}}');
  tm_rep_(body, 'Purpose of Travel: .*', 'Purpose of Travel: {{purpose}}');
  // the one sample row that stays becomes the repeating row
  tm_rowRep_(body, 'September 01, 2026', 'September 01, 2026', '{{r_date}}');
  tm_rowRep_(body, '{{r_date}}', 'Residence in \\(Fairview Quezon City\\) to DOH Central Office', '{{r_place}}');
  tm_rowRep_(body, '{{r_date}}', '07:00 AM', '{{r_dep}}');
  tm_rowRep_(body, '{{r_date}}', '08:00 AM', '{{r_arr}}');
  tm_rowRep_(body, '{{r_date}}', 'Grab', '{{r_mode}}');
  tm_rowRep_(body, '{{r_date}}', '700', '{{r_allowance}}');
  tm_rowRep_(body, '{{r_date}}', '360', '{{r_perdiem}}');
  tm_rowRep_(body, '{{r_date}}', '1,060', '{{r_total}}');
  tm_removeRowsContaining_(body, ['DOH-Central Office to Sunday', 'ACTIVITY PROPER', 'Sunday Hevea Hotel and Resort to DOH',
                                  'DOH-Central Office to Residence']);
  tm_rep_(body, 'PhP2,120', 'PhP{{grand_total}}');
  tm_rep_(body, 'MARIA LOURDES B\\. GAJITOS, MD, MPH, CFP', '{{certifier_name}}');
  tm_rep_(body, 'Medical Officer V', '{{certifier_title}}');
  tm_rowRep_(body, 'Prepared by', 'Name', '{{prepared_by}}');
  tm_rep_(body, 'JUAN ALFONSO R\\. PEREZ IV, MD, MBA, MPM', '{{approver_name}}');
  tm_rep_(body, 'OIC-Director IV-BLHSD', '{{approver_title}}');
}

function tm_appendixB_(id) {
  const body = DocumentApp.openById(id).getBody();
  tm_rep_(body, 'JUAN ALFONSO R\\. PEREZ IV, MD, MBA, MPM', '{{head_name}}');
  tm_rep_(body, 'OIC-Director IV', '{{head_title}}');
  tm_rep_(body, 'Bureau of Local Health System Development', '{{station}}');
  tm_rep_(body, 'September 07, 2026', '{{date}}');
  tm_rep_(body, 'DPO No\\.\\s?2026-5556 dated August 04, 2026', '{{dpo_ref}}');
  tm_rep_(body, '☒ Strictly', '{{chk_strict}} Strictly');
  tm_rep_(body, '☐ Cut short', '{{chk_cut}} Cut short');
  tm_rep_(body, '☐ Extended', '{{chk_extended}} Extended');
  tm_rep_(body, '☐ Other deviations', '{{chk_other}} Other deviations');
  tm_rep_(body, 'Excess payment in the amount of', 'Excess payment in the amount of {{refund_amount}}');
  tm_rep_(body, 'O\\.R\\. No\\. _+ dated _+', 'O.R. No. {{refund_or_no}} dated {{refund_or_date}}');
  tm_section_(body, 'Explanation or Justification', 'Evidence of Travel attached hereto', '{{explanation}}', { exact: false });
  tm_section_(body, 'Evidence of Travel attached hereto', 'Respectfully submitted', '{{evidence_list}}', { exact: false });
  tm_rep_(body, 'ARYAMEIR BAGIS ISMAEL', '{{traveler_name}}');
  tm_rep_(body, 'Freelance Consultant', '{{traveler_designation}}');
  tm_rep_(body, 'MARIA LOURDES B\\. GAJITOS, MD, MPH', '{{approver_name}}');
  tm_rep_(body, 'Medical Officer V-BLHSD', '{{approver_title}}');
}

function tm_report_(id) {
  const body = DocumentApp.openById(id).getBody();
  tm_rep_(body, 'Maria Lourdes Gajitos, Medical Officer V', '{{name_designation}}');
  tm_rep_(body, 'November 10-14, 2025', '{{travel_dates}}');
  tm_rep_(body, 'DPO No\\. 2025-7852 dated October 29, 2025', '{{dpo_ref}}');
  const x = { exact: true };
  tm_section_(body, 'Overview', 'Day-by-Day Highlights', '{{overview}}', x);
  tm_section_(body, 'Day-by-Day Highlights', 'Key Points Raised:', '{{day_by_day}}', x);
  tm_section_(body, 'Key Points Raised:', 'Key Contributions and Observations', '{{key_points}}', x);
  tm_section_(body, 'Key Contributions and Observations', 'Support Needed:', '{{contributions}}', x);
  tm_section_(body, 'Support Needed:', 'Policy Recommendations', '{{support_needed}}', x);
  tm_section_(body, 'Policy Recommendations', 'Conclusion', '{{recommendations}}', x);
  tm_section_(body, 'Conclusion', null, '{{conclusion}}', x);
  tm_rep_(body, 'DEMI ARANTXA C\\. SEPE', '{{submitted_by_name}}');
  tm_rep_(body, 'Senior Health Program Officer', '{{submitted_by_title}}');
  tm_rep_(body, 'Special Concerns and Equity in Health Section', '');
  tm_rep_(body, 'MARIA LOURDES B\\. GAJITOS, MD, MPH', '{{reviewed_by_name}}');
  tm_rep_(body, 'Medical Officer V', '{{reviewed_by_title}}');
  tm_rep_(body, 'MAR WYNN D\\. BELLO, MD, MPA, CESO IV', '{{approved_by_name}}');
  tm_rep_(body, 'Director IV', '{{approved_by_title}}');
}

function tm_joCert_(id) {
  const body = DocumentApp.openById(id).getBody();
  tm_rep_(body, 'July 28, 2026', '{{date}}');
  tm_rep_(body, 'Mr\\. Ronnel John Dela Cruz', '{{traveler_name}}');
  tm_rep_(body, 'during the Conduct of.*respectively', 'during the following:');
  // the activities go in their own paragraph right after the sentence that introduces them
  const n = body.getNumChildren();
  for (let i = 0; i < n; i++) {
    const el = body.getChild(i);
    if (el.getType() === DocumentApp.ElementType.PARAGRAPH && el.asText().getText().indexOf('during the following:') >= 0) {
      body.insertParagraph(i + 1, '{{activities}}');
      break;
    }
  }
  tm_section_(body, 'The said undertaking requires', 'Furthermore', '{{obligations}}', { exact: false });
  tm_rep_(body, 'reimbursement purposes pursuant to Department Memorandum.*DM No\\. 2025-0202-A\\.',
          '{{request_phrase}} purposes pursuant to {{dm_citation}}.');
  tm_rep_(body, 'JUAN ALFONSO PEREZ IV, MD, MBA, MDM', '{{signatory_name}}');
  tm_rep_(body, 'OIC - Director IV', '{{signatory_title}}');
}

function tm_mc114_(id) {
  const body = DocumentApp.openById(id).getBody();
  tm_section_(body, 'This is to justify', 'This justification is issued', '{{body}}', { exact: false, includeStart: true });
  tm_rep_(body, 'JUAN ALFONSO R\\. PEREZ IV, MD, MBA, MPM', '{{approver_name}}');
  tm_rep_(body, 'OIC-Director IV', '{{approver_title}}');
}

// -------------------------------------------------------------------- the Sheets ---

// Replace text in a sheet. first=true changes only the first match (reading order).
function tm_sheetRep_(sh, pattern, repl, first) {
  const finder = sh.createTextFinder(pattern).useRegularExpressions(true);
  if (!first) { finder.replaceAllWith(repl); return; }
  const hit = finder.findNext();
  if (hit) hit.createTextFinder(pattern).useRegularExpressions(true).replaceAllWith(repl);
}

// The row (1-based) of the first cell whose text matches, or 0.
function tm_sheetRow_(sh, pattern) {
  const hit = sh.createTextFinder(pattern).useRegularExpressions(true).findNext();
  return hit ? hit.getRow() : 0;
}

// Put `text` in the first numeric cell of a row.
function tm_numericCell_(sh, row, text) {
  const vals = sh.getRange(row, 1, 1, sh.getLastColumn()).getValues()[0];
  for (let c = 0; c < vals.length; c++) {
    if (typeof vals[c] === 'number') { sh.getRange(row, c + 1).setNumberFormat('@').setValue(text); return true; }
  }
  return false;
}

function tm_cenrr_(id) {
  const sh = SpreadsheetApp.openById(id).getSheets()[0];
  tm_sheetRep_(sh, 'DR\\. JUNE ROSE A\\. NAIG', '{{employee_name}}', true);
  tm_sheetRep_(sh, 'DR\\. JUNE ROSE A\\. NAIG', '{{printed_name}}', false);
  tm_sheetRep_(sh, 'Employee No\\. 20240016', 'Employee No. {{employee_no}}', false);
  tm_sheetRep_(sh, 'Office: BLHSD', 'Office: {{office}}', false);
  tm_sheetRep_(sh, 'Division: HSDD', 'Division: {{division}}', false);
  tm_sheetRep_(sh, 'To attend the .*per DPO No\\. 2026-0507', 'To {{purpose}} on {{dates}} per {{dpo_ref}}', false);
  // one repeating line: the date and the details share a cell, the amount sits beside it
  const line = tm_sheetRow_(sh, 'Taxi fare from');
  if (line) {
    const dateRow = tm_sheetRow_(sh, 'March 10, 2026');
    const cell = sh.createTextFinder('Taxi fare from').useRegularExpressions(true).findNext();
    cell.setValue('{{p_date}}: {{p_text}}');
    tm_numericCell_(sh, line, '{{p_amount}}');
    if (dateRow && dateRow === line - 1) sh.deleteRow(dateRow);
  }
  const total = tm_sheetRow_(sh, '^TOTAL$');
  if (total) tm_numericCell_(sh, total, '{{total}}');
  tm_sheetRep_(sh, 'Senior Health Program Officer', '{{designation}}', false);
  tm_sheetRep_(sh, 'MAR WYNN D\\. BELLO, MD, MPA, CESO IV', '{{noted_by_name}}', false);
  tm_sheetRep_(sh, 'Director IV', '{{noted_by_title}}', false);
}

function tm_rer_(id) {
  const sh = SpreadsheetApp.openById(id).getSheets()[0];
  tm_sheetRep_(sh, 'MR\\. RALIE JAY N\\. RAMOS', '{{payee_name}}', false);
  tm_sheetRep_(sh, 'ADMINISTRATIVE ASSISTANT III', '{{payee_designation}}', false);
  tm_sheetRep_(sh, 'of _{3,}', 'of {{amount_words}}', false);
  tm_sheetRep_(sh, '\\(P_{3,}\\)', '(P{{amount_figures}})', false);
  tm_sheetRep_(sh, 'Taxi fare from _+', 'fare from {{ride_from}} to {{ride_to}}', false);
  tm_sheetRep_(sh, '\\bon _{3,}', 'on {{ride_date}}', false);
  tm_sheetRep_(sh, 'in Attendance to .*DPO No\\. 2026-5451', 'in attendance to {{activity_title}} as per {{dpo_ref}}', false);
}
