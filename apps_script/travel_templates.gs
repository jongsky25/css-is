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

// The "Claims Templates" folder (Cash Advance, Liquidation and Reimbursement sub-folders), the office's current forms.
// Appendix A for a cash advance, and Appendix A and B together for a liquidation and a reimbursement, are made from the
// "Sample [...]" files in it. The mailbox that runs this must be able to open the folder.
const TM_CLAIMS_FOLDER_ID = '1VkxwIB8CxgLzqESbHdeoN4q4eDDTDnTn';

const TM_DOC = 'application/vnd.google-apps.document';
const TM_SHEET = 'application/vnd.google-apps.spreadsheet';

const TM_TEMPLATES = [
  // Appendix A of a cash advance (PERA): the itinerary form alone.
  { key: 'appendix_a', from: 'claims', source: 'Sample [CASH ADVANCE / PERA] .docx', mime: TM_DOC, build: tm_claimCa_,
    expect: ['traveler_name', 'purpose', 'r_date', 'r_place', 'r_dep', 'r_arr', 'r_mode', 'r_allowance', 'r_perdiem',
             'r_total', 'grand_total', 'certifier_name', 'certifier_title', 'prepared_by', 'prepared_title',
             'approver_name', 'approver_title'] },
  // Appendix A and B of a liquidation, one document: the itinerary with its Cash Advance and Reimbursement lines, then the certificate.
  { key: 'claim_liq', from: 'claims', source: 'Sample [LIQUIDATION] .docx', mime: TM_DOC, build: tm_claimLiq_,
    expect: ['traveler_name', 'purpose', 'r_date', 'r_place', 'r_dep', 'r_arr', 'r_mode', 'r_allowance', 'r_perdiem',
             'r_total', 'grand_total', 'certifier_name', 'certifier_title', 'prepared_by', 'prepared_title',
             'approver_name', 'approver_title',
             'ca_amount', 'reimb_amount', 'date', 'head_name', 'head_title', 'station', 'dpo_ref', 'chk_strict', 'chk_cut', 'chk_extended', 'chk_other',
             'refund_amount', 'refund_or_no', 'refund_or_date', 'explanation', 'evidence_list', 'traveler_designation'] },
  // Appendix A and B of a reimbursement, one document ("Expenses Incidental" in the itinerary).
  { key: 'claim_rei', from: 'claims', source: 'Sample [REIMBURSEMENT] .docx', mime: TM_DOC, build: tm_claimRei_,
    expect: ['traveler_name', 'purpose', 'r_date', 'r_place', 'r_dep', 'r_arr', 'r_mode', 'r_allowance', 'r_perdiem',
             'r_total', 'grand_total', 'certifier_name', 'certifier_title', 'prepared_by', 'prepared_title',
             'approver_name', 'approver_title',
             'date', 'head_name', 'head_title', 'station', 'dpo_ref', 'chk_strict', 'chk_cut', 'chk_extended', 'chk_other',
             'refund_amount', 'refund_or_no', 'refund_or_date', 'explanation', 'evidence_list', 'traveler_designation'] },
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
             'ride_mode', 'activity_title', 'dpo_ref'] }
];

// ------------------------------------------------------------------ entry points ---

function makeTravelTemplates() { return tm_make_(null, false); }

// Makes the three claim forms again even when they look good: Appendix A (cash advance), and Appendix A and B for a
// liquidation and for a reimbursement. The older copies stay in _templates.
function rebuildClaimTemplates() { return tm_make_(['appendix_a', 'claim_liq', 'claim_rei'], true); }

