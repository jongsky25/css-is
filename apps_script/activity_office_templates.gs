// Converts office Blanks without redrawing their page, header, footer or artwork.
// Same project as travel_docs.gs; enable Drive v3 and Docs advanced services.
// Run makeOfficeTemplates() as the office mailbox. Failed candidates are never activated.
const AO_SOURCE_FOLDER_ID = '1HU-MCk_csQhYmIs_5g1HqKNZ3DIbPVy4';
const AO_TEMPLATES = [
  { key: 'invitation', source: 'Blank [Memo - Invitation - Internal]', build: ao_memo_,
    expect: ['date', 'for_name', 'for_title', 'for_office', 'from_name', 'from_title', 'unit_name',
             'subject', 'reiteration', 'rationale', 'details', 'representatives', 'contact_details'] }
];

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
