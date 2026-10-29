// Office Connect: legacy activity body builders and drawn-template maker.
// The office maker reuses the DPO/minutes bodies with officeFrame=true inside a copied memo Blank.
// Ordinary two-argument builder calls retain the drawn header/footer for legacy setup and rollback.
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

// The DOH seal and the Bagong Pilipinas logo come from activity_logos.gs (add that file to this project too). To use other
// pictures, put their Drive file ids here: an id wins over the embedded picture. With neither, the letterhead is plain text.
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
             'details', 'a_area', 'a_request', 'contact_name', 'contact_email', 'contact_phone'] },
  { key: 'concept_note', title: 'Template - concept note', build: at_buildConceptNote_,
    expect: ['title', 'background', 'objectives', 'outputs', 'participants', 'participant_count', 'methodology', 'date_duration',
             'venue', 'facilitators', 'budget', 'pd_day', 'pd_am', 'pd_pm', 'prepared_by', 'prepared_title', 'noted_by_name',
             'noted_by_title', 'recommended_name', 'recommended_title', 'unit_name'] },
  { key: 'program_flow', title: 'Template - program flow', build: at_buildProgramFlow_,
    expect: ['title', 'pf_time', 'pf_topic', 'pf_person'] },
  { key: 'notice_of_meeting', title: 'Template - notice of meeting', build: at_buildNotice_,
    expect: ['date', 'title', 'meeting_when', 'venue', 'invited', 'agenda', 'prepared_by', 'prepared_title', 'head_name',
             'head_title', 'unit_name'] },
  { key: 'minutes', title: 'Template - minutes of the meeting', build: at_buildMinutes_,
    expect: ['title', 'meeting_when', 'venue', 'attendees', 'agenda', 'discussion', 'm_action', 'm_who', 'm_due', 'next_steps',
             'prepared_by', 'prepared_title', 'approved_by', 'unit_name'] }
];

// Rebuilds drawn templates even when they are already good, for a new letterhead or logos.
// Office-managed templates are kept; rebuild them with their scoped office-maker function. TPL_<key> then points to the
// new Docs; the old ones stay in "_templates".
function rebuildActivityTemplates() {
  return makeActivityTemplates(true);
}

