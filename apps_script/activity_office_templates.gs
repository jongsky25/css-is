// Converts office Blanks without redrawing their page, header, footer or artwork.
// Same project as travel_docs.gs; enable Drive v3 and Docs advanced services.
// Run makeOfficeTemplates() as the office mailbox. Failed candidates are never activated.
const AO_SOURCE_FOLDER_ID = '1HU-MCk_csQhYmIs_5g1HqKNZ3DIbPVy4';
const AO_TEMPLATES = [
  { key: 'invitation', source: 'Blank [Memo - Invitation - Internal]', build: ao_memo_,
    expect: ['date', 'for_name', 'for_title', 'for_office', 'from_name', 'from_title', 'unit_name',
             'subject', 'reiteration', 'rationale', 'details', 'representatives', 'contact_details'] },
  { key: 'notice_of_meeting', source: 'Blank [NOM] .docx', build: ao_notice_,
    expect: ['date', 'inv_name', 'inv_office', 'head_name', 'head_title', 'unit_name',
             'subject', 'meeting_date', 'meeting_time', 'venue', 'meeting_link', 'agenda'] }
];

function makeOfficeNoticeTemplate() { return makeOfficeTemplates(['notice_of_meeting'], false); }
function rebuildOfficeNoticeTemplate() { return makeOfficeTemplates(['notice_of_meeting'], true); }

function rebuildOfficeMemoTemplate() { return makeOfficeTemplates(['invitation'], true); }

function makeOfficeTemplates(only, force) {
  if (typeof only === 'string') only = [only];
  const props = PropertiesService.getScriptProperties(), report = [];
  const source = DriveApp.getFolderById(AO_SOURCE_FOLDER_ID);
  const root = DriveApp.getFolderById(props.getProperty('ROOT_FOLDER_ID'));
  const folders = root.getFoldersByName('_templates');
  const out = folders.hasNext() ? folders.next() : root.createFolder('_templates');
  AO_TEMPLATES.forEach(function (t) {
    if (only && only.indexOf(t.key) < 0) return;
    try {
      const old = props.getProperty('TPL_' + t.key);
      if (old && !force && props.getProperty('TPLF_' + t.key) === old) {
        let gaps;
        try { gaps = ao_missing_(old, t); } catch (e) { gaps = ['unreadable']; }
        if (!gaps.length) { report.push(t.key + ': already good, kept'); return; }
      }
      const files = source.getFilesByName(t.source);
      if (!files.hasNext()) throw new Error('source Blank not found');
      const file = files.next();
      if (files.hasNext()) throw new Error('source name is ambiguous');
      const candidate = Drive.Files.copy({ name: 'Template - office ' + t.key,
        mimeType: 'application/vnd.google-apps.document', parents: [out.getId()] }, file.getId(), { supportsAllDrives: true });
      if (!candidate || !candidate.id) throw new Error('conversion returned no document');
      t.build(candidate.id);
      const missing = ao_missing_(candidate.id, t);
      if (missing.length) throw new Error('MISSING ' + missing.join(', ') + '; candidate ' + candidate.id);
      // One property update only after building and checking the complete candidate.
      const settings = {};
      settings['TPL_' + t.key] = candidate.id;
      settings['TPLF_' + t.key] = candidate.id;
      props.setProperties(settings);
      report.push(t.key + ': all placeholders present; activated https://docs.google.com/document/d/' + candidate.id
        + (old ? '; previous template ' + old : ''));
    } catch (e) { report.push(t.key + ': FAILED - ' + e.message); }
  });
  Logger.log(report.join('\n')); return report.join('\n');
}

function checkOfficeTemplates() {
  const props = PropertiesService.getScriptProperties();
  const report = AO_TEMPLATES.map(function (t) {
    try {
      const id = props.getProperty('TPL_' + t.key);
      if (!id) return t.key + ': not set';
      const missing = ao_missing_(id, t);
      return t.key + ': ' + (missing.length ? 'MISSING ' + missing.join(', ') : 'all placeholders present')
        + (props.getProperty('TPLF_' + t.key) === id ? '; office format marker matches' : '; office format marker MISMATCH');
    } catch (e) { return t.key + ': FAILED - ' + e.message; }
  });
  Logger.log(report.join('\n')); return report.join('\n');
}

function ao_missing_(id, t) {
  const text = DocumentApp.openById(id).getBody().getText();
  return t.expect.filter(function (key) { return text.indexOf('{{' + key + '}}') < 0; });
}
function ao_norm_(text) { return String(text).replace(/[\s\u00a0]+/g, ' ').trim(); }

