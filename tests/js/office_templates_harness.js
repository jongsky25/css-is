// Test converter mapping, publication and repeated addressees with synthetic source text.
const fs = require('fs'), vm = require('vm'), path = require('path');
const load = name => fs.readFileSync(path.resolve(__dirname, '../../apps_script/' + name), 'utf8');
const T = { PARAGRAPH: 'P', LIST_ITEM: 'L', TABLE: 'T', TABLE_ROW: 'R' };
class Para {
  constructor(text, type = T.PARAGRAPH) { Object.assign(this, { text, type, attrs: { spacing: 12 }, bold: false }); }
  setBold(value) { this.bold = value; return this; }
  setItalic(value) { this.italic = value; return this; }
  setUnderline(value) { this.underline = value; return this; }
  setAlignment(value) { this.attrs.alignment = value; return this; }
  setSpacingAfter(value) { this.attrs.spacingAfter = value; return this; }
  getType() { return this.type; }
  asParagraph() { if (this.type !== T.PARAGRAPH) throw Error('not a paragraph'); return this; }
  getText() { return this.text; }
  clear() { this.text = ''; delete this.attrs.pageBreak; return this; }
  setText(text) { this.text = text; return this; }
  asListItem() { return this; }
  setListId(item) { this.list = item.list; return this; }
  getParent() { return this.parent; }
  copy() { return Object.assign(new Para(this.text, this.type), this, { attrs: {...this.attrs} }); }
  getAttributes() { return this.attrs; }
  setAttributes(x) { this.attrs = {...x}; return this; }
  setIndentStart(x) { this.attrs.indentStart = x; return this; }
  setIndentFirstLine(x) { this.attrs.indentFirstLine = x; return this; }
  setGlyphType(x) { this.glyph = x; return this; }
  replaceText(pattern, value) {
    if (this.runs) {
      this.runs.forEach(run => run.text = run.text.replace(new RegExp(pattern, 'g'), () => value));
      this.text = this.runs.map(run => run.text).join('');
    } else this.text = this.text.replace(new RegExp(pattern, 'g'), () => value);
    return this;
  }
  editAsText() {
    const p = this;
    return {
      getText: () => p.text,
      insertText(i, value) { p.text = p.text.slice(0, i) + value + p.text.slice(i); return this; },
      deleteText(a, b) { p.text = p.text.slice(0, a) + p.text.slice(b + 1); return this; },
      setBold(value) { p.bold = value; return this; },
      setUnderline(...value) { p.underline = value; return this; }
    };
  }
}
class Body {
  constructor(items) { this.children = items.map(x => typeof x === 'string' ? new Para(x) : x); this.children.forEach(p => p.parent = this); }
  clear() { this.clears = (this.clears || 0) + 1; this.children = [new Para('')]; this.children[0].parent = this; return this; }
  appendParagraph(text) { return this.insertParagraph(this.children.length, text); }
  appendTable(rows) { const table = new Table(rows, []); table.parent = this; this.children.push(table); return table; }
  editAsText() { const body = this; return {
    setFontFamily(value) { body.font = value; return this; }, setFontSize(value) { body.size = value; return this; },
    setBold(value) { body.bold = value; return this; }
  }; }
  getNumChildren() { return this.children.length; }
  getChild(i) { return this.children[i]; }
  getChildIndex(p) { return this.children.indexOf(p); }
  removeChild(p) {
    // Google Docs refuses to remove a document body's last paragraph.
    if (this.constructor === Body && p === this.children[this.children.length - 1] && p instanceof Para) {
      throw new Error("Can't remove the last paragraph in a document section.");
    }
    this.children.splice(this.getChildIndex(p), 1);
  }
  getText() { return this.children.map(p => p.getText()).join('\n'); }
  insertParagraph(i, p) { if (typeof p === 'string') p = new Para(p); this.children.splice(i, 0, p); p.parent = this; return p; }
  insertListItem(i, text) { return this.insertParagraph(i, typeof text === 'string' ? new Para(text, T.LIST_ITEM) : text); }
  replaceText(pattern, value) { this.children.forEach(p => p.replaceText(pattern, value)); return this; }
  findText(pattern) {
    for (const child of this.children) {
      if (child instanceof Table) {
        for (const row of child.rows) for (const cell of row.cells) { const hit = cell.findText(pattern); if (hit) return hit; }
      } else if (new RegExp(pattern).test(child.text)) return { getElement: () => ({ getType: () => 'TEXT', getParent: () => child }) };
    }
    return null;
  }
}
class Cell extends Body {
  getType() { return 'CELL'; }
  getParent() { return this.parent; }
  constructor(items) { super(items); }
  copy() { return new Cell(this.children.map(p => p.copy())); }
}
class Row {
  constructor(cells) { this.cells = cells.map(c => c instanceof Cell ? c : new Cell([c])); this.cells.forEach(c => c.parent = this); }
  getType() { return T.TABLE_ROW; }
  asTableRow() { return this; }
  getParent() { return this.parent; }
  editAsText() { const row = this; return {setBold(value) { row.bold = value; return this; }}; }
  getNumCells() { return this.cells.length; }
  getCell(i) { return this.cells[i]; }
  copy() { return new Row(this.cells.map(c => c.copy())); }
  replaceText(pattern, value) { this.cells.forEach(c => c.replaceText(pattern, value)); }
}
class Table {
  constructor(rows, grid) { this.rows = rows.map(r => new Row(r)); this.grid = grid; this.rows.forEach(r => r.parent = this); }
  getType() { return T.TABLE; }
  asTable() { return this; }
  getParent() { return this.parent; }
  getText() { return this.rows.map(r => r.cells.map(c => c.getText()).join(' ')).join('\n'); }
  setBorderWidth(value) { this.borderWidth = value; return this; }
  setColumnWidth(c, width) { if (!this.columnWidths) this.columnWidths = []; this.columnWidths[c] = width; return this; }
  editAsText() { const table = this; return {setBold(value) { table.bold = value; return this; }}; }
  getNumRows() { return this.rows.length; }
  getRow(r) { return this.rows[r]; }
  getCell(r, c) { return this.rows[r].getCell(c); }
  removeRow(r) { this.rows.splice(r, 1); }
  getChildIndex(row) { return this.rows.indexOf(row); }
  insertTableRow(i, row) { this.rows.splice(i, 0, row); row.parent = this; return row; }
  replaceText(pattern, value) { this.rows.forEach(r => r.replaceText(pattern, value)); }
}
function notice(listAgenda = true) {
  function first() {
    const name = () => new Cell([new Para('', T.LIST_ITEM)]);
    const invites = new Table([['Name', 'Office'], ...Array.from({length: 5}, () => [name(), ''])], [4005, 5730]);
    const agenda = new Cell([new Para('', listAgenda ? T.LIST_ITEM : T.PARAGRAPH), '', '']);
    const grid = new Table([['SUBJECT:', '', ''], ['DATE:', '', ''], ['TIME:', '', ''],
      ['VENUE:', '', ''], ['AGENDA:', '', agenda]], [1365, 735, 7275]);
    const end = new Para('\t'); end.attrs.pageBreak = true;
    return ['______________', 'NOTICE OF MEETING', '  ', invites, '', 'FROM: SOURCE HEAD MUST GO',
      'SOURCE TITLE MUST GO', 'SOURCE OFFICE MUST GO', '', grid, end];
  }
  return new Body(first().concat(first(), ['', '']));
}
function original() {
  const first = ['', '________________', 'MEMORANDUM', '', 'FOR:\t', '', '', '',
    'FROM:\tSOURCE HEAD MUST GO', 'SOURCE TITLE MUST GO', 'SOURCE OFFICE MUST GO', '', 'SUBJECT:\t', '___________',
    '[Reiteration of Subject]', '[Rationale of Invitation]',
    '[Further details of activity or event, e.g. date, venue, number of requested participants]',
    '[Contact details of assigned staff] ', 'Thank you very much. ', ''];
  return new Body(first.concat(first.slice(1), [new Table([['Initials', 'SOURCE REVIEWER MUST GO']], [825, 4035]), '']));
}
function concept() {
  return new Body(['CONCEPT NOTE', '[Name of Activity / Event / Technical Assistance]', '',
    'Background and Rationale', '', '', 'Objectives', '', 'Expected Outputs', '', '', 'Participants',
    new Table([['Participant', 'Number'], ['', ''], ['', ''], ['', ''], ['', ''], ['Estimated Total', '']], [7695, 1200]),
    '', '', 'Methodology', '', 'Operational Details',
    new Table(['Title', 'Date/Duration', 'Venue', 'Participants', 'Facilitators', 'Budget and Source'].map(x => [x, '']), [1850, 7370]),
    '', 'Proposed Program of Activities', new Table([['Day', 'Activity'], ['Day 1', ''], ['Day 2', '']], [1215, 7995]),
    '', 'Prepared by:        Noted by:', '', '', 'SOURCE STAFF\tSOURCE SUPERVISOR', 'Designation\tDesignation', '',
    'Recommended by:', '', '', 'SOURCE DIRECTOR', 'SOURCE DIRECTOR TITLE', 'SOURCE DIRECTOR UNIT', '', '',
    'Approved by:', '', '', 'SOURCE APPROVER', 'SOURCE APPROVER TITLE', 'SOURCE APPROVER UNIT', '']);
}
function program() {
  return new Body(['', 'Activity: SOURCE ACTIVITY', 'Tentative Program Flow:',
    new Table([['Date/Time', 'Topic/Activity', 'Person Responsible'], ['SOURCE MERGED DAY'],
      ['SOURCE TIME', 'SOURCE SCHEDULE', 'SOURCE PERSON'], ['SOURCE MERGED DAY 2'],
      ['SOURCE TIME 2', 'SOURCE SCHEDULE 2', 'SOURCE PERSON 2']], [2370, 4575, 2415]), '']);
}
function splitApi(ctx, selected, drift = false) {
  // The Blank holds the concept note and the program page in two tabs; the legacy `body` shows only the first.
  const dim = magnitude => ({magnitude, unit: 'PT'});
  function tab(tabId, headerId, footerMargin, text) {
    return {tabProperties: {tabId}, documentTab: {
      documentStyle: {documentSize: {width: dim(612), height: dim(792)}, marginTop: dim(72), marginFooter: dim(footerMargin),
        useFirstPageHeaderFooter: true, firstPageHeaderId: headerId},
      headers: {[headerId]: {content: [{paragraph: {positionedObjectIds: ['IMG_' + tabId],
        elements: [{textRun: {content: text}}]}}]}},
      footers: {},
      positionedObjects: {['IMG_' + tabId]: {objectId: 'IMG_' + tabId, positionedObjectProperties: {embeddedObject: {
        size: {width: dim(75)}, imageProperties: {contentUri: 'temporary-image-url'}}}}},
      body: {content: [{startIndex: 0, endIndex: 1, sectionBreak: {sectionStyle: {}}}, {startIndex: 1, endIndex: 500, paragraph: {}}]}}};
  }
  const base = {tabs: [tab('t.0', 'H1', 21.6, 'OFFICE HEADER'), tab('t.1', 'H2', 36, 'PROGRAM HEADER')]};
  const requests = []; let after = null;
  ctx.Docs = {Documents: {
    get(id, options) {
      if (!options || !options.includeTabsContent) throw new Error('tabs must be requested');
      return JSON.parse(JSON.stringify(after || base));
    },
    batchUpdate(batch) {
      requests.push(...batch.requests);
      const dropId = batch.requests[0].deleteTab.tabId;
      after = JSON.parse(JSON.stringify(base));
      after.tabs = after.tabs.filter(t => t.tabProperties.tabId !== dropId);
      const kept = after.tabs[0].documentTab, headerId = selected ? 'H2' : 'H1';
      if (drift === true || drift === 'header') kept.headers[headerId].content[0].paragraph.elements[0].textRun.content = 'CHANGED HEADER';
      if (drift === 'image') Object.values(kept.positionedObjects)[0].positionedObjectProperties.embeddedObject.size.width.magnitude = 100;
      if (drift === 'wrong_section') after.tabs[0].tabProperties.tabId = 't.other';
      if (drift === 'paper') kept.documentStyle.documentSize.width.magnitude = 700;
    }
  }};
  return requests;
}
function letter() {
  function original() {
    const addressee = new Para('[NAME OF HEAD]\n[Name of Agency]\n[Address of Agency]');
    addressee.runs = [{text: '[NAME OF HEAD]', bold: true}, {text: '\n[Name of Agency]\n[Address of Agency]', bold: false}];
    return ['[Date]', addressee, 'Subject: ', 'Dear [Head]:', '[Brief purpose of letter or invitation]',
      '[Purpose of activity]', '[Expanded reiteration of purpose of letter or invitation, e.g. representatives]',
      '[Contact details of staff or personnel]', 'Thank you very much.', 'Very truly yours,', '',
      '[NAME OF HEAD OF OFFICE OR CLUSTER LEAD]', '[Designation]', '', ''];
  }
  return new Body(original().concat(original()));
}
function briefer() {
  const labels = ['I. Subject', 'II. Requested Action', 'III. Background/ Rational / Legal Basis',
    'IV. Key Outputs / Expected Output / Attachments', 'V. Participants / Key Stakeholders ', 'VI. Date/Venue/ References'];
  const table = new Table([[' EXECUTIVE BRIEFER', ''], ...labels.map(label => [label, '']),
    ['VI. Prepared by', new Cell(['', 'Name of Staff', 'Designation', '', 'Noted by:', '', 'Name of Supervisor', 'Designation'])],
    ['Approved by', new Cell(['', '', 'SOURCE HEAD MUST GO', 'SOURCE TITLE MUST GO', 'SOURCE UNIT MUST GO'])]], [2445, 8475]);
  const lead = new Para(''); lead.attrs.indentStart = -27;
  return new Body(['', lead, table, '']);
}
function context(body, opts = {}) {
  const key = opts.key || 'invitation';
  const props = { ['TPL_' + key]: opts.existing || 'OLD' }, writes = [], docs = {};
  if (opts.marked) props['TPLF_' + key] = props['TPL_' + key];
  docs.CANDIDATE = body;
  docs.OLD = opts.existingBody || new Body(['old drawn template']);
  const document = id => ({ getBody: () => { if (!docs[id]) throw Error('missing doc'); return docs[id]; }, saveAndClose() {} });
  let copies = 0;
  const iter = xs => ({ hasNext: () => xs.length > 0, next: () => xs.shift() });
  const ctx = {
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => props[k], setProperties: x => { writes.push(x); Object.assign(props, x); } }) },
    DocumentApp: { ElementType: T, GlyphType: { BULLET: 'bullet' }, openById: document },
    DriveApp: { getFolderById: id => id === '1HU-MCk_csQhYmIs_5g1HqKNZ3DIbPVy4'
      ? { getFilesByName: () => iter([{ getId: () => 'SOURCE' }]) }
      : { getFoldersByName: () => iter([{ getId: () => 'OUTPUT' }]) } },
    Drive: { Files: { copy: (request, id) => { copies++; if (id !== 'SOURCE' || request.parents[0] !== 'OUTPUT') throw Error('wrong source'); return { id: 'CANDIDATE' }; } } },
    Logger: { log() {} }
  };
  vm.createContext(ctx); vm.runInContext(load('activity_office_templates.gs'), ctx);
  if (opts.missing) ctx.ao_missing_ = () => ['missing_marker'];
  return { ctx, props, writes, document, copies: () => copies };
}
const body = original(), env = context(body);
const report = env.ctx.makeOfficeTemplates('invitation');
const output = {
  built: { report, props: env.props, writes: env.writes, text: body.getText(),
    paragraphs: body.children.map(p => ({ text: p.text, bold: p.bold, type: p.type, glyph: p.glyph, attrs: p.attrs })),
    expect: vm.runInContext('AO_TEMPLATES[0].expect', env.ctx) },
  failures: []
};
for (const mode of ['changed', 'missing']) {
  const b = original(); if (mode === 'changed') b.children[14].text = 'unexpected source';
  const e = context(b, { missing: mode === 'missing' });
  output.failures.push({ report: e.ctx.makeOfficeTemplates('invitation'), writes: e.writes, active: e.props.TPL_invitation });
}
const kept = context(original(), { existing: 'OLD', marked: true, existingBody: body });
output.kept = { report: kept.ctx.makeOfficeTemplates('invitation'), copies: kept.copies() };
const rebuild = context(original(), { existing: 'OLD', marked: true, existingBody: body });
output.forced = { report: rebuild.ctx.makeOfficeTemplates('invitation', true), copies: rebuild.copies() };
const unknown = context(original());
output.unselected = { report: unknown.ctx.makeOfficeTemplates('not_supported'), writes: unknown.writes };
// Real relay group expansion: preserve different attributes and keep the FOR label once.
vm.runInContext(load('travel_docs.gs'), env.ctx);
const groupBody = new Body(['FOR:\t{{for_name}}', '{{for_title}}', '{{for_office}}', 'FROM: head']);
groupBody.children[0].bold = true; groupBody.children[1].attrs = { indentStart: 180 };
env.ctx.applyAddressees_(groupBody, [
  { for_name: 'FIRST PERSON', for_title: 'First title', for_office: 'First office' },
  { for_name: 'SECOND PERSON', for_title: 'Second title', for_office: 'Second office' }
]);
output.groups = groupBody.children.map(p => ({ text: p.text, bold: p.bold, attrs: p.attrs }));
vm.runInContext(load('activity_templates.gs'), kept.ctx);
kept.ctx.Utilities = { formatDate: () => 'stamp' };
vm.runInContext('AT_TEMPLATES.splice(0, AT_TEMPLATES.length, AT_TEMPLATES.filter(t => t.key === "invitation")[0])', kept.ctx);
output.legacyRebuild = kept.ctx.rebuildActivityTemplates();
const nomBody = notice(), nom = context(nomBody, {key: 'notice_of_meeting'});
const nomReport = nom.ctx.makeOfficeNoticeTemplate();
const snapshot = body => body.children.map(p => p instanceof Table
  ? {type: 'table', grid: p.grid, columnWidths: p.columnWidths, rows: p.rows.map(r => r.cells.map(c => c.getText()))}
  : {type: p.type, text: p.text, attrs: p.attrs, runs: p.runs ? p.runs.map(run => ({...run})) : undefined});
