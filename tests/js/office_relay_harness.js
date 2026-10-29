// Exercise the real block filler and generateDoc_ dispatch without Google services.
const fs = require('fs'), vm = require('vm'), path = require('path');
const source = fs.readFileSync(path.resolve(__dirname, '../../apps_script/travel_docs.gs'), 'utf8');
const T = { PARAGRAPH: 'P', LIST_ITEM: 'L' };
class Paragraph {
  constructor(text, type = T.PARAGRAPH) {
    Object.assign(this, { text, type, attrs: { indent: 36, spacing: 12 }, glyph: 'BULLET', nesting: 1, list: 'source-list' });
  }
  getType() { return this.type; }
  asParagraph() { if (this.type !== T.PARAGRAPH) throw Error('not paragraph'); return this; }
  asListItem() { if (this.type !== T.LIST_ITEM) throw Error('not list'); return this; }
  getParent() { return this.parent; }
  setText(text) { this.text = text; return this; }
  getAttributes() { return this.attrs; }
  setAttributes(attrs) { this.attrs = {...attrs}; return this; }
  copy() { return Object.assign(new Paragraph(this.text, this.type), this); }
  setListId(item) { this.list = item.list; return this; }
}
function block(type, lines) {
  const para = new Paragraph('{{agenda}}', type);
  const parent = {
    children: [new Paragraph('before'), para, new Paragraph('after')],
    getChildIndex: p => parent.children.indexOf(p),
    insertParagraph(i, text) { const p = new Paragraph(text); this.children.splice(i, 0, p); p.parent = this; return p; },
    insertListItem(i, p) { this.children.splice(i, 0, p); p.parent = this; return p; }
  };
  para.parent = parent;
  // findText also searches descendants, so parent can be a table cell.
  const body = { findText: () => ({ getElement: () => ({ getParent: () => para }) }) };
  const ctx = { PropertiesService: { getScriptProperties: () => ({}) }, DocumentApp: { ElementType: T } };
  vm.createContext(ctx); vm.runInContext(source, ctx);
  ctx.applyBlocks_(body, { agenda: lines });
  return parent.children.map(p => ({ text: p.text, type: p.type, attrs: p.attrs, glyph: p.glyph, nesting: p.nesting, list: p.list }));
}
function generate(marker, template = 'OFFICE', key = 'invitation') {
  const props = { TPL_invitation: template, TPL_travel_report: template, ROOT_FOLDER_ID: 'ROOT', TPLF_invitation: marker, TPLF_travel_report: marker };
  const p = { getProperty: k => props[k] || null };
  const para = new Paragraph('MEMORANDUM');
  para.font = 'Office font'; para.size = 10;
  const calls = [];
  const copy = { getId: () => 'COPY', setDescription() {} };
  const folder = { getFiles: () => ({ hasNext: () => false }) };
  const ctx = {
    PropertiesService: { getScriptProperties: () => p },
    DriveApp: {
      getFolderById: () => ({ getFoldersByName: () => ({ hasNext: () => true, next: () => folder }) }),
      getFileById: () => ({ getMimeType: () => 'application/vnd.google-apps.document', makeCopy: () => copy })
    },
    DocumentApp: { openById: () => ({ getBody: () => para, saveAndClose: () => calls.push('save') }) }
  };
  vm.createContext(ctx); vm.runInContext(source, ctx);
  ctx.applyRows_ = () => calls.push('rows');
  ctx.applyBlocks_ = () => calls.push('blocks');
  ctx.applyFields_ = () => calls.push('fields');
  ctx.formatDoc_ = body => { calls.push('format'); body.font = 'Times New Roman'; body.size = 12; };
  ctx.reportLetterhead_ = () => calls.push('report-letterhead');
  ctx.formatReport_ = () => calls.push('report-format');
  ctx.dropEmptyReportSections_ = () => calls.push('report-sections');
  ctx.doc_ = () => ({ ok: true });
  const result = ctx.generateDoc_({ template_key: key, folder_key: 'activities', request_id: 'r1', title: 'Draft' });
  return { result, calls, font: para.font, size: para.size };
}
console.log(JSON.stringify({
  list: block(T.LIST_ITEM, ['First', 'Second', 'Third']),
  emptyList: block(T.LIST_ITEM, []),
  paragraph: block(T.PARAGRAPH, ['First', 'Second']),
  office: generate('OFFICE'), unmarked: generate(null), stale: generate('OFFICE', 'RESTORED'),
  travel: generate(null, 'TRAVEL', 'travel_report')
}));
