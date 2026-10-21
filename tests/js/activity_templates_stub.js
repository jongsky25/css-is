// A fake of just enough of the Docs API to run all four template builders (DPO, invitation, concept note, program flow) and report the {{placeholders}} each writes.
// Usage: node activity_templates_stub.js apps_script/activity_templates.gs [apps_script/activity_logos.gs]
// Also reports, per template, the pictures it embeds (decoded PNG sizes) and whether it adds the address footer.
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
function newBody() { return { paragraphs: [],
  appendParagraph(t) { log.push('P: ' + t); const p = mk('p', t); this.paragraphs.push(p); return p; },
  appendTable(c) { log.push('TABLE: ' + JSON.stringify(c)); const cell = mk('cell'); return { setBorderWidth() {}, editAsText: () => mk('t'), setColumnWidth(c, w) { log.push('WIDTH: ' + c + ' ' + w); }, getRow: () => mk('row'), getCell: () => cell }; },
  appendHorizontalRule() { return mk('h'); },
  editAsText: () => mk('t'), getChild: () => mk('p', 'x'), removeChild() { } }; }
const doc = { addFooter() { return { setText(t) { log.push('FOOTER: ' + t); }, appendParagraph(t) { log.push('FOOTER: ' + t); return mk('p'); },
  getParagraphs: () => [mk('p')], editAsText: () => mk('t') }; } };
global.DocumentApp = { HorizontalAlignment: { CENTER: 'C', RIGHT: 'R', JUSTIFY: 'J' }, ElementType: { PARAGRAPH: 'PARAGRAPH' } };
global.Utilities = { base64Decode: (b) => Buffer.from(b, 'base64'),
  newBlob: (bytes, type, name) => { log.push('IMAGE: ' + name + ' ' + type + ' ' + bytes.length); return { bytes, type, name }; } };
const logos = process.argv[3] ? fs.readFileSync(process.argv[3], 'utf8') + '\n' : '';
const src = logos + fs.readFileSync(process.argv[2], 'utf8') + '\n;module.exports = { AT_TEMPLATES, at_buildDpo_, at_buildInvitation_, at_buildConceptNote_, at_buildProgramFlow_ };';
const m = new Function('module', 'DocumentApp', 'Utilities', src + '\nreturn module.exports;')({ exports: {} }, global.DocumentApp, global.Utilities);
const out = {};
[['dpo', m.at_buildDpo_], ['invitation', m.at_buildInvitation_], ['concept_note', m.at_buildConceptNote_], ['program_flow', m.at_buildProgramFlow_]].forEach(function (x) {
  log.length = 0;
  x[1](newBody(), doc);
  const text = log.join('\n');
  const tpl = m.AT_TEMPLATES.find(t => t.key === x[0]);
  out[x[0]] = { expect: tpl.expect,
                found: Array.from(new Set((text.match(/\{\{[a-z0-9_]+\}\}/g) || []).map(y => y.slice(2, -2)))),
                missing: tpl.expect.filter(k => text.indexOf('{{' + k + '}}') < 0),
                images: (text.match(/IMAGE: \S+ image\/png \d+/g) || []), footer: /FOOTER: Building 1/.test(text),
                widths: (text.match(/WIDTH: \d+ \d+/g) || []).map(w => +w.split(' ')[2]) };
});
console.log(JSON.stringify(out));