output.notice = {report: nomReport, writes: nom.writes, children: snapshot(nomBody),
  expect: vm.runInContext('AO_TEMPLATES[1].expect', nom.ctx), text: nomBody.getText()};
output.noticeFailures = [];
for (const mode of ['grid', 'populated', 'wrapped', 'duplicate']) {
  const b = notice();
  if (mode === 'grid') b.children[9].getCell(0, 0).children[0].text = 'CHANGED:';
  if (mode === 'populated') b.children[3].getCell(1, 0).children[0].text = 'Unexpected person';
  if (mode === 'wrapped') b.children[3] = new Para('Name Office', 'UNSUPPORTED');
  if (mode === 'duplicate') b.children[12].text = 'changed title';
  const e = context(b, {key: 'notice_of_meeting'});
  output.noticeFailures.push({report: e.ctx.makeOfficeNoticeTemplate(), writes: e.writes, active: e.props.TPL_notice_of_meeting});
}
const plainAgenda = notice(false), pa = context(plainAgenda, {key: 'notice_of_meeting'});
output.plainAgenda = pa.ctx.makeOfficeNoticeTemplate();
vm.runInContext(load('travel_docs.gs'), nom.ctx);
nom.ctx.applyRows_(nomBody, {invitees: {marker: 'inv_name', data: [
  {inv_name: 'Person One', inv_office: 'Office One'}, {inv_name: 'Person Two', inv_office: ''}
]}});
nom.ctx.applyBlocks_(nomBody, {agenda: ['First topic', 'Second topic']});
nom.ctx.applyFields_(nomBody, {date: 'Today', head_name: 'CONFIGURED HEAD', head_title: 'Configured title',
  unit_name: 'Bureau', subject: 'Meeting subject', meeting_date: 'Meeting day', meeting_time: '9:00 AM', venue: 'Room', meeting_link: ''});