// Pure mapping: derive positions from labels, not the source's fixed personal names.
// Refuse changed source structures instead of activating a partial or wrongly mapped template.
function ao_memoPlan_(items) {
  const texts = items.map(function (item) { return ao_norm_(item.text); });
  const titles = texts.reduce(function (out, text, i) { if (text === 'MEMORANDUM') out.push(i); return out; }, []);
  if (titles.length !== 2) throw new Error('expected original and file-copy MEMORANDUM');
  const first = titles[0], second = titles[1];
  const find = function (predicate) {
    const found = [];
    for (let i = first + 1; i < second; i++) if (predicate(texts[i])) found.push(i);
    if (found.length !== 1) throw new Error('memo label missing or ambiguous');
    return found[0];
  };
  const to = find(function (s) { return s === 'FOR:'; });
  const from = find(function (s) { return /^FROM:/.test(s); });
  const subject = find(function (s) { return s === 'SUBJECT:'; });
  const reit = find(function (s) { return s === '[Reiteration of Subject]'; });
  const rationale = find(function (s) { return s === '[Rationale of Invitation]'; });
  const details = find(function (s) { return /^\[Further details .*\]$/.test(s); });
  const contact = find(function (s) { return s === '[Contact details of assigned staff]'; });
  const thanks = find(function (s) { return s === 'Thank you very much.'; });
  let date = first - 1;
  while (date >= 0 && !texts[date]) date--;
  if (date < 0 || !/^_+$/.test(texts[date]) || !(to + 2 < from && from + 2 < subject
      && subject < reit && reit < rationale && rationale < details && details < contact && contact < thanks)
      || texts[to + 1] || texts[to + 2]) throw new Error('unexpected memo structure');
  for (let i = date; i <= thanks; i++) if (items[i].type !== 'paragraph') throw new Error('unexpected memo body element');
  const replacements = [
    [date, '{{date}}'], [to, 'FOR:\t{{for_name}}'], [to + 1, '{{for_title}}'], [to + 2, '{{for_office}}'],
    [from, 'FROM:\t{{from_name}}'], [from + 1, '{{from_title}}'], [from + 2, '\t\t{{unit_name}}'],
    [subject, 'SUBJECT:\t{{subject}}'], [reit, '{{reiteration}}'], [rationale, '{{rationale}}'],
    [details, '{{details}}'], [contact, '{{contact_details}}']
  ];
  return { replacements: replacements, end: thanks + 1, representativesBefore: contact, addressee: to };
}

// Keep the paragraph and its first character's text formatting, rather than replacing its structure.
function ao_text_(paragraph, value) {
  const text = paragraph.editAsText(), length = text.getText().length;
  text.insertText(0, value);
  if (length) text.deleteText(value.length, value.length + length - 1);
}

function ao_memo_(id) {
  const doc = DocumentApp.openById(id), body = doc.getBody(), T = DocumentApp.ElementType;
  const items = [];
  for (let i = 0; i < body.getNumChildren(); i++) {
    const el = body.getChild(i);
    items.push({ type: el.getType() === T.PARAGRAPH ? 'paragraph' : 'other', text: el.getText ? el.getText() : '' });
  }
  const plan = ao_memoPlan_(items);
  // Remove the embedded duplicate and its named initials table; the relay copies the filled original later.
  for (let i = body.getNumChildren() - 1; i >= plan.end; i--) body.removeChild(body.getChild(i));
  plan.replacements.forEach(function (replacement) { ao_text_(body.getChild(replacement[0]).asParagraph(), replacement[1]); });
  // The Blank leaves this area empty. Retain bold names and plain stacked title/office lines.
  body.getChild(plan.addressee).asParagraph().editAsText().setBold(true);
  [1, 2].forEach(function (offset) {
    const para = body.getChild(plan.addressee + offset).asParagraph();
    para.setIndentStart(180).setIndentFirstLine(180); para.editAsText().setBold(false);
  });
  const list = body.insertListItem(plan.representativesBefore, '{{representatives}}');
  list.setAttributes(body.getChild(plan.representativesBefore - 1).getAttributes());
  list.setGlyphType(DocumentApp.GlyphType.BULLET).setIndentStart(36).setIndentFirstLine(18);
  doc.saveAndClose();
}

