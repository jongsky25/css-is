// Run the real advisory Slides relay code (travel_docs.gs + advisory_slides.gs) against fake Google services.
const fs = require('fs'), vm = require('vm'), path = require('path');
const read = f => fs.readFileSync(path.resolve(__dirname, '../../apps_script/' + f), 'utf8');
const SOURCE = read('travel_docs.gs') + '\n' + read('advisory_slides.gs');

function world(opts = {}) {
  const log = [];
  let nextId = 1;
  const props = Object.assign({ ROOT_FOLDER_ID: 'ROOTFOLDER0000000000000', ALLOWED_DOMAIN: 'doh.gov.ph',
                                TPL_advisory: 'MASTER000000000000000000' }, opts.props || {});
  const files = {}, folders = {};
  function folder(id, name, parent) {
    const f = { id, name, parent, children: [], files: [],
      getId: () => id, getName: () => name,
      getParents: () => iter(parent ? [folders[parent]] : []),
      getFoldersByName: n => iter(f.children.map(c => folders[c]).filter(c => c.name === n)),
      createFolder: n => { const c = folder('FOLDER' + (nextId++) + '0000000000000000', n, id); f.children.push(c.id); return c; },
      getFiles: () => iter(f.files.map(x => files[x])) };
    folders[id] = f; return f;
  }
  function iter(list) { let i = 0; return { hasNext: () => i < list.length, next: () => list[i++] }; }
  function shape(text) {
    const s = { text, image: null, getPageElementType: () => 'SHAPE', asShape: () => s,
      getText: () => ({ asString: () => s.text }), replaceWithImage: blob => { s.image = blob; s.text = ''; } };
    return s;
  }
  function deck(slideTexts) {
    return slideTexts.map((texts, i) => ({ id: 'slide' + (i + 1), elements: texts.map(shape) }));
  }
  function file(id, name, parent, slides) {
    const f = { id, name, parent, description: '', slides, version: 1, perms: [{ id: 'p0', type: 'user', role: 'owner', emailAddress: 'office@doh.gov.ph' }],
      comments: [],
      getId: () => id, getName: () => f.name, getUrl: () => 'https://docs.google.com/presentation/d/' + id + '/edit',
      getDescription: () => f.description, setDescription: d => { f.description = d; },
      getParents: () => iter(parent ? [folders[parent]] : []),
      makeCopy: (n, dest) => {
        const cid = 'COPY' + (nextId++) + '00000000000000000000';
        const c = file(cid, n, dest.id, JSON.parse(JSON.stringify(f.slides)));
        dest.files.push(cid); log.push('copy'); return c;
      },
      getAs: () => ({ getBytes: () => Array.from(Buffer.from('%PDF-1.7 ' + id + ' v' + f.version)) }) };
    files[id] = f; return f;
  }
  folder(props.ROOT_FOLDER_ID, 'root', null);
  folder('ELSEWHERE00000000000000', 'elsewhere', null);
  const masterSlides = opts.master || [
    ['ADVISORY {{number}}', '{{title}}', '{{message}}', '{{qr}}'],
    ['ADVISORY {{number}}', '{{title}}', '{{dates}} at {{venue}}'],
    ['ADVISORY {{number}}', '{{attention}}']];
  const master = file(props.TPL_advisory, 'master', 'ELSEWHERE00000000000000',
                      masterSlides.map((t, i) => ({ id: 'slide' + (i + 1), elements: t.map(x => ({ text: x })) })));
  function openDeck(id) {
    const f = files[id];
    f.slides.forEach(s => s.elements = s.elements.map(e => e.getPageElementType ? e : Object.assign(shape(e.text), { image: e.image || null })));
    return {
      getSlides: () => f.slides.map(s => ({
        getObjectId: () => s.id,
        getPageElements: () => s.elements,
        remove: () => { f.slides = f.slides.filter(x => x !== s); }
      })),
      replaceAllText: (a, b) => { f.slides.forEach(s => s.elements.forEach(e => { e.text = e.text.split(a).join(b); })); },
      saveAndClose: () => { f.version += 1; log.push('save'); }
    };
  }
  const bump = opts.editDuringSnapshot;
  const ctx = {
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => props[k] || null, setProperty: (k, v) => { props[k] = v; } }) },
    DriveApp: {
      getFolderById: id => { if (!folders[id]) throw Error('no folder'); return folders[id]; },
      getFileById: id => { if (!files[id]) throw Error('no file'); return files[id]; }
    },
    SlidesApp: { openById: openDeck, PageElementType: { SHAPE: 'SHAPE' } },
    Drive: {
      Files: { get: id => ({ id, version: String(files[id].version), modifiedTime: '2026-11-24T00:00:0' + files[id].version + 'Z' }) },
      Permissions: {
        create: (p, id, o) => { log.push(['share', p.emailAddress, p.role, o.sendNotificationEmail]);
          files[id].perms.push({ id: 'p' + (nextId++), type: 'user', role: p.role, emailAddress: p.emailAddress }); },
        list: id => ({ permissions: files[id].perms.slice() }),
        remove: (id, pid) => { log.push(['remove', files[id].perms.find(p => p.id === pid).emailAddress]);
          files[id].perms = files[id].perms.filter(p => p.id !== pid); }
      },
      Comments: { list: id => ({ comments: files[id].comments }) }
    },
    Utilities: {
      base64Decode: s => Array.from(Buffer.from(s, 'base64')),
      base64Encode: b => Buffer.from(b).toString('base64'),
      newBlob: (bytes, mime, name) => ({ bytes, mime, name }),
      computeDigest: (_, bytes) => Array.from(require('crypto').createHash('sha256').update(Buffer.from(bytes)).digest()).map(b => b > 127 ? b - 256 : b),
      DigestAlgorithm: { SHA_256: 'SHA_256' }
    },
    LockService: { getScriptLock: () => ({ tryLock: () => !opts.locked, releaseLock: () => {} }) },
    ScriptApp: { getOAuthToken: () => 'token' },
    UrlFetchApp: { fetch: (url) => {
      const id = /\/d\/([^/]+)\//.exec(url)[1];
      if (bump) files[id].version += 1;
      return { getResponseCode: () => (opts.pngStatus || 200), getBlob: () => ({ getBytes: () => Array.from(Buffer.from('\x89PNG ' + url, 'latin1')) }) };
    } },
    ContentService: { createTextOutput: t => ({ setMimeType: () => JSON.parse(t) }), MimeType: { JSON: 'json' } },
    Logger: { log: () => {} }
  };
  vm.createContext(ctx); vm.runInContext(SOURCE, ctx);
  return { ctx, files, folders, log, props, master };
}

