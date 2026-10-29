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
             'subject', 'meeting_date', 'meeting_time', 'venue', 'meeting_link', 'agenda'] },
  { key: 'concept_note', source: 'Blank [Concept Note and Program]', build: ao_concept_,
    expect: ['title', 'background', 'objectives', 'outputs', 'participants_note', 'methodology',
      'pt_group', 'pt_count', 'participant_count', 'date_duration', 'venue', 'facilitators', 'budget',
      'pd_day', 'pd_text', 'prepared_by', 'prepared_title', 'noted_by_name', 'noted_by_title',
      'recommended_name', 'recommended_title', 'recommended_unit', 'approved_name', 'approved_title', 'approved_unit'] },
  { key: 'program_flow', source: 'Blank [Concept Note and Program]', build: ao_program_,
    expect: ['title', 'pf_time', 'pf_topic', 'pf_person'] },
  { key: 'invitation_external', source: 'Blank [Letter - Invitation - External]', build: ao_letter_,
    expect: ['date', 'addressee_name', 'addressee_title', 'addressee_agency', 'addressee_address',
      'subject', 'salutation_name', 'letter_opening', 'activity_purpose', 'letter_details', 'contact_details', 'head_name', 'head_title'] }
];

function makeOfficeExternalLetterTemplate() { return makeOfficeTemplates(['invitation_external'], false); }
function rebuildOfficeExternalLetterTemplate() { return makeOfficeTemplates(['invitation_external'], true); }

function makeOfficeConceptTemplates() { return makeOfficeTemplates(['concept_note', 'program_flow'], false); }
function rebuildOfficeConceptTemplates() { return makeOfficeTemplates(['concept_note', 'program_flow'], true); }

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

