// Exact-build diagnostic. Receivers identify membership, never exclusive page ownership.
const image = Process.getModuleByName('chromium');
const stamp = Memory.alloc(16);
const clock = new NativeFunction(Module.getGlobalExportByName('clock_gettime'), 'int', ['int', 'pointer']);
function now() {
  if (clock(1, stamp) !== 0) throw new Error('clock_gettime failed');
  return Number(stamp.readU64()) * 1e9 + Number(stamp.add(8).readU64());
}
const offsets = {allocate: 0x5ab0350, pool: 0x5ab0550, receiver: 0x100b1880};
let phase = 'attached', dropped = 0;
const events = [];
function store(e) { if (events.length < 50000) events.push(e); else dropped++; }
for (const [kind, offset] of Object.entries(offsets)) {
  Interceptor.attach(image.base.add(offset), {
    onEnter(args) {
      this.enabled = kind !== 'receiver' || phase.startsWith('census:');
      if (!this.enabled) return;
      this.begin = now(); this.phase = phase;
      this.backend = kind === 'receiver' ? null : args[0].toString();
      this.address = kind === 'pool' ? args[1].toString() : kind === 'receiver' ? args[0].toString() : null;
      this.ready = now();
    },
    onLeave(retval) {
      if (!this.enabled) return;
      store({kind, phase: this.phase, begin_ns: this.begin, callback_ready_ns: this.ready,
        returned_ns: now(), thread: Process.getCurrentThreadId(), backend: this.backend,
        address: kind === 'allocate' ? retval.toString() : this.address});
    }
  });
}
rpc.exports = {
  setphase(value) { phase = value; },
  result() { return {module: image.path, offsets, page_size: 131072, events, dropped}; }
};
send({ready: true, pid: Process.id, module: image.path});