output.noticeFilled = {children: snapshot(nomBody), text: nomBody.getText()};
const agendaCell = nomBody.children[9].getCell(4, 2);
output.noticeAgenda = agendaCell.children.map(p => ({text: p.text, type: p.type, attrs: p.attrs}));
output.concepts = {};
for (const key of ['concept_note', 'program_flow']) {
  const body = key === 'concept_note' ? concept() : program();
  const env = context(body, {key});
  const requests = splitApi(env.ctx, key === 'program_flow' ? 1 : 0);
  const report = env.ctx.makeOfficeTemplates(key);
  output.concepts[key] = {report, writes: env.writes, text: body.getText(), children: snapshot(body), requests,
    expect: vm.runInContext('AO_TEMPLATES.find(t => t.key === "' + key + '").expect', env.ctx)};
  vm.runInContext(load('travel_docs.gs'), env.ctx);
  if (key === 'concept_note') {
    env.ctx.applyRows_(body, {participants: {marker: 'pt_group', data: [{pt_group: 'Person One', pt_count: '1'}, {pt_group: 'Person Two', pt_count: '1'}]},
      program: {marker: 'pd_day', data: [{pd_day: 'Day 1', pd_text: 'First activities'}, {pd_day: 'Day 2', pd_text: 'Second activities'}]}});
    env.ctx.applyBlocks_(body, {background: ['Background'], objectives: ['Objective'], outputs: ['Output'], methodology: ['Method'], participants_note: ['Confirm count']});
    const fields = Object.fromEntries(output.concepts[key].expect.filter(k => !['pt_group', 'pt_count', 'pd_day', 'pd_text'].includes(k)).map(k => [k, k === 'participant_count' ? '2' : 'Value']));
    env.ctx.applyFields_(body, fields);
  } else {
    env.ctx.applyRows_(body, {flow: {marker: 'pf_time', data: [{pf_time: 'Day 1', pf_topic: '', pf_person: ''}, {pf_time: '', pf_topic: '', pf_person: ''}]}});
    env.ctx.applyFields_(body, {title: 'Current activity'});
  }
  output.concepts[key].filled = {text: body.getText(), children: snapshot(body)};
}
output.conceptFailures = [];
for (const mode of ['header', 'image', 'paper', 'wrong_section', 'prose', 'table', 'program']) {
  const key = ['program', 'wrong_section'].includes(mode) ? 'program_flow' : 'concept_note';
  const body = key === 'program_flow' ? program() : concept();
  if (mode === 'prose') body.children[4].text = 'Unexpected prose';
  if (mode === 'table') body.children[12].getCell(1, 0).children[0].text = 'Unexpected participant';
  if (mode === 'program') body.children[3].getCell(0, 0).children[0].text = 'CHANGED HEADER';
  const env = context(body, {key}); splitApi(env.ctx, key === 'program_flow' ? 1 : 0, ['header', 'image', 'paper', 'wrong_section'].includes(mode) ? mode : false);
  output.conceptFailures.push({report: env.ctx.makeOfficeTemplates(key), writes: env.writes});
}
const letterBody = letter(), letterEnv = context(letterBody, {key: 'invitation_external'});
output.letter = {report: letterEnv.ctx.makeOfficeExternalLetterTemplate(), writes: letterEnv.writes,
  expect: vm.runInContext('AO_TEMPLATES.find(t => t.key === "invitation_external").expect', letterEnv.ctx),
  text: letterBody.getText(), children: snapshot(letterBody)};