function tm_make_(only, force) {
  const P = PropertiesService.getScriptProperties();
  const needOld = TM_TEMPLATES.some(function (t) { return t.from !== 'claims' && (!only || only.indexOf(t.key) >= 0); });
  if (needOld && TM_SOURCE_FOLDER_ID.indexOf('PUT-') === 0) throw new Error('Set TM_SOURCE_FOLDER_ID at the top of this file first.');
  const source = needOld ? DriveApp.getFolderById(TM_SOURCE_FOLDER_ID) : null;
  const claims = DriveApp.getFolderById(TM_CLAIMS_FOLDER_ID);
  const out = tm_outFolder_(P);
  const stamp = Utilities.formatDate(new Date(), 'Asia/Manila', 'MMM d HH:mm');
  const report = [];
  TM_TEMPLATES.forEach(function (t) {
    if (only && only.indexOf(t.key) < 0) return;
    try {
      // A template that is already set and has every placeholder is kept; anything else is (re)made.
      const existing = P.getProperty('TPL_' + t.key);
      if (existing && !force) {
        let gaps = null;
        try { gaps = tm_missing_(existing, t); } catch (e) { gaps = ['(could not open it)']; }
        if (!gaps.length) { report.push(t.key + ': already good, kept'); return; }
      }
      const file = tm_find_(t.from === 'claims' ? claims : source, t.source);
      if (!file) throw new Error('could not find "' + t.source + '" under the ' + (t.from === 'claims' ? 'Claims Templates' : 'source') + ' folder');
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

// The claim forms. Each is made from the office's own filled-in sample: its text becomes {{placeholders}}, its first itinerary row
// becomes the row the app repeats and the other sample rows are removed. Replacements are made in this order on purpose: first
// the ones that belong to one table row (Prepared by, Approved by), then the ones that would also match elsewhere.

// The itinerary table, shared by the three forms. `firstRow` is text in the row kept as the repeating row; `others` are
// text in the rows to remove; `n` holds the sample strings of this form.
function tm_itinerary_(body, firstRow, others, n) {
  tm_rep_(body, 'Purpose of Travel: .*', 'Purpose of Travel: {{purpose}}');
  const row = tm_findRow_(body, firstRow);
  if (row) {
    const cols = ['r_date', 'r_place', 'r_dep', 'r_arr', 'r_mode', 'r_allowance', 'r_perdiem', 'r_total'];
    for (let c = 0; c < Math.min(row.getNumCells(), cols.length); c++) tm_setCell_(row.getCell(c), '{{' + cols[c] + '}}');
  }
  tm_removeRowsContaining_(body, others);
  tm_rowRep_(body, 'Total:', n.total, '{{grand_total}}');
  tm_rowRep_(body, 'Prepared by', n.person, '{{prepared_by}}');
  tm_rowRep_(body, 'Prepared by', n.designation, '{{prepared_title}}');
  tm_rowRep_(body, 'Approved by:', 'JUAN ALFONSO PEREZ IV, MD, MBA, MPM', '{{approver_name}}');
  tm_rowRep_(body, 'Approved by:', 'OIC-Director IV, BLHSD', '{{approver_title}}');
  tm_rep_(body, n.certifier, '{{certifier_name}}');
  tm_rep_(body, n.certifierTitle, '{{certifier_title}}');
  tm_rep_(body, n.person, '{{traveler_name}}');
}

// The certificate (Appendix B) that follows the itinerary in a liquidation and a reimbursement.
//   `approvedInRow`: the "APPROVED:" block is a table cell (liquidation) rather than loose paragraphs (reimbursement).
function tm_certificate_(body, n, approvedInRow) {
  if (approvedInRow) {
    tm_rowRep_(body, 'APPROVED:', 'JUAN ALFONSO PEREZ IV, MD, MBA, MPM', '{{approver_name}}');
    tm_rowRep_(body, 'APPROVED:', 'OIC-Director IV, BLHSD', '{{approver_title}}');
  } else {
    tm_afterPara_(body, 'APPROVED:', ['{{approver_name}}', '{{approver_title}}']);
  }
  tm_rep_(body, 'JUAN ALFONSO PEREZ IV, MD, MBA, MPM', '{{head_name}}');
  tm_rep_(body, 'BLHSD-DOH', '{{station}}');
  tm_rep_(body, 'Director IV', '{{head_title}}');
  tm_rep_(body, n.certDate, '{{date}}');
  tm_check_(body, 'Strictly in accordance', '{{chk_strict}}');
  tm_check_(body, 'Cut short', '{{chk_cut}}');
  tm_check_(body, 'Extended as explained', '{{chk_extended}}');
  tm_check_(body, 'Other deviations', '{{chk_other}}');
  tm_rep_(body, 'Excess payment in the amount of', 'Excess payment in the amount of {{refund_amount}}');
  tm_rep_(body, 'O\\.R\\. No\\. _+ dated _+', 'O.R. No. {{refund_or_no}} dated {{refund_or_date}}');
  if (n.evidenceFirst) {                                   // the liquidation sample lists the evidence, then the justification
    tm_section_(body, 'Evidence of Travel attached hereto', 'Justification:', '{{evidence_list}}', { exact: false });
    tm_section_(body, 'Justification:', null, '{{explanation}}', { exact: false });
  } else {
    tm_section_(body, 'Explanation or Justification', 'Evidence of Travel attached hereto', '{{explanation}}', { exact: false });
    tm_section_(body, 'Evidence of Travel attached hereto', 'Respectfully submitted', '{{evidence_list}}', { exact: false });
  }
  tm_rep_(body, n.dpoRef, '{{dpo_ref}}');
  tm_rep_(body, n.designation, '{{traveler_designation}}');
}

// Sets the next non-empty paragraphs after the paragraph that reads `heading` (used where a block is loose paragraphs).
function tm_afterPara_(body, heading, placeholders) {
  const n = body.getNumChildren(), want = tm_norm_(heading);
  let start = -1;
  for (let i = 0; i < n && start < 0; i++) {
    const el = body.getChild(i);
    if (el.getType() === DocumentApp.ElementType.PARAGRAPH && tm_norm_(el.asParagraph().getText()) === want) start = i;
  }
  if (start < 0) return false;
  let k = 0;
  for (let i = start + 1; i < n && k < placeholders.length; i++) {
    const el = body.getChild(i);
    if (el.getType() !== DocumentApp.ElementType.PARAGRAPH || !tm_norm_(el.asParagraph().getText())) continue;
    el.asParagraph().setText(placeholders[k++]);
  }
  return k === placeholders.length;
}

// Appendix A of a cash advance (PERA).
function tm_claimCa_(id) {
  const body = DocumentApp.openById(id).getBody();
  tm_itinerary_(body, 'August 3, 2026', ['NAIA Terminal 3 to Virac Airport', 'August 4-6, 2026', 'August 7, 2026',
                'NAIA Terminal 3 to Residence', 'August 10, 2026', 'NAIA Terminal 2 to Bancasi Airport',
                'August 11-13, 2026', 'August 14, 2026', 'NAIA Terminal 2 to Residence'],
                { total: '26,414\\.4', person: 'VLANCHE APRIL DULFO', designation: 'Medical Officer III',
                  certifier: 'MARIA LOURDES GAJITOS, MD', certifierTitle: 'Medical Officer V' });
}

// Appendix A and B of a liquidation, with the Cash Advance and Reimbursement lines.
function tm_claimLiq_(id) {
  const body = DocumentApp.openById(id).getBody();
  tm_itinerary_(body, 'August 3, 2026', ['NAIA Terminal 3 to Virac Airport', 'August 4-6, 2026', 'August 7, 2026',
                'NAIA Terminal 3 to Residence', 'August 10, 2026', 'NAIA Terminal 2 to Bancasi Airport',
                'August 11-13, 2026', 'August 14, 2026', 'NAIA Terminal 2 to Residence'],
                { total: '39,417\\.4', person: 'VLANCHE APRIL DULFO', designation: 'Medical Officer III',
                  certifier: 'MARIA LOURDES GAJITOS, MD', certifierTitle: 'Medical Officer V' });
  tm_rowRep_(body, 'Cash Advance:', '25,714\\.4', '{{ca_amount}}');
  tm_rowRep_(body, 'Reimbursement:', '13,703', '{{reimb_amount}}');
  tm_certificate_(body, { certDate: 'August 17, 2026', evidenceFirst: true, designation: 'Medical Officer III',
                          dpoRef: 'DPO No\\.\\s?2026-4835 dated July 17, 2026, and DPO No\\.\\s?2026-5023 dated July 24, 2026, respectively' }, true);
}

// Appendix A and B of a reimbursement.
function tm_claimRei_(id) {
  const body = DocumentApp.openById(id).getBody();
  tm_itinerary_(body, 'September 28, 2026', ['NAIA Terminal 2 to Iloilo International Airport',
                'Iloilo International Airport to Zuri Hotel', 'October 1, 2026', 'Iloilo International Airport to NAIA Terminal 2',
                'NAIA Terminal 2 to Residence'],
                { total: '12,971', person: 'VLANCHE APRIL DULFO', designation: 'Medical Officer III',
                  certifier: 'MARIA LOURDES B\\. GAJITOS, MD', certifierTitle: 'Medical Officer V-BLHSD' });
  tm_certificate_(body, { certDate: 'October 6, 2026', evidenceFirst: false, designation: 'Medical Officer III',
                          dpoRef: 'DPO No\\.\\s?2026-6168 dated September 10, 2026' }, false);
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
  // Spot feedback #203, to follow General Form No. 2 (Revised January 1992): "in the amount of", the kind of transport
  // in the fare line, and the form's own instruction about rentals and transportation.
  tm_sheetRep_(sh, '(?:the amount )?of _{3,}', 'the amount of {{amount_words}}', false);
  tm_sheetRep_(sh, '\\(P_{3,}\\)', '(P{{amount_figures}})', false);
  tm_sheetRep_(sh, '(?:Taxi )?fare from _+', '{{ride_mode}} fare from {{ride_from}} to {{ride_to}}', false);
  tm_sheetRep_(sh, '\\bon _{3,}', 'on {{ride_date}}', false);
  tm_sheetRep_(sh, 'in Attendance[\\s\\S]*?2026-5451', 'in attendance to {{activity_title}} as per {{dpo_ref}}', false);
  tm_rerInstruction_(sh);
}

const TM_RER_INSTRUCTION = 'Rental or transportation should show inclusive dates, purpose, distance, inclusive points of travel, etc.';

// Puts the form's instruction under the payment lines unless the sheet already carries it.
function tm_rerInstruction_(sh) {
  if (sh.createTextFinder('inclusive points of travel').findNext()) return;
  const hit = sh.createTextFinder('{{ride_from}}').findNext();
  if (!hit) return;
  const v = String(hit.getValue());
  hit.setValue(v + '\n\n' + TM_RER_INSTRUCTION);
  hit.setWrap(true);
}

// Makes the RER again from its source even when it looks good (after a change to tm_rer_).
function rebuildRerTemplate() { return tm_make_(['rer'], true); }

// ------------------------------------------------------------- when a template needs a look ---

// Logs how the converted claim forms' itinerary tables and checkbox lines really look, so a gap can be fixed.
function debugTravelTemplates() {
  const P = PropertiesService.getScriptProperties(), out = [];
  ['appendix_a', 'claim_liq', 'claim_rei'].forEach(function (key) {
  const a = P.getProperty('TPL_' + key);
  if (a) {
    DocumentApp.openById(a).getBody().getTables().forEach(function (tb, ti) {
      for (let r = 0; r < tb.getNumRows(); r++) {
        const row = tb.getRow(r), cells = [];
        for (let c = 0; c < row.getNumCells(); c++) cells.push(tm_norm_(row.getCell(c).getText()).slice(0, 28));
        out.push(key + ' table ' + ti + ' row ' + r + ' [' + row.getNumCells() + ']: ' + cells.join(' | '));
      }
    });
    DocumentApp.openById(a).getBody().getText().split('\n').forEach(function (line) {
      if (/Strictly|Cut short|Extended|Other deviations|Excess/.test(line)) {
        out.push(key + ' line: ' + JSON.stringify(line.slice(0, 40)) + ' codes ' + line.slice(0, 3).split('').map(function (ch) { return ch.charCodeAt(0); }).join(','));
      }
    });
  }
  });
  const r = P.getProperty('TPL_rer');
  if (r) {
    SpreadsheetApp.openById(r).getSheets()[0].getDataRange().getValues().forEach(function (row, i) {
      row.forEach(function (v, j) { if (/Attendance|5451|\{\{/.test(String(v))) out.push('RER r' + (i + 1) + 'c' + (j + 1) + ': ' + JSON.stringify(String(v).slice(0, 120))); });
    });
  }
  Logger.log('\n' + out.join('\n'));
  return out.join('\n');
}
