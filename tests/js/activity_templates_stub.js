// A fake of just enough of the Docs API to run the DPO template builder and report the {{placeholders}} it writes.
// Usage: node activity_templates_stub.js apps_script/activity_templates.gs
const fs = require('fs'); const log = [];
function mk(kind, text) {
  const o = { kind, text: text || '', children: [] };
  const chain = new Proxy(o, { get(t, k) {
    if (k in t) return t[k];
    if (k === 'editAsText') return () => ({ setBold() { return this; }, setUnderline() { return this; }, setFontFamily() { return this; }, setFontSize() { return this; }, getText: () => t.text });
    if (k === 'asParagraph') return () => chain;
    if (k === 'getChild') return () => chain;
    if (k === 'getType') return () => 'PARAGRAPH';
    if (k === 'getText') return () => t.text;
    if (k === 'setText') return (x) => { t.text = x; return chain; };
    return () => chain;           // any other setter just returns the same object
  }});
  return chain;
}
const body = { paragraphs: [],
  appendParagraph(t) { log.push('P: ' + t); const p = mk('p', t); this.paragraphs.push(p); return p; },
  appendTable(c) { log.push('TABLE: ' + JSON.stringify(c)); const cell = mk('cell'); return { setBorderWidth() {}, getRow: () => mk('row'), getCell: () => cell }; },
  editAsText: () => mk('t'), getChild: () => mk('p', 'x'), removeChild() { log.push('removed leading empty paragraph?'); } };
const doc = { addFooter() { return { setText(t) { log.push('FOOTER: ' + t); }, appendParagraph(t) { log.push('FOOTER: ' + t); return mk('p'); },
  getParagraphs: () => [mk('p')], editAsText: () => mk('t') }; } };
global.DocumentApp = { HorizontalAlignment: { CENTER: 'C', RIGHT: 'R', JUSTIFY: 'J' }, ElementType: { PARAGRAPH: 'PARAGRAPH' } };
const src = fs.readFileSync(process.argv[2], 'utf8') + '\n;module.exports = { AT_TEMPLATES, at_buildDpo_, at_buildInvitation_ };';
const m = new Function('module', 'DocumentApp', src + '\nreturn module.exports;')({ exports: {} }, global.DocumentApp);
m.at_buildDpo_(body, doc);
const text = log.join('\n');
const dpo = m.AT_TEMPLATES.find(t => t.key === 'dpo');
const missing = dpo.expect.filter(k => text.indexOf('{{' + k + '}}') < 0);
const found = Array.from(new Set((text.match(/\{\{[a-z0-9_]+\}\}/g) || []).map(x => x.slice(2, -2))));
console.log(JSON.stringify({ expect: dpo.expect, found: found, missing: missing }));