vm.runInContext(load('travel_docs.gs'), letterEnv.ctx);
letterEnv.ctx.applyBlocks_(letterBody, {letter_opening: ['Opening'], activity_purpose: ['Purpose'],
  letter_details: ['Activity details', 'Requested representatives'], contact_details: ['Contact']});
letterEnv.ctx.applyFields_(letterBody, {date: 'Current date', subject: 'Current subject', salutation_name: 'Recipient',
  addressee_name: 'RECIPIENT', addressee_title: 'Recipient title', addressee_agency: 'Named agency',
  addressee_address: 'Known address', head_name: 'CONFIGURED HEAD', head_title: 'Configured title'});
output.letter.filled = {text: letterBody.getText(), children: snapshot(letterBody)};
output.letterFailures = [];
for (const mode of ['purpose', 'duplicate', 'addressee', 'element']) {
  const body = letter();
  if (mode === 'purpose') body.children[5].text = 'Unexpected purpose';
  if (mode === 'duplicate') body.children[15].text = 'Not date';
  if (mode === 'addressee') body.children[1].text += ' UNEXPECTED PERSON';
  if (mode === 'element') body.children[4].type = 'UNSUPPORTED';
  const env = context(body, {key: 'invitation_external'});
  output.letterFailures.push({report: env.ctx.makeOfficeExternalLetterTemplate(), writes: env.writes,
    active: env.props.TPL_invitation_external});
}
const brieferBody = briefer(), be = context(brieferBody, {key: 'executive_briefer'});
output.briefer = {report: be.ctx.makeOfficeBrieferTemplate(), writes: be.writes, text: brieferBody.getText(), children: snapshot(brieferBody),
  expect: vm.runInContext('AO_TEMPLATES.find(t => t.key === "executive_briefer").expect', be.ctx)};
