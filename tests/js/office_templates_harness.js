// Test converter mapping, publication and repeated addressees with synthetic source text.
const fs = require('fs'), vm = require('vm'), path = require('path');
const load = name => fs.readFileSync(path.resolve(__dirname, '../../apps_script/' + name), 'utf8');
const T = { PARAGRAPH: 'P', LIST_ITEM: 'L', TABLE: 'T', TABLE_ROW: 'R' };
class Para {
  constructor(text, type = T.PARAGRAPH) { Object.assign(this, { text, type, attrs: { spacing: 12 }, bold: false }); }
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
  replaceText(pattern, value) { this.text = this.text.replace(new RegExp(pattern, 'g'), () => value); return this; }
  editAsText() {
    const p = this;
    return {
      getText: () => p.text,
      insertText(i, value) { p.text = p.text.slice(0, i) + value + p.text.slice(i); return this; },
      deleteText(a, b) { p.text = p.text.slice(0, a) + p.text.slice(b + 1); return this; },
      setBold(value) { p.bold = value; return this; }
    };
  }
}
class Body {
  constructor(items) { this.children = items.map(x => typeof x === 'string' ? new Para(x) : x); this.children.forEach(p => p.parent = this); }
  getNumChildren() { return this.children.length; }
  getChild(i) { return this.children[i]; }
  getChildIndex(p) { return this.children.indexOf(p); }
  removeChild(p) { this.children.splice(this.getChildIndex(p), 1); }
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
  return new Body(first.concat(first.slice(1), [new Para('SOURCE REVIEWER MUST GO', T.TABLE), '']));
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
output.unselected = { report: unknown.ctx.makeOfficeTemplates('minutes'), writes: unknown.writes };
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
  ? {type: 'table', grid: p.grid, rows: p.rows.map(r => r.cells.map(c => c.getText()))}
  : {type: p.type, text: p.text, attrs: p.attrs});
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
console.log(JSON.stringify(output));
