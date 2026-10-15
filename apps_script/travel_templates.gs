// Office Connect: one-time travel template maker.
//
// Add this file to the SAME Apps Script project as travel_docs.gs (File > New > Script). It turns the
// office's Word and Excel travel forms into Google Docs / Sheets with {{placeholders}}, and saves their
// ids as the TPL_* Script Properties the relay reads. Run makeTravelTemplates() once, then read the
// Execution log: it lists every placeholder that did not land, so nothing is guessed.
//
// Setup: set TM_SOURCE_FOLDER_ID below to the id of the "Travel Reimbursement Template" folder (the part
// of its Drive address after /folders/). The office mailbox must be able to open that folder.
// Also add the Drive API service: Services (+ beside Services) > Drive API > Add (version v3).
// Run it as the office mailbox. The first run asks for permission to use Drive, Docs and Sheets.
// Converted templates are put in a "_templates" folder inside the ROOT_FOLDER_ID folder.
//
// A template that is already set and has every placeholder is kept; one with gaps is made again (the older copy stays
// in _templates). Run it as often as you like.
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
  const stamp = Utilities.formatDate(new Date(), 'Asia/Manila', 'MMM d HH:mm');
  const report = [];
  TM_TEMPLATES.forEach(function (t) {
    try {
      // A template that is already set and has every placeholder is kept; anything else is (re)made.
      const existing = P.getProperty('TPL_' + t.key);
      if (existing) {
        let gaps = null;
        try { gaps = tm_missing_(existing, t); } catch (e) { gaps = ['(could not open it)']; }
        if (!gaps.length) { report.push(t.key + ': already good, kept'); return; }
      }
      const file = tm_find_(source, t.source);
      if (!file) throw new Error('could not find "' + t.source + '" under the source folder');
      const id = tm_convert_(file, t.mime, out.getId(), tm_title_(t) + ' (' + stamp + ')');
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
// Uses the Drive API "advanced service" (Services > Drive API > v3), which needs no web-request permission.
function tm_convert_(file, mime, folderId, title) {
  if (typeof Drive === 'undefined') {
    throw new Error('add the Drive API service first: Services (the + beside Services) > Drive API > Add');
  }
  const copy = Drive.Files.copy({ name: title, mimeType: mime, parents: [folderId] }, file.getId(), { supportsAllDrives: true });
  if (!copy || !copy.id) throw new Error('conversion returned nothing for ' + file.getName());
  return copy.id;
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

// In a pattern, every space matches any run of spaces, tabs and non-breaking spaces (Word text often has them).
function tm_pat_(p) { return String(p).replace(/ /g, '[ \\x{00A0}\\t]+'); }
function tm_norm_(s) { return String(s).replace(/[\s\u00a0]+/g, ' ').trim(); }

// Replace text anywhere in a document body (regex, RE2). Replacements here only ever hold {{placeholders}}.
function tm_rep_(body, pattern, repl) { body.replaceText(tm_pat_(pattern), repl); }

// Make a whole table cell hold `text`, keeping the look of its first character.
function tm_setCell_(cell, text) {
  const t = cell.editAsText(), len = t.getText().length;
  t.insertText(0, text);
  if (len > 0) t.deleteText(text.length, text.length + len - 1);
}

// The paragraph that holds `text` (anywhere, tables included), or null.
function tm_paraWith_(body, text) {
  const hit = body.findText(tm_pat_(text));
  if (!hit) return null;
  let el = hit.getElement();
  while (el && el.getType() !== DocumentApp.ElementType.PARAGRAPH && el.getType() !== DocumentApp.ElementType.LIST_ITEM) el = el.getParent();
  return el;
}

// A checkbox line: drop whatever symbol starts the paragraph and put the placeholder there instead.
function tm_check_(body, lineStartsWith, placeholder) {
  const para = tm_paraWith_(body, lineStartsWith);
  if (!para) return false;
  const t = para.editAsText(), idx = t.getText().indexOf(lineStartsWith.split(' ')[0]);
  if (idx > 0) t.deleteText(0, idx - 1);
  t.insertText(0, placeholder + ' ');
  return true;
}

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

// The first table row whose text contains `contains` (spaces and line breaks ignored), or null.
function tm_findRow_(body, contains) {
  const want = tm_norm_(contains), tables = body.getTables();
  for (let t = 0; t < tables.length; t++) {
    for (let r = 0; r < tables[t].getNumRows(); r++) {
      if (tm_norm_(tables[t].getRow(r).getText()).indexOf(want) >= 0) return tables[t].getRow(r);
    }
  }
  return null;
}

// Within a table row (found by text), replace text.
function tm_rowRep_(body, rowContains, pattern, repl) {
  const row = tm_findRow_(body, rowContains);
  if (!row) return false;
  row.replaceText(tm_pat_(pattern), repl);
  return true;
}

function tm_removeRowsContaining_(body, texts) {
  const wants = texts.map(tm_norm_);
  body.getTables().forEach(function (table) {
    for (let r = table.getNumRows() - 1; r >= 0; r--) {
      const txt = tm_norm_(table.getRow(r).getText());
      if (wants.some(function (x) { return txt.indexOf(x) >= 0; })) table.removeRow(r);
    }
  });
}

// ---------------------------------------------------------------------- the Docs ---

function tm_appendixA_(id) {
  const body = DocumentApp.openById(id).getBody();
  tm_rep_(body, 'ELVIE JO ROBIS', '{{traveler_name}}');
  tm_rep_(body, 'Purpose of Travel: .*', 'Purpose of Travel: {{purpose}}');
  // the first sample row stays and becomes the repeating row: one placeholder per column
  const row = tm_findRow_(body, 'September 01, 2026');
  if (row) {
    const cols = ['r_date', 'r_place', 'r_dep', 'r_arr', 'r_mode', 'r_allowance', 'r_perdiem', 'r_total'];
    for (let c = 0; c < Math.min(row.getNumCells(), cols.length); c++) tm_setCell_(row.getCell(c), '{{' + cols[c] + '}}');
  }
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
  tm_check_(body, 'Strictly in accordance', '{{chk_strict}}');
  tm_check_(body, 'Cut short', '{{chk_cut}}');
  tm_check_(body, 'Extended as explained', '{{chk_extended}}');
  tm_check_(body, 'Other deviations', '{{chk_other}}');
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
  tm_rep_(body, 'DPO No\\.? ?2025-7852.*', '{{dpo_ref}}');
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
  pattern = String(pattern).replace(/ /g, '[\\s\\x{00A0}]+');      // a space also matches line breaks and non-breaking spaces
  const finder = sh.createTextFinder(pattern).useRegularExpression(true);
  if (!first) { finder.replaceAllWith(repl); return; }
  const hit = finder.findNext();
  if (hit) hit.createTextFinder(pattern).useRegularExpression(true).replaceAllWith(repl);
}

// The row (1-based) of the first cell whose text matches, or 0.
function tm_sheetRow_(sh, pattern) {
  const hit = sh.createTextFinder(pattern).useRegularExpression(true).findNext();
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
    const cell = sh.createTextFinder('Taxi fare from').useRegularExpression(true).findNext();
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
  tm_sheetRep_(sh, 'in Attendance[\\s\\S]*?2026-5451', 'in attendance to {{activity_title}} as per {{dpo_ref}}', false);
}

// ------------------------------------------------------------- when a template needs a look ---

// Logs how the converted Appendix A table and the Appendix B checkbox lines really look, so a gap can be fixed.
function debugTravelTemplates() {
  const P = PropertiesService.getScriptProperties(), out = [];
  const a = P.getProperty('TPL_appendix_a');
  if (a) {
    DocumentApp.openById(a).getBody().getTables().forEach(function (tb, ti) {
      for (let r = 0; r < tb.getNumRows(); r++) {
        const row = tb.getRow(r), cells = [];
        for (let c = 0; c < row.getNumCells(); c++) cells.push(tm_norm_(row.getCell(c).getText()).slice(0, 28));
        out.push('A table ' + ti + ' row ' + r + ' [' + row.getNumCells() + ']: ' + cells.join(' | '));
      }
    });
  }
  const b = P.getProperty('TPL_appendix_b');
  if (b) {
    DocumentApp.openById(b).getBody().getText().split('\n').forEach(function (line) {
      if (/Strictly|Cut short|Extended|Other deviations|Excess/.test(line)) {
        out.push('B line: ' + JSON.stringify(line.slice(0, 40)) + ' codes ' + line.slice(0, 3).split('').map(function (ch) { return ch.charCodeAt(0); }).join(','));
      }
    });
  }
  const r = P.getProperty('TPL_rer');
  if (r) {
    SpreadsheetApp.openById(r).getSheets()[0].getDataRange().getValues().forEach(function (row, i) {
      row.forEach(function (v, j) { if (/Attendance|5451|\{\{/.test(String(v))) out.push('RER r' + (i + 1) + 'c' + (j + 1) + ': ' + JSON.stringify(String(v).slice(0, 120))); });
    });
  }
  Logger.log('\n' + out.join('\n'));
  return out.join('\n');
}