vm.runInContext(load('travel_docs.gs'), be.ctx);
be.ctx.applyBlocks_(brieferBody, {requested_action: ['Editable action'], background: ['Background'], outputs: ['Output one', 'Output two'],
  participants: ['Person one', 'Visitor two'], date_venue_references: ['Date: Today', 'Venue: Room', 'References: Known reference']});
be.ctx.applyFields_(brieferBody, {subject: 'Current activity', prepared_by: 'DRAFTER', prepared_title: 'Staff title',
  noted_by_name: 'REVIEWER', noted_by_title: 'Reviewer title', head_name: 'CONFIGURED HEAD', head_title: 'Director', approved_unit: 'Bureau'});
output.briefer.filled = {text: brieferBody.getText(), children: snapshot(brieferBody)};
output.brieferFailures = [];
for (const mode of ['label', 'title', 'data', 'signature', 'body']) {
  const body = briefer();
  if (mode === 'label') body.children[2].getCell(7, 0).children[0].text = 'VII. Prepared by';
  if (mode === 'title') body.children[2].getRow(0).cells.push(new Cell(['extra title cell']));
  if (mode === 'data') body.children[2].getCell(1, 1).children[0].text = 'Unexpected existing subject';
  if (mode === 'signature') body.children[2].getCell(7, 1).children[1].text = 'Unknown staff slot';
  if (mode === 'body') body.children[0].text = 'Unexpected body';
  const env = context(body, {key: 'executive_briefer'});
  output.brieferFailures.push({report: env.ctx.makeOfficeBrieferTemplate(), writes: env.writes, active: env.props.TPL_executive_briefer});
}
function officeFrameApi(ctx, mode = '') {
  const dim = magnitude => ({magnitude, unit: 'PT'});
  const frame = {
    documentStyle: {documentSize: {width: dim(612), height: dim(792)},
      marginTop: dim(72), marginBottom: dim(72), marginLeft: dim(72), marginRight: dim(72),
      marginHeader: dim(36), marginFooter: dim(36), useFirstPageHeaderFooter: true},
    body: {content: [{startIndex: 0, endIndex: 1, sectionBreak: {sectionStyle: {
      firstPageHeaderId: 'HEADER', firstPageFooterId: 'FOOTER'
    }}}]},
    headers: {HEADER: {content: [{paragraph: {positionedObjectIds: ['LOGO1', 'LOGO2'], elements: [{textRun: {content: 'OFFICE LETTERHEAD'}}]}}]}},
    footers: {FOOTER: {content: [{paragraph: {elements: [{textRun: {content: 'ORIGINAL FOOTER 651-7800'}}]}}]}},
    positionedObjects: {LOGO1: {positionedObjectProperties: {embeddedObject: {size: {width: dim(75.375), height: dim(75.375)}}}},
      LOGO2: {positionedObjectProperties: {embeddedObject: {size: {width: dim(103.2), height: dim(105.6)}}}}}
  };
  let reads = 0;
  ctx.Docs = {Documents: {get() {
    reads++;
    const result = JSON.parse(JSON.stringify(frame));
    if (reads > 1) {
      if (mode === 'paper') result.documentStyle.documentSize.width = dim(600);
      if (mode === 'margin') result.documentStyle.marginLeft = dim(70);
      if (mode === 'first') result.documentStyle.useFirstPageHeaderFooter = false;
      if (mode === 'header') result.headers.HEADER.content[0].paragraph.elements[0].textRun.content = 'CHANGED HEADER';
      if (mode === 'footer') result.footers.FOOTER.content[0].paragraph.elements[0].textRun.content = 'CHANGED FOOTER';
      if (mode === 'logo') result.positionedObjects.LOGO1.positionedObjectProperties.embeddedObject.size.width = dim(90);
      if (mode === 'missing_image') delete result.positionedObjects.LOGO1;
      if (mode === 'section') result.body.content.push({sectionBreak: {sectionStyle: {}}});
    }
    return result;
  }}};
  return {frame, reads: () => reads};
}
output.officeBodies = {};
for (const key of ['dpo', 'minutes']) {
  const body = original(), env = context(body, {key});
  vm.runInContext(load('activity_templates.gs'), env.ctx);
  env.ctx.DocumentApp.HorizontalAlignment = {RIGHT: 'right', CENTER: 'center', JUSTIFY: 'justify'};
  const api = officeFrameApi(env.ctx);
  const report = env.ctx.makeOfficeTemplates(key);
  output.officeBodies[key] = {report, writes: env.writes, text: body.getText(), children: snapshot(body), clears: body.clears,
    font: body.font, size: body.size, reads: api.reads(),
    expect: vm.runInContext('AO_TEMPLATES.find(t => t.key === "' + key + '").expect', env.ctx)};
  vm.runInContext(load('travel_docs.gs'), env.ctx);
  const fields = Object.fromEntries(output.officeBodies[key].expect.map(k => [k, 'Value']));
  if (key === 'dpo') {
    env.ctx.applyRows_(body, {personnel: {marker: 'p_name', data: [{p_name: 'Person One', p_position: 'Role One'}, {p_name: 'Person Two', p_position: 'Role Two'}]}});
    env.ctx.applyFields_(body, fields);
  } else {
    env.ctx.applyRows_(body, {actions: {marker: 'm_action', data: [{m_action: 'Action', m_who: 'Person', m_due: 'Date'}]}});
    env.ctx.applyBlocks_(body, {attendees: ['Person One', 'Person Two'], agenda: ['Agenda'], discussion: ['Discussion'], next_steps: ['Next step']});
    env.ctx.applyFields_(body, fields);
  }
  output.officeBodies[key].filled = {text: body.getText(), children: snapshot(body)};
}
output.officeBodyFailures = [];
for (const mode of ['paper', 'margin', 'first', 'header', 'footer', 'logo', 'missing_image', 'section', 'source', 'missing_placeholder']) {
  const body = original(), env = context(body, {key: 'dpo', missing: mode === 'missing_placeholder'});
  vm.runInContext(load('activity_templates.gs'), env.ctx);
  env.ctx.DocumentApp.HorizontalAlignment = {RIGHT: 'right', CENTER: 'center', JUSTIFY: 'justify'};
  if (mode === 'source') body.children[14].text = 'UNEXPECTED SOURCE';
  officeFrameApi(env.ctx, mode);
  output.officeBodyFailures.push({report: env.ctx.makeOfficeTemplates('dpo'), writes: env.writes, active: env.props.TPL_dpo});
}
console.log(JSON.stringify(output));
