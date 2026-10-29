// Runs the REAL formatting code from apps_script/travel_docs.gs against small fakes of the Docs and Sheets APIs.
// Prints JSON for the Python test to check.
const fs = require('fs'), vm = require('vm'), path = require('path');
const root = path.resolve(__dirname, '..', '..');

const ElementType = { PARAGRAPH: 'P', LIST_ITEM: 'L', TABLE: 'T', TABLE_ROW: 'R', TABLE_CELL: 'C' };
const HorizontalAlignment = { LEFT: 'left', CENTER: 'center', RIGHT: 'right', JUSTIFY: 'justify' };
const ParagraphHeading = { NORMAL: 'normal', HEADING1: 'h1' };

class Para {
  constructor(text, o) { Object.assign(this, { text, bold: false, align: null, heading: 'normal', font: null, size: null }, o || {}); }
  getType() { return ElementType.PARAGRAPH; }
  getText() { return this.text; }
  getAlignment() { return this.align; }
  setAlignment(a) { this.align = a; return this; }
  getHeading() { return this.heading; }
  setFontFamily(f) { this.font = f; return this; }
  setFontSize(n) { this.size = n; return this; }
  editAsText() { const p = this; return { isBold: () => p.bold, setBold: (b) => { p.bold = b; return this; }, setText: (t) => { p.text = t; return this; } }; }
}
class Box {
  constructor(type, kids) { this.type = type; this.kids = kids; }
  getType() { return this.type; }
  getNumChildren() { return this.kids.length; }
  getChild(i) { return this.kids[i]; }
}

class FakeRange {
  constructor(sh, r, c, nr, nc) { Object.assign(this, { sh, r, c, nr: nr || 1, nc: nc || 1 }); }
  each(fn) { for (let i = 0; i < this.nr; i++) for (let j = 0; j < this.nc; j++) fn(this.sh.at(this.r + i, this.c + j)); }
  setFontFamily(f) { this.each(x => { x.font = f; }); return this; }
  setFontSize(n) { this.each(x => { x.size = n; }); return this; }
  setFontWeight(w) { this.each(x => { x.weight = w; }); return this; }
  setValue(v) { this.each(x => { x.value = v; }); return this; }
  grid(key) { const out = []; for (let i = 0; i < this.nr; i++) { const row = []; for (let j = 0; j < this.nc; j++) row.push(this.sh.at(this.r + i, this.c + j)[key]); out.push(row); } return out; }
  getValues() { return this.grid('value'); }
  getFormulas() { return this.grid('formula'); }
  getFontWeights() { return this.grid('weight'); }
}
class FakeSheet {
  constructor(rows) { const width = Math.max(...rows.map(r => r.length)); rows = rows.map(r => r.concat(Array(width - r.length).fill(''))); this.cells = rows.map(r => r.map(v => (typeof v === 'object' && v !== null ? Object.assign({ formula: '', weight: 'normal', value: '' }, v) : { value: v, formula: '', weight: 'normal' }))); }
  at(r, c) { return this.cells[r - 1][c - 1]; }
  getDataRange() { return new FakeRange(this, 1, 1, this.cells.length, Math.max(...this.cells.map(r => r.length))); }
  getRange(r, c) { return new FakeRange(this, r, c, 1, 1); }
}

const ctx = { PropertiesService: { getScriptProperties: () => ({ getProperty: () => null }) }, console, DocumentApp: { ElementType, HorizontalAlignment, ParagraphHeading } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(root, 'apps_script', 'travel_docs.gs'), 'utf8'), ctx, { filename: 'travel_docs.gs' });

const out = {};
out.titles = ['CERTIFICATION OF EXPENSES NOT REQUIRING RECEIPTS', 'APPENDIX A', 'itinerary of travel', 'DPO and CENRR for the MC 114 trip',
  'JUNE ROSE A', 'POST-TRAVEL REPORT', 'APPENDIX 46 REIMBURSEMENT EXPENSE RECEIPT'].map(t => ctx.titleCase_(t));
out.looks = ['APPENDIX A', 'Name of Employee: DR. JUNE ROSE A. NAIG', 'MAR WYNN D. BELLO, MD', 'Taxi fare from Residence (Paco)', 'ab', ''].map(t => ctx.looksLikeTitle_(t));

const long = 'I hereby certify that the above expenses were incurred in the course of the travel and are true and correct.';
const paras = {
  title: new Para('POST TRAVEL REPORT', { bold: true, align: 'center' }),
  capsLeft: new Para('CERTIFICATE OF TRAVEL COMPLETED', { bold: true }),
  dpoTitle: new Para('DEPARTMENT PERSONNEL ORDER', { bold: true }),
  memoTitle: new Para('MEMORANDUM', { bold: true }),
  conceptTitle: new Para('CONCEPT NOTE', { bold: true }),
  noticeTitle: new Para('NOTICE OF MEETING', { bold: true }),
  minutesTitle: new Para('MINUTES OF THE MEETING', { bold: true }),
  brieferTitle: new Para('EXECUTIVE BRIEFER', { bold: true }),
  heading: new Para('overview of the trip', { heading: 'h1', bold: true }),
  body: new Para(long),
  bodyCentered: new Para(long, { align: 'center' }),
  bodyRight: new Para(long, { align: 'right' }),
  short: new Para('Noted by:'),
  name: new Para('MAR WYNN D. BELLO, MD, MPA', { bold: true, align: 'center' }),
  sentenceBold: new Para('NOTE THAT THIS IS BOLD AND CENTERED. IT HAS A FULL STOP', { bold: true, align: 'center' }),
  blank: new Para(''),
  cell: new Para(long),
};
const body = new Box('B', [paras.title, paras.capsLeft, paras.dpoTitle, paras.memoTitle, paras.conceptTitle, paras.noticeTitle, paras.minutesTitle, paras.brieferTitle, paras.heading, paras.body, paras.bodyCentered, paras.bodyRight, paras.short, paras.name, paras.sentenceBold,
  paras.blank, new Box(ElementType.TABLE, [new Box(ElementType.TABLE_ROW, [new Box(ElementType.TABLE_CELL, [paras.cell])])])]);
ctx.formatDoc_(body);
out.doc = {};
Object.keys(paras).forEach(k => { const p = paras[k]; out.doc[k] = { text: p.text, bold: p.bold, align: p.align, font: p.font, size: p.size }; });

const sheet = new FakeSheet([
  [{ value: 'CERTIFICATION OF EXPENSES NOT REQUIRING RECEIPTS', weight: 'bold' }],
  ['Name of Employee: Juan'],
  [{ value: 'TOTAL', weight: 'bold' }, 670, { value: '=SUM(A1)', formula: '=SUM(A1)', weight: 'bold' }],
  [{ value: 'MAR WYNN D. BELLO, MD', weight: 'bold' }],
]);
ctx.formatSheet_(sheet);
out.sheet = sheet.cells.map(r => r.map(c => ({ value: c.value, weight: c.weight, font: c.font, size: c.size })));
// formatting must never throw
ctx.formatDoc_({ getType: () => 'x', getNumChildren: () => { throw new Error('boom'); } });
ctx.formatSheet_({ getDataRange: () => { throw new Error('boom'); } });
console.log(JSON.stringify(out));