const out = {};
const qr = Buffer.from('\x89PNG qr', 'latin1').toString('base64');
const base = { action: 'advisory_create', request_id: 'adv-7-r1', folder_key: 'adv-7', variant: 1, title: 'JOAS Batch 2',
  fields: { number: '2026-1124-001', title: 'JOAS Batch 2', message: 'Price: $5 \\ok' }, qr_png_b64: qr,
  editors: ['ana@doh.gov.ph', 'ANA@doh.gov.ph', 'ben@doh.gov.ph'] };

{ // create: one variant kept, text filled ($ and \ literal), QR placed, quiet shares, idempotent retry
  const w = world();
  const r = w.ctx.advisoryOperation_(base);
  const f = w.files[r.id];
  const again = w.ctx.advisoryOperation_(base);
  out.create = { result: r, slides: f.slides.length, texts: f.slides[0].elements.map(e => e.text),
    qrImage: !!f.slides[0].elements[3].image, shares: w.log.filter(x => Array.isArray(x) && x[0] === 'share'),
    copies: w.log.filter(x => x === 'copy').length, againId: again.id, path: [w.folders[f.parent].name, w.folders[w.folders[f.parent].parent].name] };
}
{ // a variant with a placeholder we did not fill is reported; no QR box is reported
  const w = world();
  const r = w.ctx.advisoryOperation_(Object.assign({}, base, { variant: 2, fields: { number: 'N', title: 'T' } }));
  out.unfilled = r;
}
{ // refusals
  const w = world();
  const call = extra => w.ctx.advisoryOperation_(Object.assign({}, base, extra)).error;
  out.refusals = {
    outsider: call({ editors: ['x@gmail.com'] }), variant: call({ variant: 9 }), zero: call({ variant: 0 }),
    folder: call({ folder_key: '../up' }), request: call({ request_id: 'a b' }), qrKey: call({ fields: { qr: 'x' } }),
    badKey: call({ fields: { 'Title': 'x' } }), long: call({ fields: { title: 'x'.repeat(2001) } }),
    noTemplate: world({ props: { TPL_advisory: '' } }).ctx.advisoryOperation_(base).error,
    locked: world({ locked: true }).ctx.advisoryOperation_(base).error,
    unknown: w.ctx.advisoryOperation_({ action: 'advisory_delete' }).error,
    copies: w.log.filter(x => x === 'copy').length
  };
}
{ // doPost hands advisory_* to the companion, and says so when it is missing
  const w = world();
  w.ctx.verify_ = () => true;
  const post = req => w.ctx.doPost({ postData: { contents: JSON.stringify({ ts: 1, sig: 'x', payload: JSON.stringify(req) }) } });
  out.route = { info: post({ action: 'advisory_info' }) };
  w.ctx.advisoryOperation_ = undefined;
  out.route.missing = post({ action: 'advisory_info' });
  out.route.ping = post({ action: 'ping' });
}
{ // snapshot: digests match bytes, only open comments, outside files refused, edits during the copy refused
  const w = world();
  const id = w.ctx.advisoryOperation_(base).id;
  w.files[id].comments = [
    { id: 'c1', content: 'Fix the date', resolved: false, createdTime: 't1', author: { displayName: 'Chief' },
      quotedFileContent: { value: 'Dec 15' }, replies: [{ content: 'Done', createdTime: 't2', author: { displayName: 'Ana' } }, { deleted: true }] },
    { id: 'c2', content: 'old', resolved: true }];
  const s = w.ctx.advisoryOperation_({ action: 'advisory_snapshot', file_id: id });
  const sha = b => require('crypto').createHash('sha256').update(Buffer.from(b, 'base64')).digest('hex');
  out.snapshot = { ok: s.ok, version: s.version, pdfOk: sha(s.pdf_b64) === s.pdf_sha256, pngOk: sha(s.png_b64) === s.png_sha256,
    comments: s.comments, outside: w.ctx.advisoryOperation_({ action: 'advisory_snapshot', file_id: w.master.id }).error,
    badId: w.ctx.advisoryOperation_({ action: 'advisory_snapshot', file_id: '../x' }).error };
  const busy = world({ editDuringSnapshot: true });
  const id2 = busy.ctx.advisoryOperation_(base).id;
  out.snapshot.changed = busy.ctx.advisoryOperation_({ action: 'advisory_snapshot', file_id: id2 }).error;
  const broken = world({ pngStatus: 500 });
  const id3 = broken.ctx.advisoryOperation_(base).id;
  out.snapshot.exportFailed = broken.ctx.advisoryOperation_({ action: 'advisory_snapshot', file_id: id3 }).error;
}
{ // access: exact set; owner kept; strongest role wins; nobody emailed
  const w = world();
  const id = w.ctx.advisoryOperation_(base).id;
  w.log.length = 0;
  const r = w.ctx.advisoryOperation_({ action: 'advisory_access', file_id: id, editors: [],
    commenters: ['ana@doh.gov.ph', 'chief@doh.gov.ph'], readers: ['chief@doh.gov.ph', 'dir@doh.gov.ph'] });
  out.access = { result: r, perms: w.files[id].perms.map(p => [p.emailAddress, p.role]).sort(),
    log: w.log, outsider: w.ctx.advisoryOperation_({ action: 'advisory_access', file_id: id, readers: ['a@b.com'] }).error,
    masterRefused: w.ctx.advisoryOperation_({ action: 'advisory_access', file_id: w.master.id }).error };
  const again = w.ctx.advisoryOperation_({ action: 'advisory_access', file_id: id, editors: [],
    commenters: ['ana@doh.gov.ph', 'chief@doh.gov.ph'], readers: ['dir@doh.gov.ph'] });
  out.access.repeat = again.changed;
}
{ // info lists variants and their placeholders; thumbnails only when asked
  out.info = world().ctx.advisoryOperation_({ action: 'advisory_info' });
  out.thumbs = world().ctx.advisoryOperation_({ action: 'advisory_info', thumbnails: true }).variants.map(v => Buffer.from(v.png_b64, 'base64').toString('latin1').slice(0, 4));
}
{ // version: the file's Drive version; outside files refused
  const w = world();
  const id = w.ctx.advisoryOperation_(base).id;
  out.version = { mine: w.ctx.advisoryOperation_({ action: 'advisory_version', file_id: id }).version,
    outside: w.ctx.advisoryOperation_({ action: 'advisory_version', file_id: w.master.id }).error };
}
process.stdout.write(JSON.stringify(out));
