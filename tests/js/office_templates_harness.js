// Test converter mapping, publication and repeated addressees with synthetic source text.
const fs = require('fs'), vm = require('vm'), path = require('path');
const load = name => fs.readFileSync(path.resolve(__dirname, '../../apps_script/' + name), 'utf8');
const T = { PARAGRAPH: 'P', LIST_ITEM: 'L', TABLE: 'T' };
class Para {
  constructor(text, type = T.PARAGRAPH) { Object.assign(this, { text, type, attrs: { spacing: 12 }, bold: false }); }
  getType() { return this.type; }
  asParagraph() { if (this.type !== T.PARAGRAPH) throw Error('not a paragraph'); return this; }
  getText() { return this.text; }
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
  getText() { return this.children.map(p => p.text).join('\n'); }
  insertParagraph(i, p) { if (typeof p === 'string') p = new Para(p); this.children.splice(i, 0, p); p.parent = this; return p; }
  insertListItem(i, text) { return this.insertParagraph(i, new Para(text, T.LIST_ITEM)); }
  findText(pattern) { const p = this.children.find(p => new RegExp(pattern).test(p.text)); return p ? { getElement: () => ({ getParent: () => p }) } : null; }
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
  const props = { TPL_invitation: opts.existing || 'OLD' }, writes = [], docs = {};
  if (opts.marked) props.TPLF_invitation = props.TPL_invitation;
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
const report = env.ctx.makeOfficeTemplates();
const output = {
  built: { report, props: env.props, writes: env.writes, text: body.getText(),
    paragraphs: body.children.map(p => ({ text: p.text, bold: p.bold, type: p.type, glyph: p.glyph, attrs: p.attrs })),
    expect: vm.runInContext('AO_TEMPLATES[0].expect', env.ctx) },
  failures: []
};
for (const mode of ['changed', 'missing']) {
  const b = original(); if (mode === 'changed') b.children[14].text = 'unexpected source';
  const e = context(b, { missing: mode === 'missing' });
  output.failures.push({ report: e.ctx.makeOfficeTemplates(), writes: e.writes, active: e.props.TPL_invitation });
}
const kept = context(original(), { existing: 'OLD', marked: true, existingBody: body });
output.kept = { report: kept.ctx.makeOfficeTemplates(), copies: kept.copies() };
const rebuild = context(original(), { existing: 'OLD', marked: true, existingBody: body });
output.forced = { report: rebuild.ctx.makeOfficeTemplates('invitation', true), copies: rebuild.copies() };
const unknown = context(original());
output.unselected = { report: unknown.ctx.makeOfficeTemplates('notice_of_meeting'), writes: unknown.writes };
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
console.log(JSON.stringify(output));