function makeActivityTemplates(force) {
  const P = PropertiesService.getScriptProperties();
  const root = DriveApp.getFolderById(P.getProperty('ROOT_FOLDER_ID'));
  const it = root.getFoldersByName('_templates');
  const out = it.hasNext() ? it.next() : root.createFolder('_templates');
  const stamp = Utilities.formatDate(new Date(), 'Asia/Manila', 'MMM d HH:mm');
  const report = [];
  AT_TEMPLATES.forEach(function (t) {
    try {
      const existing = P.getProperty('TPL_' + t.key);
      if (existing && P.getProperty('TPLF_' + t.key) === existing) {
        report.push(t.key + ': office template kept; use makeOfficeTemplates to rebuild'); return;
      }
      if (existing && !force) {
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
    if (P.getProperty('TPLF_' + t.key) === id) {
      report.push(t.key + ': office template; use checkOfficeTemplates'); return;
    }
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

// DPO/minutes accept officeFrame=true when the office maker already copied their header/footer and page setup.
// The DOH Department Personnel Order layout: letterhead, date, DPO number, subject, background, authority line, a Name /
// Position table, funding and accounting paragraphs, the signatory and the DOH address footer.
//   {{p_name}} and {{p_position}} sit in ONE table row: the app copies that row once per person.
function at_logo_(side) {
  const id = side === 0 ? AT_LOGO_LEFT_ID : AT_LOGO_RIGHT_ID;
  if (id) return { blob: DriveApp.getFileById(id).getBlob(), size: [1, 1] };
  const b64 = side === 0 ? (typeof AT_LOGO_LEFT_B64 !== 'undefined' ? AT_LOGO_LEFT_B64 : '')
                         : (typeof AT_LOGO_RIGHT_B64 !== 'undefined' ? AT_LOGO_RIGHT_B64 : '');
  if (!b64) return null;
  const size = side === 0 ? AT_LOGO_LEFT_SIZE : AT_LOGO_RIGHT_SIZE;
  return { blob: Utilities.newBlob(Utilities.base64Decode(b64), 'image/png', side === 0 ? 'doh-seal.png' : 'bagong-pilipinas.png'),
           size: size };
}

// The letterhead every DOH document starts with: the seal, "Republic of the Philippines / DEPARTMENT OF HEALTH / Office of
// the Secretary" and the Bagong Pilipinas logo. It is built into the document's real header (spot feedback #157), so it
// repeats on every page and stays out of the body text. Pictures are 90 pt tall, larger than the 11 pt text beside them (spot feedback #163) with their own proportions.
function at_letterhead_(body) {
  const names = ['Republic of the Philippines', 'DEPARTMENT OF HEALTH', 'Office of the Secretary'];
  function fill(container, first) {
    names.forEach(function (n, i) {
      const p = (i === 0 && first) ? first : container.appendParagraph('');
      p.setText(n);
      p.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
      p.setBold(i === 1);
      p.setItalic(i === 2);
      p.setFontSize(11);
    });
  }
  const logos = [at_logo_(0), at_logo_(2)];
  if (!logos[0] && !logos[1]) { fill(body, null); return; }
  const table = body.appendTable([['', '', '']]);
  table.setBorderWidth(0);
  // Fixed widths that add up to the 468 pt between the margins; the Docs default is three equal columns, which wraps the
  // title and can push the right-hand logo off the page.
  [100, 268, 100].forEach(function (w, c) { table.setColumnWidth(c, w); });
  [0, 2].forEach(function (col, i) {
    const logo = logos[i];
    if (!logo) return;
    const cell = table.getCell(0, col);
    const para = cell.getChild(0).asParagraph();
    para.setAlignment(col === 0 ? DocumentApp.HorizontalAlignment.LEFT : DocumentApp.HorizontalAlignment.RIGHT);
    const img = para.appendInlineImage(logo.blob);
    // keep the picture's own proportions: the size read from the inserted image wins over the stated one
    const w = img.getWidth(), h = img.getHeight();
    const ratio = (typeof w === 'number' && typeof h === 'number' && w > 0 && h > 0) ? w / h : logo.size[0] / logo.size[1];
    img.setHeight(90);
    img.setWidth(Math.round(90 * ratio));
  });
  const mid = table.getCell(0, 1);
  fill(mid, mid.getChild(0).asParagraph());
  at_dropLeadingBlank_(body);
}

// A new header starts with one empty paragraph that would sit above the letterhead. Deleting it is not safe: Docs accepts
// the removal when it is made, then refuses to save the document ("Service Documents failed while accessing document"),
// and a try/catch cannot see that. So the blank line is shrunk to nothing instead, which looks the same.
function at_dropLeadingBlank_(container) {
  try {
    if (typeof container.getNumChildren !== 'function' || container.getNumChildren() < 2) return;
    const first = container.getChild(0);
    if (first.getType() !== DocumentApp.ElementType.PARAGRAPH || first.asParagraph().getText() !== '') return;
    first.asParagraph().setFontSize(1).setLineSpacing(1).setSpacingBefore(0).setSpacingAfter(0);
  } catch (e) { /* cosmetic only */ }
}

// Docs copies the formatting of the paragraph above onto a new one, so one bold line made every line after it bold
// (spot feedback #154). Each paragraph and table starts plain; the builders then bold only what is meant to be bold.
function at_add_(body, text) {
  const p = body.appendParagraph(text);
  p.setBold(false); p.setItalic(false); p.setUnderline(false);
  return p;
}

function at_table_(body, cells) {
  const table = body.appendTable(cells);
  table.editAsText().setBold(false);
  return table;
}

// The DOH address block at the foot of every page.
function at_footer_(doc) {
  const footer = doc.addFooter();
  footer.setText(AT_FOOTER_LINES[0]);
  footer.appendParagraph(AT_FOOTER_LINES[1]);
  footer.getParagraphs().forEach(function (p) {
    p.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  });
  footer.editAsText().setFontFamily('Times New Roman');
  footer.editAsText().setFontSize(8);
}

// DPO layout, in points, measured from the sample the office supplied (spot feedback #170); the text is 468 pt wide.
var AT_DPO_TITLE_INDENT = 0;         // "DEPARTMENT PERSONNEL ORDER" and its number: flush left, like the lines of the first paragraph (spot feedback #180)
var AT_DPO_SUBJECT_LABEL = 36;       // where "SUBJECT:" starts
var AT_DPO_SUBJECT_TEXT = 108;       // where the subject text starts; its wrapped lines line up under it
var AT_DPO_BODY_FIRST_LINE = 36;     // first line of each body paragraph
var AT_DPO_SIGNATORY_INDENT = 144;   // "By Authority of the Secretary of Health:" and the signatory block: the 2-inch mark (spot feedback #182)
var AT_DPO_SPACE_AFTER = 12;         // points of space after each paragraph

function at_buildDpo_(body, doc, officeFrame) {
  if (!officeFrame) at_letterhead_(doc.addHeader());
  // A space after the subject and after every paragraph (spot feedback #170).
  const add = function (text) { return at_add_(body, text).setSpacingAfter(AT_DPO_SPACE_AFTER); };
  add('{{dpo_date}}').setAlignment(DocumentApp.HorizontalAlignment.RIGHT);
  // no space between the title and its number (spot feedback #180)
  add('DEPARTMENT PERSONNEL ORDER').setBold(true).setIndentStart(AT_DPO_TITLE_INDENT).setIndentFirstLine(AT_DPO_TITLE_INDENT).setSpacingAfter(0);
  add('No. {{dpo_year}} - {{dpo_no}}').setIndentStart(AT_DPO_TITLE_INDENT).setIndentFirstLine(AT_DPO_TITLE_INDENT);
  // "SUBJECT:" then a tab to the subject text, which is bold, underlined and justified; its wrapped lines line up under
  // the text, not under the label.
  const subject = add('SUBJECT:\t{{subject}}');
  const subjectText = subject.editAsText();
  subjectText.setBold(true);
  subjectText.setUnderline(9, subjectText.getText().length - 1, true);
  subject.setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
  subject.setIndentStart(AT_DPO_SUBJECT_TEXT).setIndentFirstLine(AT_DPO_SUBJECT_LABEL);
  [
    '{{background}}',
    '{{intro}}'
  ].forEach(function (t) {
    const p = add(t);
    p.setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
    p.setIndentFirstLine(AT_DPO_BODY_FIRST_LINE);
  });
  const table = at_table_(body, [['Name', 'Designation'], ['{{p_name}}', '{{p_position}}']]);
  table.setBorderWidth(0);
  [234, 234].forEach(function (w, c) { table.setColumnWidth(c, w); });
  table.getRow(0).editAsText().setBold(true);
  [0, 1].forEach(function (r) {
    table.getCell(r, 1).getChild(0).asParagraph().setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  });
  table.getCell(0, 0).getChild(0).asParagraph().setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  [
    'Under this Order, traveling expenses such as plane fare, per diem, TNVs (e.g. grab, InDrive), bus, boat, taxi, and other allowable incidental expenses relative to the conduct of the activity of the abovementioned staff shall be charged against the {{funding_source}} funds.',
    'All expenses are subject to the usual accounting and auditing rules and regulations.'
  ].forEach(function (t) {
    const p = add(t);
    p.setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
    p.setIndentFirstLine(AT_DPO_BODY_FIRST_LINE);
  });
  add('By Authority of the Secretary of Health:').setIndentStart(AT_DPO_SIGNATORY_INDENT).setIndentFirstLine(AT_DPO_SIGNATORY_INDENT);
  add('');
  add('');
  // the first-line indent is set too: with only the start indent, a one-line paragraph begins at the left margin (spot feedback #182)
  // the signatory's name, title and unit sit on consecutive lines with no space between them (spot feedback #183)
  add('{{head_name}}').setBold(true).setIndentStart(AT_DPO_SIGNATORY_INDENT).setIndentFirstLine(AT_DPO_SIGNATORY_INDENT).setSpacingAfter(0);
  add('{{head_title}}').setIndentStart(AT_DPO_SIGNATORY_INDENT).setIndentFirstLine(AT_DPO_SIGNATORY_INDENT).setSpacingAfter(0);
  add('{{unit_name}}').setIndentStart(AT_DPO_SIGNATORY_INDENT).setIndentFirstLine(AT_DPO_SIGNATORY_INDENT);
  body.editAsText().setFontFamily('Times New Roman');
  body.editAsText().setFontSize(12);
  if (!officeFrame) at_footer_(doc);
  const first = body.getChild(0);
  if (first.getType() === DocumentApp.ElementType.PARAGRAPH && first.asParagraph().getText() === '') body.removeChild(first);
}

// The DOH memorandum to a regional office (the "Memo to Regions (Invitation)" format): date, MEMORANDUM, FOR / FROM /
// SUBJECT, the request, the what / when / where lines, a table of the help asked for, the contact line and an initials block.
//   {{details}} is a block (the app replaces that line with several); {{a_area}} and {{a_request}} sit in ONE table row.
function at_buildInvitation_(body, doc) {
  at_letterhead_(doc.addHeader());
  at_add_(body, '{{date}}');
  const title = at_add_(body, 'MEMORANDUM');
  title.setBold(true);
  title.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  [
    ['FOR:\t{{for_name}}', '{{for_title}}', '{{for_office}}'],
    ['FROM:\t{{from_name}}', '{{from_title}}', '{{unit_name}}']
  ].forEach(function (group) {
    group.forEach(function (line, i) {
      const p = at_add_(body, line);
      if (i === 0) p.setBold(true);
      if (i > 0) p.setIndentStart(36);
    });
  });
  at_add_(body, 'SUBJECT:\t{{subject}}').setBold(true);
  body.appendHorizontalRule();
  [
    '{{opening}}',
    '{{details}}',
    'In this regard, we kindly request your office\u2019s assistance in facilitating the activity through the following:'
  ].forEach(function (t) {
    const p = at_add_(body, t);
    p.setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
  });
  const table = at_table_(body, [['Area', 'Requested Assistance'], ['{{a_area}}', '{{a_request}}']]);
  table.getRow(0).editAsText().setBold(true);
  [
    'For clarifications, your staff may contact {{contact_name}} at {{contact_email}}, or you may reach us via telephone: {{contact_phone}}.',
    'We sincerely appreciate your support in facilitating the successful conduct of this activity.',
    'Thank you very much for your continued support.'
  ].forEach(function (t) {
    const p = at_add_(body, t);
    p.setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
  });
  at_add_(body, '');
  const initials = at_table_(body, [['', '{{unit_name}}'], ['Initials', ''], ['Date', '']]);
  initials.getRow(0).editAsText().setBold(true);
  body.editAsText().setFontFamily('Times New Roman');
  body.editAsText().setFontSize(12);
  at_footer_(doc);
  const first = body.getChild(0);
  if (first.getType() === DocumentApp.ElementType.PARAGRAPH && first.asParagraph().getText() === '') body.removeChild(first);
}

// The DOH concept note: numbered sections, an Operational Details table, the program of activities (one row per day),
// and the Prepared by / Noted by / Recommended by block.
//   {{background}} {{objectives}} {{outputs}} {{participants}} {{methodology}} are blocks (a prompt or lines the app writes).
//   {{pd_day}} {{pd_am}} {{pd_pm}} sit in ONE table row: the app copies that row once per day.
function at_buildConceptNote_(body, doc) {
  at_letterhead_(doc.addHeader());
  const heading = at_add_(body, 'CONCEPT NOTE');
  heading.setBold(true);
  heading.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  const title = at_add_(body, '{{title}}');
  title.setBold(true);
  title.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  [
    ['1.  Background and Rationale', ['{{background}}']],
    ['2.  Objectives', ['{{objectives}}']],
    ['3.  Expected Outputs', ['{{outputs}}']],
    ['4.  Participants', ['{{participants}}', 'Estimated total: {{participant_count}}']],
    ['5.  Methodology', ['{{methodology}}']]
  ].forEach(function (section) {
    at_add_(body, section[0]).setBold(true);
    section[1].forEach(function (line) {
      at_add_(body, line).setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
    });
  });
  at_add_(body, '6.  Operational Details').setBold(true);
  const details = at_table_(body, [
    ['Title', '{{title}}'], ['Date/Duration', '{{date_duration}}'], ['Venue', '{{venue}}'],
    ['Participants', '{{participant_count}}'], ['Facilitators', '{{facilitators}}'], ['Budget and Source', '{{budget}}']
  ]);
  details.setBorderWidth(1);
  at_add_(body, '7.  Proposed Program of Activities').setBold(true);
  const program = at_table_(body, [['Day', 'AM', 'PM'], ['{{pd_day}}', '{{pd_am}}', '{{pd_pm}}']]);
  program.getRow(0).editAsText().setBold(true);
  at_add_(body, '');
  const signers = at_table_(body, [['Prepared by:', 'Noted by:'], ['{{prepared_by}}', '{{noted_by_name}}'],
                                    ['{{prepared_title}}', '{{noted_by_title}}']]);
  signers.setBorderWidth(0);
  signers.getRow(0).editAsText().setBold(true);
  at_add_(body, '');
  at_add_(body, 'Recommended by:').setBold(true);
  at_add_(body, '{{recommended_name}}').setBold(true);
  at_add_(body, '{{recommended_title}}');
  at_add_(body, '{{unit_name}}');
  body.editAsText().setFontFamily('Times New Roman');
  body.editAsText().setFontSize(12);
  at_footer_(doc);
  const first = body.getChild(0);
  if (first.getType() === DocumentApp.ElementType.PARAGRAPH && first.asParagraph().getText() === '') body.removeChild(first);
}

// The program flow: the activity and one table of Date/Time, Topic/Activity and Person Responsible.
//   {{pf_time}} {{pf_topic}} {{pf_person}} sit in ONE table row: the app copies it for each day heading and each empty row.
function at_buildProgramFlow_(body, doc) {
  at_letterhead_(doc.addHeader());
  at_add_(body, 'Activity: {{title}}').setBold(true);
  at_add_(body, 'Tentative Program Flow:');
  const table = at_table_(body, [['Date/Time', 'Topic/Activity', 'Person Responsible'], ['{{pf_time}}', '{{pf_topic}}', '{{pf_person}}']]);
  table.getRow(0).editAsText().setBold(true);
  body.editAsText().setFontFamily('Times New Roman');
  body.editAsText().setFontSize(12);
  at_footer_(doc);
  const first = body.getChild(0);
  if (first.getType() === DocumentApp.ElementType.PARAGRAPH && first.asParagraph().getText() === '') body.removeChild(first);
}

// Notice of meeting (spot feedback #189/#192): the date, what the meeting is, when and where (with the online link when there is
// one), who is invited and the agenda to write. {{invited}} and {{agenda}} are blocks; {{meeting_link}} is optional.
function at_buildNotice_(body, doc) {
  at_letterhead_(doc.addHeader());
  at_add_(body, '{{date}}');
  at_add_(body, 'NOTICE OF MEETING').setBold(true).setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  at_add_(body, '{{title}}').setBold(true).setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  at_add_(body, 'Please be informed that a meeting will be held as follows:').setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
  at_add_(body, 'Date and time: {{meeting_when}}');
  at_add_(body, 'Venue: {{venue}}');
  at_add_(body, 'Online link: {{meeting_link}}');
  at_add_(body, 'Invited:').setBold(true);
  at_add_(body, '{{invited}}');
  at_add_(body, 'Agenda:').setBold(true);
  at_add_(body, '{{agenda}}');
  at_add_(body, 'Your attendance is requested.').setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
  at_add_(body, '{{head_name}}').setBold(true);
  at_add_(body, '{{head_title}}');
  at_add_(body, '{{unit_name}}');
  at_add_(body, 'Prepared by: {{prepared_by}}');
  at_add_(body, '{{prepared_title}}');
  body.editAsText().setFontFamily('Times New Roman');
  body.editAsText().setFontSize(12);
  at_footer_(doc);
  const first = body.getChild(0);
  if (first.getType() === DocumentApp.ElementType.PARAGRAPH && first.asParagraph().getText() === '') body.removeChild(first);
}

// Minutes of the meeting (spot feedback #177): title, when and where, who attended, the agenda, what was discussed and
// decided, a table of action points and the signatures. {{attendees}}, {{agenda}}, {{discussion}} and {{next_steps}} are
// blocks; {{m_action}}, {{m_who}} and {{m_due}} sit in ONE table row.
function at_buildMinutes_(body, doc, officeFrame) {
  if (!officeFrame) at_letterhead_(doc.addHeader());
  at_add_(body, 'MINUTES OF THE MEETING').setBold(true).setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  at_add_(body, '{{title}}').setBold(true).setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  at_add_(body, 'Date and time: {{meeting_when}}');
  at_add_(body, 'Venue: {{venue}}');
  at_add_(body, 'Attendees:').setBold(true);
  at_add_(body, '{{attendees}}');
  at_add_(body, 'Agenda:').setBold(true);
  at_add_(body, '{{agenda}}');
  at_add_(body, 'Discussion and decisions:').setBold(true);
  at_add_(body, '{{discussion}}').setAlignment(DocumentApp.HorizontalAlignment.JUSTIFY);
  at_add_(body, 'Action points:').setBold(true);
  const table = at_table_(body, [['Action', 'Person responsible', 'Due'], ['{{m_action}}', '{{m_who}}', '{{m_due}}']]);
  table.getRow(0).editAsText().setBold(true);
  at_add_(body, 'Next steps:').setBold(true);
  at_add_(body, '{{next_steps}}');
  at_add_(body, 'Prepared by:').setBold(true);
  at_add_(body, '{{prepared_by}}');
  at_add_(body, '{{prepared_title}}');
  at_add_(body, 'Approved by:').setBold(true);
  at_add_(body, '{{approved_by}}');
  at_add_(body, '{{unit_name}}');
  body.editAsText().setFontFamily('Times New Roman');
  body.editAsText().setFontSize(12);
  if (!officeFrame) at_footer_(doc);
  const first = body.getChild(0);
  if (first.getType() === DocumentApp.ElementType.PARAGRAPH && first.asParagraph().getText() === '') body.removeChild(first);
}
