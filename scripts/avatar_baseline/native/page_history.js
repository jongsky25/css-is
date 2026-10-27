// Diagnostic-only hooks for pinned Chromium 156; not an application dependency.
const image = Process.getModuleByName('chromium');
const stamp = Memory.alloc(16);
const gettime = new NativeFunction(Module.getGlobalExportByName('clock_gettime'), 'int', ['int', 'pointer']);
function now() {
  if (gettime(1, stamp) !== 0) throw new Error('clock_gettime failed');
  return Number(stamp.readU64()) * 1e9 + Number(stamp.add(8).readU64());
}
const events = [];
let phase = 'attached', dropped = 0;
function store(e) { if (events.length < 20000) events.push(e); else dropped++; }
const offsets = {allocate: 0x5ab0350, pool: 0x5ab0550};
for (const [kind, offset] of Object.entries(offsets)) {
  Interceptor.attach(image.base.add(offset), {
    onEnter(args) {
      this.begin = now(); this.phase = phase;
      this.backend = args[0].toString();
      this.page = kind === 'pool' ? args[1].toString() : null;
      this.stack = kind === 'allocate' ? Thread.backtrace(this.context, Backtracer.ACCURATE).map(p =>
        p.compare(image.base) >= 0 && p.compare(image.base.add(image.size)) < 0
          ? {offset: p.sub(image.base).toString()} : {external: p.toString()}) : [];
      this.ready = now();
    },
    onLeave(retval) {
      const returned = now();
      store({kind, begin_ns: this.begin, callback_ready_ns: this.ready, returned_ns: returned,
        thread: Process.getCurrentThreadId(), phase: this.phase, backend: this.backend,
        page: kind === 'allocate' ? retval.toString() : this.page, stack: this.stack});
    }
  });
}
rpc.exports = {
  setphase(value) { phase = value; },
  result() { return {module_base: image.base.toString(), module_size: image.size, offsets, events, dropped}; }
};
send({ready: true, pid: Process.id, module: image.path});