// Split with the Docs API: DocumentApp cannot reliably preserve section styles
// while removing section breaks. Restore the selected section's effective page
// settings, then refuse activation if its header/footer content changed.
function ao_cleanLayout_(value) {
  if (Array.isArray(value)) return value.map(ao_cleanLayout_);
  if (!value || typeof value !== 'object') return value;
  const out = {};
  Object.keys(value).sort().forEach(function (key) {
    if (['startIndex', 'endIndex', 'objectId', 'inlineObjectId', 'positionedObjectIds',
         'contentUri', 'sourceUri', 'tabId'].indexOf(key) < 0) out[key] = ao_cleanLayout_(value[key]);
  });
  return out;
}
function ao_sections_(doc) {
  return (doc.body && doc.body.content || []).filter(function (el) { return !!el.sectionBreak; });
}
function ao_headerFooter_(doc, index) {
  const sections = ao_sections_(doc), effective = Object.assign({}, doc.documentStyle || {}), result = {};
  for (let i = 0; i <= index; i++) Object.assign(effective, sections[i].sectionBreak.sectionStyle || {});
  ['defaultHeaderId', 'firstPageHeaderId', 'evenPageHeaderId',
   'defaultFooterId', 'firstPageFooterId', 'evenPageFooterId'].forEach(function (key) {
    const id = effective[key], part = ((/Header/.test(key) ? doc.headers : doc.footers) || {})[id];
    const objects = [];
    function collect(value) {
      if (!value || typeof value !== 'object') return;
      if (value.inlineObjectId) {
        const inline = (doc.inlineObjects || {})[value.inlineObjectId];
        if (!inline) throw new Error('header/footer inline image missing');
        objects.push(ao_cleanLayout_(inline));
      }
      (value.positionedObjectIds || []).forEach(function (objectId) {
        const positioned = (doc.positionedObjects || {})[objectId];
        if (!positioned) throw new Error('header/footer positioned image missing');
        objects.push(ao_cleanLayout_(positioned));
      });
      Object.keys(value).forEach(function (k) { collect(value[k]); });
    }
    if (id && !part) throw new Error('section header/footer could not be inspected');
    collect(part);
    result[key] = { content: ao_cleanLayout_(part ? part.content : []),
      objects: objects.map(function (o) { return JSON.stringify(o); }).sort() };
  });
  return JSON.stringify(result);
}
function ao_splitConcept_(id, selected) {
  const before = Docs.Documents.get(id), sections = ao_sections_(before);
  if (sections.length !== 2) throw new Error('expected two concept/program sections');
  const expected = ao_headerFooter_(before, selected), style = {}, effective = Object.assign({}, before.documentStyle,
    sections[selected].sectionBreak.sectionStyle || {});
  ['marginTop', 'marginBottom', 'marginLeft', 'marginRight', 'marginHeader', 'marginFooter',
   'useFirstPageHeaderFooter'].forEach(function (key) { if (effective[key] !== undefined) style[key] = effective[key]; });
  const content = before.body.content, last = content[content.length - 1];
  const range = selected === 0
    ? { startIndex: sections[1].startIndex, endIndex: last.endIndex - 1 }
    : { startIndex: 1, endIndex: sections[1].endIndex };
  if (!(range.startIndex < range.endIndex)) throw new Error('invalid concept/program split range');
  const requests = [{ deleteContentRange: { range: range } },
    { updateSectionStyle: { range: { startIndex: 1, endIndex: 2 }, sectionStyle: style, fields: Object.keys(style).join(',') } }];
  if (before.documentStyle.documentSize) requests.push({ updateDocumentStyle: {
    documentStyle: { documentSize: before.documentStyle.documentSize }, fields: 'documentSize' } });
  Docs.Documents.batchUpdate({ requests: requests }, id);
  const after = Docs.Documents.get(id);
  if (ao_sections_(after).length !== 1 || ao_headerFooter_(after, 0) !== expected) {
    throw new Error('split changed section headers/footers; candidate not activated');
  }
  if (JSON.stringify(ao_cleanLayout_(after.documentStyle.documentSize)) !== JSON.stringify(ao_cleanLayout_(before.documentStyle.documentSize))) {
    throw new Error('split changed paper size');
  }
  const actual = Object.assign({}, after.documentStyle, ao_sections_(after)[0].sectionBreak.sectionStyle || {});
  Object.keys(style).forEach(function (key) {
    if (JSON.stringify(ao_cleanLayout_(actual[key])) !== JSON.stringify(ao_cleanLayout_(style[key]))) throw new Error('split changed ' + key);
  });
}
function ao_items_(body) {
  const T = DocumentApp.ElementType, items = [];
  for (let i = 0; i < body.getNumChildren(); i++) {
    const child = body.getChild(i), type = child.getType();
    const item = { type: type === T.TABLE ? 'table' : type === T.PARAGRAPH || type === T.LIST_ITEM ? 'paragraph' : 'other',
      text: child.getText ? child.getText() : '' };
    if (type === T.TABLE) item.rows = ao_tableRows_(child.asTable());
    items.push(item);
  }
  return items;
}
function ao_conceptPlan_(items) {
  const texts = items.map(function (item) { return ao_norm_(item.text || ''); });
  function find(text) {
    const found = [];
    texts.forEach(function (value, i) { if (value === text) found.push(i); });
    if (found.length !== 1) throw new Error('concept label missing/ambiguous: ' + text);
    return found[0];
  }
  const title = find('CONCEPT NOTE');
  const labels = ['Background and Rationale', 'Objectives', 'Expected Outputs', 'Participants', 'Methodology',
    'Operational Details', 'Proposed Program of Activities', 'Recommended by:', 'Approved by:'];
  const positions = labels.map(find);
  if (positions.some(function (pos, i) { return pos <= (i ? positions[i - 1] : title + 1); })) throw new Error('concept sections out of order');
  if (!/^\[Name of Activity/.test(texts[title + 1])) throw new Error('concept activity title missing');
  const tables = items.reduce(function (out, item, i) { if (item.type === 'table') out.push(i); return out; }, []);
  if (tables.length !== 3 || tables[0] !== positions[3] + 1 || tables[1] !== positions[5] + 1 || tables[2] !== positions[6] + 1) {
    throw new Error('unexpected concept tables');
  }
  const participants = items[tables[0]].rows, operations = items[tables[1]].rows, program = items[tables[2]].rows;
  if (participants.length < 3 || participants.some(function (row) { return row.length !== 2; })
      || ao_norm_(participants[0][0]) !== 'Participant' || ao_norm_(participants[0][1]) !== 'Number'
      || ao_norm_(participants[participants.length - 1][0]) !== 'Estimated Total'
      || participants.slice(1, -1).some(function (row) { return row.some(function (cell) { return ao_norm_(cell); }); })) {
    throw new Error('unexpected participant table');
  }
  const ops = ['Title', 'Date/Duration', 'Venue', 'Participants', 'Facilitators', 'Budget and Source'];
  if (operations.length !== ops.length || operations.some(function (row, i) {
    return row.length !== 2 || ao_norm_(row[0]) !== ops[i] || ao_norm_(row[1]);
  })) throw new Error('unexpected operational details');
  if (program.length < 2 || program.some(function (row) { return row.length !== 2; })
      || ao_norm_(program[0][0]) !== 'Day' || ao_norm_(program[0][1]) !== 'Activity'
      || program.slice(1).some(function (row) { return !/^Day \d+$/.test(ao_norm_(row[0])) || ao_norm_(row[1]); })) {
    throw new Error('unexpected activities table');
  }
  const prepared = texts.findIndex(function (text) { return /^Prepared by:.*Noted by:/.test(text); });
  function nextText(start) { let i = start + 1; while (i < texts.length && !texts[i]) i++; return i; }
  const preparedNames = nextText(prepared), recommended = nextText(positions[7]), approved = nextText(positions[8]);
  if (!(prepared > tables[2] && preparedNames + 1 < positions[7] && recommended + 2 < positions[8] && approved + 2 < items.length)) {
    throw new Error('unexpected concept signatories');
  }
  [positions[0] + 1, positions[1] + 1, positions[2] + 1, tables[0] + 1, positions[4] + 1].forEach(function (i) {
    if (texts[i]) throw new Error('concept prose area is not blank');
  });
  const replacements = [[title + 1, '{{title}}'], [positions[0] + 1, '{{background}}'],
    [positions[1] + 1, '{{objectives}}'], [positions[2] + 1, '{{outputs}}'],
    [tables[0] + 1, '{{participants_note}}'], [positions[4] + 1, '{{methodology}}'],
    [preparedNames, '{{prepared_by}}\t\t\t\t{{noted_by_name}}'],
    [preparedNames + 1, '{{prepared_title}}\t\t\t\t\t{{noted_by_title}}'],
    [recommended, '{{recommended_name}}'], [recommended + 1, '{{recommended_title}}'], [recommended + 2, '{{recommended_unit}}'],
    [approved, '{{approved_name}}'], [approved + 1, '{{approved_title}}'], [approved + 2, '{{approved_unit}}']];
  replacements.forEach(function (replacement) {
    if (!items[replacement[0]] || items[replacement[0]].type !== 'paragraph') throw new Error('unexpected concept placeholder location');
  });
  return { replacements: replacements, tables: tables };
}
function ao_concept_(id) {
  ao_splitConcept_(id, 0);
  const doc = DocumentApp.openById(id), body = doc.getBody(), plan = ao_conceptPlan_(ao_items_(body));
  plan.replacements.forEach(function (replacement) { ao_text_(body.getChild(replacement[0]), replacement[1]); });
  const participants = body.getChild(plan.tables[0]).asTable();
  for (let r = participants.getNumRows() - 2; r > 1; r--) participants.removeRow(r);
  ao_cellText_(participants.getCell(1, 0), '{{pt_group}}'); ao_cellText_(participants.getCell(1, 1), '{{pt_count}}');
  ao_cellText_(participants.getCell(2, 1), '{{participant_count}}');
  const operations = body.getChild(plan.tables[1]).asTable();
  ['title', 'date_duration', 'venue', 'participant_count', 'facilitators', 'budget'].forEach(function (key, i) {
    ao_cellText_(operations.getCell(i, 1), '{{' + key + '}}');
  });
  const program = body.getChild(plan.tables[2]).asTable();
  for (let r = program.getNumRows() - 1; r > 1; r--) program.removeRow(r);
  ao_cellText_(program.getCell(1, 0), '{{pd_day}}'); ao_cellText_(program.getCell(1, 1), '{{pd_text}}');
  doc.saveAndClose();
}
function ao_programPlan_(items) {
  const texts = items.map(function (item) { return ao_norm_(item.text || ''); });
  const heading = texts.indexOf('Tentative Program Flow:');
  const tables = items.reduce(function (out, item, i) { if (item.type === 'table') out.push(i); return out; }, []);
  if (heading < 1 || !/^Activity:/.test(texts[heading - 1]) || tables.length !== 1 || tables[0] !== heading + 1) {
    throw new Error('unexpected program flow section');
  }
  const rows = items[tables[0]].rows;
  if (rows.length < 3 || JSON.stringify(rows[0].map(ao_norm_)) !== JSON.stringify(['Date/Time', 'Topic/Activity', 'Person Responsible'])) {
    throw new Error('unexpected program flow table');
  }
  const prototype = rows.findIndex(function (row, i) { return i > 0 && row.length === 3; });
  if (prototype < 0) throw new Error('program flow has no three-cell prototype');
  return { title: heading - 1, table: tables[0], prototype: prototype };
}
function ao_program_(id) {
  ao_splitConcept_(id, 1);
  const doc = DocumentApp.openById(id), body = doc.getBody(), plan = ao_programPlan_(ao_items_(body));
  ao_text_(body.getChild(plan.title), 'Activity: {{title}}');
  const table = body.getChild(plan.table).asTable();
  for (let r = table.getNumRows() - 1; r > 0; r--) if (r !== plan.prototype) table.removeRow(r);
  ['pf_time', 'pf_topic', 'pf_person'].forEach(function (key, i) { ao_cellText_(table.getCell(1, i), '{{' + key + '}}'); });
  doc.saveAndClose();
}

function ao_literal_(value) { return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
function ao_letterPlan_(items) {
  const texts = items.map(function (item) { return ao_norm_(item.text || ''); });
  const dates = [];
  texts.forEach(function (text, i) { if (text === '[Date]') dates.push(i); });
  if (dates.length !== 2) throw new Error('expected original and file-copy letter');
  const start = dates[0], second = dates[1];
  function find(predicate) {
    const found = [];
    for (let i = start; i < second; i++) if (predicate(texts[i])) found.push(i);
    if (found.length !== 1) throw new Error('letter label missing/ambiguous');
    return found[0];
  }
  const addressee = find(function (text) {
    return text.indexOf('[NAME OF HEAD]') >= 0 && text.indexOf('[Name of Agency]') >= 0 && text.indexOf('[Address of Agency]') >= 0;
  });
  const subject = find(function (text) { return text === 'Subject:'; });
  const dear = find(function (text) { return text === 'Dear [Head]:'; });
  const opening = find(function (text) { return text === '[Brief purpose of letter or invitation]'; });
  const purpose = find(function (text) { return text === '[Purpose of activity]'; });
  const details = find(function (text) { return /^\[Expanded reiteration of purpose of letter or invitation,.*\]$/.test(text); });
  const contact = find(function (text) { return text === '[Contact details of staff or personnel]'; });
  const thanks = find(function (text) { return text === 'Thank you very much.'; });
  const close = find(function (text) { return text === 'Very truly yours,'; });
  const name = find(function (text) { return text === '[NAME OF HEAD OF OFFICE OR CLUSTER LEAD]'; });
  const title = find(function (text) { return text === '[Designation]'; });
  const positions = [start, addressee, subject, dear, opening, purpose, details, contact, thanks, close, name, title];
  if (positions.some(function (pos, i) { return i && pos <= positions[i - 1]; })) throw new Error('letter sections out of order');
  for (let i = start; i <= title; i++) if (items[i].type !== 'paragraph') throw new Error('unexpected letter body element');
  const residue = texts[addressee].replace('[NAME OF HEAD]', '').replace('[Name of Agency]', '').replace('[Address of Agency]', '').trim();
  if (residue) throw new Error('unexpected letter addressee content');
  return { addressee: addressee, end: title + 1, replacements: [
    [start, '{{date}}'], [subject, 'Subject: {{subject}}'], [dear, 'Dear {{salutation_name}}:'],
    [opening, '{{letter_opening}}'], [purpose, '{{activity_purpose}}'], [details, '{{letter_details}}'],
    [contact, '{{contact_details}}'], [name, '{{head_name}}'], [title, '{{head_title}}'] ] };
}
function ao_letter_(id) {
  const doc = DocumentApp.openById(id), body = doc.getBody(), plan = ao_letterPlan_(ao_items_(body));
  for (let i = body.getNumChildren() - 1; i >= plan.end; i--) body.removeChild(body.getChild(i));
  plan.replacements.forEach(function (replacement) { ao_text_(body.getChild(replacement[0]), replacement[1]); });
  // Replace runs individually: the source name is bold, agency/address are plain.
  const addressee = body.getChild(plan.addressee);
  addressee.replaceText(ao_literal_('[NAME OF HEAD]'), '{{addressee_name}}');
  addressee.replaceText(ao_literal_('[Name of Agency]'), '{{addressee_title}}\n{{addressee_agency}}');
  addressee.replaceText(ao_literal_('[Address of Agency]'), '{{addressee_address}}');
  doc.saveAndClose();
}
