// Exact-build diagnostic. Receivers identify membership, never exclusive page ownership.
const image = Process.getModuleByName('chromium');
const stamp = Memory.alloc(16);
const clock = new NativeFunction(Module.getGlobalExportByName('clock_gettime'), 'int', ['int', 'pointer']);
function now() {
  if (clock(1, stamp) !== 0) throw new Error('clock_gettime failed');
  return Number(stamp.readU64()) * 1e9 + Number(stamp.add(8).readU64());
}
const offsets = {allocate: 0x5ab0350, pool: 0x5ab0550, receiver: 0x100cce80, shutdown: 0x100208d0, destroy: 0x5aa4490, release: 0x5ab09d0};
let phase = 'attached', dropped = 0, censusCursor = 0;
const events = [];
function store(e) { if (events.length < 50000) events.push(e); else dropped++; }
for (const [kind, offset] of Object.entries(offsets)) {
  Interceptor.attach(image.base.add(offset), {
    onEnter(args) {
      this.enabled = kind !== 'receiver' || (phase.startsWith('census:') || phase.startsWith('batch:') || phase.startsWith('navigation:'));
      if (!this.enabled) return;
      this.begin = now(); this.phase = phase;
      if (kind === 'receiver' && (phase.startsWith('batch:') || phase.startsWith('navigation:'))) {
        const groups = ['avatar:0', 'avatar:1', 'other:0', 'other:1'];
        const group = groups[Math.floor(censusCursor / 32)] || 'overflow';
        this.phase = 'census:' + phase.split(':')[1] + ':' + group;
        censusCursor++;
      }
      this.backend = kind === 'receiver' ? null : args[0];
      this.address = kind === 'pool' ? args[1] : ['receiver', 'shutdown', 'destroy'].includes(kind) ? args[0] : null;
      this.ready = now();
    },
    onLeave(retval) {
      if (!this.enabled) return;
      store({kind, phase: this.phase, begin_ns: this.begin, callback_ready_ns: this.ready,
        returned_ns: now(), thread: Process.getCurrentThreadId(), backend: this.backend,
        // Invocation return values are recycled: copy its VALUE before leaving the callback.
        address: kind === 'allocate' ? retval.add(0) : this.address,
        attribute_absent: kind === 'receiver' ? retval.isNull() : null});
    }
  });
}
rpc.exports = {
  enablereference() {
    if (offsets.reference) throw new Error('Reference already enabled');
    offsets.reference = 0x100b1880;
    Interceptor.attach(image.base.add(offsets.reference), {
      onEnter(args) {
        this.enabled = phase.startsWith('reference:');
        if (!this.enabled) return;
        this.begin = now(); this.phase = phase; this.address = args[0].toString(); this.ready = now();
      },
      onLeave(retval) {
        if (!this.enabled) return;
        store({kind: 'reference', phase: this.phase, begin_ns: this.begin,
          callback_ready_ns: this.ready, returned_ns: now(), thread: Process.getCurrentThreadId(),
          backend: null, address: this.address});
      }
    });
  },
  setphase(value) { phase = value; if (phase.startsWith('batch:') || phase.startsWith('navigation:')) censusCursor = 0; },
  result() {
    // Formatting is deferred until AFTER the host has sealed measurement.
    const exported = events.map(e => ({...e,
      backend: e.backend === null ? null : e.backend.toString(),
      address: e.address === null ? null : e.address.toString()}));
    return {module: image.path, offsets, page_size: 131072,
      address_encoding: 'deferred-native-pointer-v1', events: exported, dropped};
  }
};
send({ready: true, pid: Process.id, module: image.path});
