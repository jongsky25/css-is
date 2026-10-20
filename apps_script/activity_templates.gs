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

const AT_TEMPLATES = [
  { key: 'dpo', title: 'Template - dpo', build: at_buildDpo_,
    expect: ['dpo_no', 'dpo_date', 'title', 'purpose', 'dates', 'venue', 'funding_source', 'personnel', 'head_name',
             'head_title', 'prepared_by'] },
  { key: 'invitation', title: 'Template - invitation', build: at_buildInvitation_,
    expect: ['date', 'title', 'invited', 'details', 'sender_name', 'sender_title', 'contact', 'head_name', 'head_title'] }
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
      t.build(doc.getBody());
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

function at_heading_(body, text) {
  body.appendParagraph(text).setHeading(DocumentApp.ParagraphHeading.HEADING2).setAlignment(DocumentApp.HorizontalAlignment.CENTER);
}

function at_buildDpo_(body) {
  body.appendParagraph('DEPARTMENT PERSONNEL ORDER').setHeading(DocumentApp.ParagraphHeading.HEADING1)
      .setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  body.appendParagraph('No. {{dpo_no}}, Series of {{dpo_date}}').setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  body.appendParagraph('SUBJECT: Authority to participate in {{title}}').setBold(true);
  body.appendParagraph('In the interest of the service, the following personnel are authorized to {{purpose}} on {{dates}} at {{venue}}:');
  body.appendParagraph('{{personnel}}');
  body.appendParagraph('Funding source: {{funding_source}}');
  body.appendParagraph('Travel and other expenses are subject to the usual accounting and auditing rules and regulations.');
  body.appendParagraph('This Order takes effect immediately.');
  body.appendParagraph('');
  body.appendParagraph('{{head_name}}').setBold(true);
  body.appendParagraph('{{head_title}}');
  body.appendParagraph('');
  body.appendParagraph('Prepared by: {{prepared_by}}').setItalic(true);
}

function at_buildInvitation_(body) {
  body.appendParagraph('{{date}}').setAlignment(DocumentApp.HorizontalAlignment.RIGHT);
  body.appendParagraph('TO: {{invited}}').setBold(true);
  body.appendParagraph('SUBJECT: Invitation to {{title}}').setBold(true);
  body.appendParagraph('Greetings!');
  body.appendParagraph('You are invited to the following activity:');
  body.appendParagraph('{{details}}');
  body.appendParagraph('Please confirm your attendance with the contact below.');
  body.appendParagraph('Contact: {{contact}}');
  body.appendParagraph('');
  body.appendParagraph('Thank you.');
  body.appendParagraph('');
  body.appendParagraph('{{sender_name}}').setBold(true);
  body.appendParagraph('{{sender_title}}');
  body.appendParagraph('');
  body.appendParagraph('Noted by: {{head_name}}, {{head_title}}').setItalic(true);
}
