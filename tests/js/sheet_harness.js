// Runs the REAL sheet code from apps_script/*.gs against a tiny fake of the Sheets API, on grids that
// copy the layout of the office's CENRR and RER forms. Prints JSON for the Python test to check.
const fs = require('fs'), vm = require('vm'), path = require('path');
const root = path.resolve(__dirname, '..', '..');

class FakeRange {
  constructor(sh, r, c, nr, nc) { Object.assign(this, { sh, r, c, nr: nr || 1, nc: nc || 1 }); }
  getValues() { const out = []; for (let i = 0; i < this.nr; i++) { const row = []; for (let j = 0; j < this.nc; j++) row.push(this.sh.cell(this.r + i, this.c + j)); out.push(row); } return out; }
  setValue(v) { this.sh.set(this.r, this.c, v); return this; }
  getValue() { return this.sh.cell(this.r, this.c); }
  setWrap() { return this; }
  setNumberFormat() { return this; }
  getRow() { return this.r; }
  copyTo(dest) { for (let i = 0; i < this.nr; i++) for (let j = 0; j < this.nc; j++) this.sh.set(dest.r + i, dest.c + j, this.sh.cell(this.r + i, this.c + j)); }
  createTextFinder(p) { return new FakeFinder(this.sh, p, this); }
}
class FakeFinder {
  constructor(sh, p, range) { this.sh = sh; this.p = p; this.range = range; this.rx = false; }
  useRegularExpression(b) { this.rx = b; return this; }
  re(flags) { return new RegExp(this.rx ? this.p.replace(/\\x\{00A0\}/g, '\\u00a0') : this.p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), flags); }
  cells() {
    const rg = this.range || new FakeRange(this.sh, 1, 1, this.sh.grid.length, this.sh.getLastColumn()), out = [];
    for (let i = 0; i < rg.nr; i++) for (let j = 0; j < rg.nc; j++) out.push([rg.r + i, rg.c + j]);
    return out;
  }
  findNext() { for (const [r, c] of this.cells()) if (this.re('').test(String(this.sh.cell(r, c)))) return new FakeRange(this.sh, r, c, 1, 1); return null; }
  replaceAllWith(s) { let n = 0; for (const [r, c] of this.cells()) { const v = String(this.sh.cell(r, c)); if (this.re('').test(v)) { this.sh.set(r, c, v.replace(this.re('g'), () => s)); n++; } } return n; }
}
class FakeSheet {
  constructor(rows) { this.grid = rows.map(r => r.slice()); }
  getLastColumn() { return Math.max(1, ...this.grid.map(r => r.length)); }
  cell(r, c) { const v = (this.grid[r - 1] || [])[c - 1]; return v === undefined ? '' : v; }
  set(r, c, v) { while (this.grid.length < r) this.grid.push([]); const row = this.grid[r - 1]; while (row.length < c) row.push(''); row[c - 1] = v; }
  getRange(r, c, nr, nc) { return new FakeRange(this, r, c, nr, nc); }
  insertRowsAfter(r, n) { for (let i = 0; i < n; i++) this.grid.splice(r, 0, []); }
  deleteRow(r) { this.grid.splice(r - 1, 1); }
  createTextFinder(p) { return new FakeFinder(this, p, null); }
  getDataRange() { return new FakeRange(this, 1, 1, this.grid.length, this.getLastColumn()); }
}