// Pure mapping for the converted NOM. Drive conversion must expose the Word
// content-control table as a normal table; otherwise refuse activation.
function ao_noticePlan_(items) {
  const text = items.map(function (item) { return ao_norm_(item.text || ''); });
  const titles = [];
  text.forEach(function (value, i) { if (value === 'NOTICE OF MEETING') titles.push(i); });
  if (titles.length !== 2) throw new Error('expected original and file-copy NOTICE OF MEETING');
  const first = titles[0], second = titles[1];
  const tables = [], from = [];
  for (let i = first + 1; i < second; i++) {
    if (items[i].type === 'table') tables.push(i);
    if (/^FROM:/.test(text[i])) from.push(i);
  }
  if (tables.length !== 2 || from.length !== 1) throw new Error('NOM tables or FROM missing/ambiguous');
  const invites = tables[0], grid = tables[1], sender = from[0];
  const rows = items[invites].rows, labels = ['SUBJECT:', 'DATE:', 'TIME:', 'VENUE:', 'AGENDA:'];
  if (!rows || rows.length < 2 || rows.some(function (row) { return row.length !== 2; })
      || ao_norm_(rows[0][0]) !== 'Name' || ao_norm_(rows[0][1]) !== 'Office'
      || rows.slice(1).some(function (row) { return row.some(function (cell) { return ao_norm_(cell) !== ''; }); })) {
    throw new Error('unexpected NOM invitee table');
  }
  const values = items[grid].rows;
  if (!values || values.length !== labels.length || values.some(function (row, i) {
    return row.length !== 3 || ao_norm_(row[0]) !== labels[i] || ao_norm_(row[1]) || ao_norm_(row[2]);
  })) throw new Error('unexpected NOM details grid');
  let date = first - 1;
  while (date >= 0 && !text[date]) date--;
  if (date < 0 || !/^_+$/.test(text[date]) || !(invites < sender && sender + 2 < grid)
      || !items[grid + 1] || items[grid + 1].type !== 'paragraph' || text[grid + 1]) {
    throw new Error('unexpected NOM structure');
  }
  [date, sender, sender + 1, sender + 2].forEach(function (i) {
    if (items[i].type !== 'paragraph') throw new Error('unexpected NOM sender/date element');
  });
  return { date: date, sender: sender, invites: invites, grid: grid, end: grid + 2 };
}

function ao_tableRows_(table) {
  const rows = [];
  for (let r = 0; r < table.getNumRows(); r++) {
    const row = table.getRow(r), cells = [];
    for (let c = 0; c < row.getNumCells(); c++) cells.push(row.getCell(c).getText());
    rows.push(cells);
  }
  return rows;
}

function ao_cellText_(cell, value) {
  // Retain the first element's paragraph/list style. Avoid replacing the cell,
  // which would discard borders, widths and the NOM's own spacing.
  const first = cell.getChild(0);
  ao_text_(first, value);
  for (let i = cell.getNumChildren() - 1; i > 0; i--) cell.removeChild(cell.getChild(i));
}

function ao_notice_(id) {
  const doc = DocumentApp.openById(id), body = doc.getBody(), T = DocumentApp.ElementType, items = [];
  for (let i = 0; i < body.getNumChildren(); i++) {
    const child = body.getChild(i), type = child.getType();
    const item = { type: type === T.TABLE ? 'table' : type === T.PARAGRAPH ? 'paragraph' : 'other',
      text: child.getText ? child.getText() : '' };
    if (type === T.TABLE) item.rows = ao_tableRows_(child.asTable());
    items.push(item);
  }
  const plan = ao_noticePlan_(items);
  for (let i = body.getNumChildren() - 1; i >= plan.end; i--) body.removeChild(body.getChild(i));
  // Keep the required paragraph after the last table, removing its old page break.
  body.getChild(plan.end - 1).asParagraph().clear();
  ao_text_(body.getChild(plan.date).asParagraph(), '{{date}}');
  ao_text_(body.getChild(plan.sender).asParagraph(), 'FROM:\t{{head_name}}');
  ao_text_(body.getChild(plan.sender + 1).asParagraph(), '{{head_title}}');
  ao_text_(body.getChild(plan.sender + 2).asParagraph(), '{{unit_name}}');
  const invitees = body.getChild(plan.invites).asTable();
  for (let r = invitees.getNumRows() - 1; r > 1; r--) invitees.removeRow(r);
  ao_cellText_(invitees.getCell(1, 0), '{{inv_name}}');
  ao_cellText_(invitees.getCell(1, 1), '{{inv_office}}');
  const grid = body.getChild(plan.grid).asTable();
  ['{{subject}}', '{{meeting_date}}', '{{meeting_time}}', '{{venue}}\n{{meeting_link}}'].forEach(function (value, i) {
    ao_cellText_(grid.getCell(i, 2), value);
  });
  const cell = grid.getCell(4, 2), first = cell.getChild(0);
  if (first.getType() === T.LIST_ITEM) ao_cellText_(cell, '{{agenda}}');
  else {
    const list = cell.insertListItem(0, '{{agenda}}');
    list.setAttributes(first.getAttributes());
    list.setGlyphType(DocumentApp.GlyphType.BULLET).setIndentStart(36).setIndentFirstLine(18);
    for (let i = cell.getNumChildren() - 1; i > 0; i--) cell.removeChild(cell.getChild(i));
  }
  doc.saveAndClose();
}
