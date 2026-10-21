// Runs the REAL addFileCopy_ from apps_script/travel_docs.gs against a small fake of the Apps Script document service and the
// Docs advanced service, then prints what happened as JSON for the Python test. The fake is deliberately simple (indexes are
// approximate) -- it checks the order of the calls, the copied content and the failure paths, not Google's own behaviour.
const fs = require('fs'), vm = require('vm'), path = require('path');
const root = path.resolve(__dirname, '..', '..');

function makeDoc(children) {
  const doc = { children: children.map(c => Object.assign({}, c)), sectionBreaks: [], calls: [], marksRemoved: 0 };
  const T = { PARAGRAPH: 'PARAGRAPH', TABLE: 'TABLE', LIST_ITEM: 'LIST_ITEM', HORIZONTAL_RULE: 'HORIZONTAL_RULE' };
  function el(c) {
    const o = Object.assign({}, c);
    o.getType = () => o.type; o.asParagraph = () => o; o.asTable = () => o; o.asListItem = () => o;
    o.copy = () => Object.assign({}, c);
    o.setBold = () => o; o.editAsText = () => ({ setBold() { return this; }, setFontFamily() { return this; }, setFontSize() { return this; } });
    o.setColumnWidth = () => o;
    return o;
  }
  const body = {
    getNumChildren: () => doc.children.length, getChild: i => el(doc.children[i]),
    appendParagraph(x) { const c = typeof x === 'string' ? { type: 'PARAGRAPH', text: x } : { type: 'PARAGRAPH', text: x.text }; doc.children.push(c); return el(c); },
    appendTable(x) { const c = Array.isArray(x) ? { type: 'TABLE', cells: x } : { type: 'TABLE', cells: x.cells }; doc.children.push(c); return el(c); },
    appendListItem(x) { doc.children.push({ type: 'LIST_ITEM', text: x.text }); return el(doc.children[doc.children.length - 1]); },
    appendHorizontalRule() { doc.children.push({ type: 'HORIZONTAL_RULE' }); }
  };
  doc.api = { getBody: () => body, saveAndClose() { doc.saved = (doc.saved || 0) + 1; } };
  // The Docs-service view of the same document: a first section break, then one element per child.
  doc.json = function () {
    let idx = 1; const content = [{ sectionBreak: {}, endIndex: 1 }];
    doc.children.forEach((c, i) => {
      if (doc.sectionBreaks.includes(i)) { content.push({ startIndex: idx, endIndex: idx + 1, sectionBreak: {} }); idx += 1; }
      const len = c.type === 'TABLE' ? 10 : (c.text || '').length + 1;
      if (c.type === 'PARAGRAPH') content.push({ startIndex: idx, endIndex: idx + len, paragraph: { elements: [{ startIndex: idx, endIndex: idx + len, textRun: { content: c.text + '\n' } }] } });
      else content.push({ startIndex: idx, endIndex: idx + len, table: {} });
      idx += len;
    });
    return { body: { content } };
  };
  return doc;
}

function run(opts) {
  const doc = makeDoc(opts.children);
  const starts = {}; // paragraph index -> startIndex, so a request's index can be mapped back to a child
  const Docs = opts.noDocs ? undefined : {
    Documents: {
      get() { doc.calls.push('get'); return doc.json(); },
      batchUpdate(req) {
        if (opts.fail) throw new Error('refused');
        req.requests.forEach(r => {
          const k = Object.keys(r)[0]; doc.calls.push({ [k]: r[k] });
          if (k === 'insertSectionBreak') {
            const j = doc.json().body.content.find(c => c.startIndex === r[k].location.index && c.paragraph);
            doc.sectionBreaks.push(doc.children.findIndex(c => c.type === 'PARAGRAPH' && c.text === '[[FILE COPY]]'));
          }
          if (k === 'replaceAllText') { doc.children.forEach(c => { if (c.text === '[[FILE COPY]]') { c.text = ''; doc.marksRemoved++; } }); }
        });
      }
    }
  };
  const ctx = { PropertiesService: { getScriptProperties: () => ({ getProperty: () => null }) }, console,
    DocumentApp: { ElementType: { PARAGRAPH: 'PARAGRAPH', TABLE: 'TABLE', LIST_ITEM: 'LIST_ITEM', HORIZONTAL_RULE: 'HORIZONTAL_RULE' },
                   openById: () => doc.api }, Docs };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(root, 'apps_script', 'travel_docs.gs'), 'utf8'), ctx, { filename: 'travel_docs.gs' });
  const status = ctx.addFileCopy_('DOC1');
  return { status, calls: doc.calls, children: doc.children, sectionBreaks: doc.sectionBreaks, marksRemoved: doc.marksRemoved,
           pure: { mark: ctx.findMarkIndex_(doc.json(), '[[FILE COPY]]'), last: ctx.lastSectionBreakIndex_(doc.json()) } };
}

const original = [{ type: 'PARAGRAPH', text: 'DEPARTMENT PERSONNEL ORDER' }, { type: 'PARAGRAPH', text: 'No. 2026 - ____' },
                  { type: 'TABLE', cells: [['Name', 'Position']] }, { type: 'PARAGRAPH', text: 'By Authority of the Secretary of Health:' }];
console.log(JSON.stringify({
  ok: run({ children: original }),
  off: run({ children: original, noDocs: true }),
  fail: run({ children: original, fail: true }),
  pure: (function () {
    const ctx = { PropertiesService: { getScriptProperties: () => ({ getProperty: () => null }) }, console };
    vm.createContext(ctx);
    vm.runInContext(fs.readFileSync(path.join(root, 'apps_script', 'travel_docs.gs'), 'utf8'), ctx);
    const one = { body: { content: [{ sectionBreak: {} }, { startIndex: 1, paragraph: { elements: [{ startIndex: 1, textRun: { content: 'x\n' } }] } }] } };
    const two = { body: { content: [{ sectionBreak: {} }, { startIndex: 1, paragraph: { elements: [{ startIndex: 1, textRun: { content: 'a\n' } }] } },
                                    { startIndex: 3, sectionBreak: {} }, { startIndex: 4, paragraph: { elements: [{ startIndex: 4, textRun: { content: 'b [[M]]\n' } }] } }] } };
    return { oneBreak: ctx.lastSectionBreakIndex_(one), twoBreaks: ctx.lastSectionBreakIndex_(two), missing: ctx.findMarkIndex_(one, '[[M]]'),
             found: ctx.findMarkIndex_(two, '[[M]]'), empty: ctx.findMarkIndex_({}, 'x'), emptyBreak: ctx.lastSectionBreakIndex_(null) };
  })()
}));