const CENRR = [
  ['Republic of the Philippines'], ['Department of Health'], ['CERTIFICATION OF EXPENSES NOT REQUIRING RECEIPTS'],
  ['Pursuant to COA Circular No. 2017-001 dated June 19, 2017'],
  ['Name of Employee: DR. JUNE ROSE A. NAIG', '', '', '', '', 'Employee No. 20240016'],
  ['Office: BLHSD'], ['Division: HSDD'], ['Paticulars', '', '', '', '', 'Amount (P)'],
  ['March 10, 2026'],
  ['Taxi fare from Residence (Paco, Manila) to Department of Health ', '', '', '', '', 300],
  ['TOTAL', '', '', '', '', 300], ['Purpose'],
  ['To attend the "Consultation and Writeshop" on March 10-13, 2026 per DPO No. 2026-0507'],
  ['I hereby certify that the above expenses are incurred'],
  ['', '', 'Certified Correct:', '', '', 'Noted by:'], ['Signature'],
  ['Printed Name', '', 'DR. JUNE ROSE A. NAIG', '', '', 'MAR WYNN D. BELLO, MD, MPA, CESO IV '],
  ['', '', 'Senior Health Program Officer', '', '', 'Director IV'], ['', '', 'Date', '', '', 'Date'],
];
const RER = [
  ['Appendix 46 REIMBURSEMENT EXPENSE RECEIPT'], ['Fund Cluster : ______________', '', 'Date : ______________'], ['RER No. : ____________'],
  ['RECEIVED from MR. RALIE JAY N. RAMOS'], ['ADMINISTRATIVE ASSISTANT III'],
  ['of ____________________________ (P__________)'], ['in payment for Taxi fare from ______________________________'],
  ['(Payments for subsistence, services,'], ['on ______________________'],
  ['in Attendance to the CY 2026 Measles-Rubella SIA\nscheduled on August 17-28, 2026 as per DPO\u00a0No. 2026-5451'],
  ['Name/Signature: ____________'], ['Address : ____________'],
];

function load(file, extra) {
  const ctx = Object.assign({ PropertiesService: { getScriptProperties: () => ({ getProperty: () => null }) }, console }, extra || {});
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(root, 'apps_script', file), 'utf8'), ctx, { filename: file });
  return ctx;
}

const out = {};
// 1. the relay's own sheet code
const relay = load('travel_docs.gs');
const sh = new FakeSheet(CENRR);
const maker = load('travel_templates.gs', { SpreadsheetApp: { openById: () => ({ getSheets: () => [sh] }) }, DocumentApp: { ElementType: {} } });
maker.tm_cenrr_('x');
out.cenrrTemplate = sh.grid.map(r => r.join('|'));
const rows = { items: { marker: 'p_date', data: [
  { p_date: 'September 1, 2026', p_text: 'Fare from Home to Airport by public transport', p_amount: '250' },
  { p_date: 'September 2, 2026', p_text: 'Fare from Airport to Home by public transport', p_amount: '300' },
  { p_date: 'September 4, 2026', p_text: 'Fare from Home to Venue by public transport', p_amount: '120' }] } };
relay.applyRowsSheet_(sh, rows);
relay.applyFieldsSheet_(sh, { employee_name: 'Juan Dela Cruz', employee_no: '12345', office: 'Manila', division: 'PLANNING', total: '670',
  purpose: 'attend Workshop', dates: 'September 01-04, 2026', dpo_ref: 'DPO No. 2026-123', printed_name: 'Juan Dela Cruz',
  designation: 'Nurse II', noted_by_name: 'Dr. Ana Reyes', noted_by_title: 'OIC-Director', not_a_field: 'x' });
out.cenrrFilled = sh.grid.map(r => r.join('|'));
const empty = new FakeSheet(maker.tm_cenrr_ && CENRR); maker.SpreadsheetApp.openById = () => ({ getSheets: () => [empty] });
maker.tm_cenrr_('x'); relay.applyRowsSheet_(empty, { items: { marker: 'p_date', data: [] } }); relay.applyFieldsSheet_(empty, {});
out.emptyRows = empty.grid.map(r => r.join('|'));
// 2. the RER template
const rer = new FakeSheet(RER);
maker.SpreadsheetApp.openById = () => ({ getSheets: () => [rer] });
maker.tm_rer_('x');
out.rerTemplate = rer.grid.map(r => r.join('|'));
relay.applyFieldsSheet_(rer, { payee_name: 'Juan', payee_designation: 'Nurse II', amount_words: 'Five Hundred Pesos', amount_figures: '500',
  ride_mode: 'Taxi', ride_from: 'Home', ride_to: 'Airport', ride_date: 'September 1, 2026', activity_title: 'Workshop', dpo_ref: 'DPO No. 2026-123' });
out.rerFilled = rer.grid.map(r => r.join('|'));
console.log(JSON.stringify(out));
