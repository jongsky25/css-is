// Office Connect: one-time activity template maker (DPO and invitation).
//
// Add this file to the SAME Apps Script project as travel_docs.gs (File > New > Script). Unlike the travel
// forms, these two documents are built here from scratch, so no source folder is needed. Run
// makeActivityTemplates() once: it creates a Google Doc for each, saves its id as the TPL_dpo and
// TPL_invitation Script Properties the relay reads, and logs every placeholder that did not land.
// checkActivityTemplates() re-checks the ones already set. Run it as the office mailbox, the same account that
// runs the travel relay. The templates are put in the "_templates" folder inside ROOT_FOLDER_ID.
//
// You can restyle a template afterwards in Google Docs. Keep every {{placeholder}} it lists: the app fills
// them, and a placeholder you remove is simply left empty on the draft.
//   {{details}} and {{personnel}} are blocks: the app replaces that whole line with several lines.

// Optional: the Drive file ids of the DOH seal and the Bagong Pilipinas logo. When set, the DPO letterhead is built with
// them. When blank the letterhead is plain text; add the two logos by hand in Google Docs once and every draft keeps them.
const AT_LOGO_LEFT_ID = '';
const AT_LOGO_RIGHT_ID = '';
const AT_FOOTER_LINES = [
  'Building 1, San Lazaro Compound, Rizal Avenue, Sta. Cruz, 1003 Manila \u2022 Trunk Line 651-7800 local 1113, 1108, 1135',
  'Direct Line: 711-9502; 711-9503 Fax: 743-1829 \u2022 URL: http://www.doh.gov.ph; e-mail: dohosec@doh.gov.ph'
];

const AT_TEMPLATES = [
  { key: 'dpo', title: 'Template - dpo', build: at_buildDpo_,
    expect: ['dpo_year', 'dpo_no', 'dpo_date', 'subject', 'background', 'intro', 'funding_source', 'p_name', 'p_position',
             'head_name', 'head_title', 'unit_name'] },
  { key: 'invitation', title: 'Template - invitation (memorandum)', build: at_buildInvitation_,
    expect: ['date', 'for_name', 'for_title', 'for_office', 'from_name', 'from_title', 'unit_name', 'subject', 'opening',
             'details', 'a_area', 'a_request', 'contact_name', 'contact_email', 'contact_phone'] }
];

function makeActivityTemplates() {
  const P = PropertiesService.getScriptProperties();
  const root = DriveApp.getFolderById(P.getProperty('ROOT_FOLDER_ID'));
  const it = root.getFoldersByName('_templates');
  const out = it.hasNext() ? it.next() : root.createFolder('_templates');
  const stamp = Utilities.formatDate(new Date(), 'Asia/Manila', 'MMM d HH:mm');
  const report = [];
  AT_TEMPLATES.forEach(function (t) {
    try {
      const existing = P.getProperty('TPL_' + t.key);
      if (existing) {
        let gaps = null;
        try { gaps = at_missing_(existing, t); } catch (e) { gaps = ['(could not open it)']; }
        if (!gaps.length) { report.push(t.key + ': already good, kept'); return; }
      }
      const doc = DocumentApp.create(t.title + ' (' + stamp + ')');
      const id = doc.getId();
      t.build(doc.getBody(), doc);
      doc.saveAndClose();
      DriveApp.getFileById(id).moveTo(out);
      P.setProperty('TPL_' + t.key, id);
      const missing = at_missing_(id, t);
      report.push(t.key + ': ' + (missing.length ? 'MISSING ' + missing.join(', ') : 'all placeholders present')
                  + '  https://drive.google.com/open?id=' + id);
    } catch (e) {
      report.push(t.key + ': FAILED - ' + e.message);
    }
  });
  Logger.log('\n' + report.join('\n'));
  return report.join('\n');
}

function checkActivityTemplates() {
  const P = PropertiesService.getScriptProperties(), report = [];
  AT_TEMPLATES.forEach(function (t) {
    const id = P.getProperty('TPL_' + t.key);
    if (!id) { report.push(t.key + ': not set'); return; }
    try {
      const gaps = at_missing_(id, t);
      report.push(t.key + ': ' + (gaps.length ? 'MISSING ' + gaps.join(', ') : 'all placeholders present'));
    } catch (e) { report.push(t.key + ': could not open it - ' + e.message); }
  });
  Logger.log('\n' + report.join('\n'));
  return report.join('\n');
}

function at_missing_(id, t) {
  const text = DocumentApp.openById(id).getBody().getText();
  return t.expect.filter(function (k) { return text.indexOf('{{' + k + '}}') < 0; });
}

// The DOH Department Personnel Order layout: letterhead, date, DPO number, subject, background, authority line, a Name /
// Position table, funding and accounting paragraphs, the signatory and the DOH address footer.
//   {{p_name}} and {{p_position}} sit in ONE table row: the app copies that row once per person.
function at_letterhead_(body) {
  const names = ['Republic of the Philippines', 'DEPARTMENT OF HEALTH', 'Office of the Secretary'];
  function fill(container, first) {
    names.forEach(function (n, i) {
      const p = (i === 0 && first) ? first : container.appendParagraph('');
      p.setText(n);
      p.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
      p.setBold(i === 1);
      p.setItalic(i === 2);
    });
  }
  if (!AT_LOGO_LEFT_ID && !AT_LOGO_RIGHT_ID) { fill(body, null); return; }
  const table = body.appendTable([['', '', '']]);
  table.setBorderWidth(0);
  [[0, AT_LOGO_LEFT_ID], [2, AT_LOGO_RIGHT_ID]].forEach(function (x) {
    if (!x[1]) return;
    const img = table.getCell(0, x[0]).getChild(0).asParagraph().appendInlineImage(DriveApp.getFileById(x[1]).getBlob());
    img.setWidth(70);
    img.setHeight(70);
  });
  const mid = table.getCell(0, 1);
  fill(mid, mid.getChild(0).asParagraph());
}

function at_buildDpo_(body, doc) {
  at_letterhead_(body);
  body.appendParagraph('{{dpo_date}}').setAlignment(DocumentApp.HorizontalAlignment.RIGHT);
  body.appendParagraph('DEPARTMENT PERSONNEL ORDER').setBold(true);
  body.appendParagraph('No. {{dpo_year}} - {{dpo_no}}');
  const subject = body.appendParagraph('SUBJECT: {{subject}}');
  const subjectText = subject.editAsText();
  subjectText.setBold(true);
  subjectText.setUnderline(9, subjectText.getText().length - 1, true);
  [
    '{{background}}',
    '{{intro}}'
  ].forEach(function (t) {
    const p = body.appendParagraph(t);
    p.setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
    p.setIndentFirstLine(36);
  });
  const table = body.appendTable([['Name', 'Position'], ['{{p_name}}', '{{p_position}}']]);
  table.setBorderWidth(0);
  table.getRow(0).editAsText().setBold(true);
  [0, 1].forEach(function (r) {
    table.getCell(r, 1).getChild(0).asParagraph().setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  });
  table.getCell(0, 0).getChild(0).asParagraph().setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  [
    'Under this Order, traveling expenses such as plane fare, per diem, TNVs (e.g. grab, InDrive), bus, boat, taxi, and other allowable incidental expenses relative to the conduct of the activity of the abovementioned staff shall be charged against the {{funding_source}} funds.',
    'All expenses are subject to the usual accounting and auditing rules and regulations.'
  ].forEach(function (t) {
    const p = body.appendParagraph(t);
    p.setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
    p.setIndentFirstLine(36);
  });
  body.appendParagraph('By Authority of the Secretary of Health:').setIndentStart(216);
  body.appendParagraph('');
  body.appendParagraph('');
  body.appendParagraph('{{head_name}}').setBold(true).setIndentStart(216);
  body.appendParagraph('{{head_title}}').setIndentStart(216);
  body.appendParagraph('{{unit_name}}').setIndentStart(216);
  body.editAsText().setFontFamily('Times New Roman');
  body.editAsText().setFontSize(12);
  const footer = doc.addFooter();
  footer.setText(AT_FOOTER_LINES[0]);
  footer.appendParagraph(AT_FOOTER_LINES[1]);
  footer.getParagraphs().forEach(function (p) {
    p.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  });
  footer.editAsText().setFontFamily('Times New Roman');
  footer.editAsText().setFontSize(8);
  const first = body.getChild(0);
  if (first.getType() === DocumentApp.ElementType.PARAGRAPH && first.asParagraph().getText() === '') body.removeChild(first);
}

// The DOH memorandum to a regional office (the "Memo to Regions (Invitation)" format): date, MEMORANDUM, FOR / FROM /
// SUBJECT, the request, the what / when / where lines, a table of the help asked for, the contact line and an initials block.
//   {{details}} is a block (the app replaces that line with several); {{a_area}} and {{a_request}} sit in ONE table row.
function at_buildInvitation_(body, doc) {
  body.appendParagraph('{{date}}');
  const title = body.appendParagraph('MEMORANDUM');
  title.setBold(true);
  title.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  [
    ['FOR:\t{{for_name}}', '{{for_title}}', '{{for_office}}'],
    ['FROM:\t{{from_name}}', '{{from_title}}', '{{unit_name}}']
  ].forEach(function (group) {
    group.forEach(function (line, i) {
      const p = body.appendParagraph(line);
      if (i === 0) p.setBold(true);
      if (i > 0) p.setIndentStart(36);
    });
  });
  body.appendParagraph('SUBJECT:\t{{subject}}').setBold(true);
  body.appendHorizontalRule();
  [
    '{{opening}}',
    '{{details}}',
    'In this regard, we kindly request your office\u2019s assistance in facilitating the activity through the following:'
  ].forEach(function (t) {
    const p = body.appendParagraph(t);
    p.setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
  });
  const table = body.appendTable([['Area', 'Requested Assistance'], ['{{a_area}}', '{{a_request}}']]);
  table.getRow(0).editAsText().setBold(true);
  [
    'For clarifications, your staff may contact {{contact_name}} at {{contact_email}}, or you may reach us via telephone: {{contact_phone}}.',
    'We sincerely appreciate your support in facilitating the successful conduct of this activity.',
    'Thank you very much for your continued support.'
  ].forEach(function (t) {
    const p = body.appendParagraph(t);
    p.setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
  });
  body.appendParagraph('');
  const initials = body.appendTable([['', '{{unit_name}}'], ['Initials', ''], ['Date', '']]);
  initials.getRow(0).editAsText().setBold(true);
  body.editAsText().setFontFamily('Times New Roman');
  body.editAsText().setFontSize(12);
  const first = body.getChild(0);
  if (first.getType() === DocumentApp.ElementType.PARAGRAPH && first.asParagraph().getText() === '') body.removeChild(first);
}
