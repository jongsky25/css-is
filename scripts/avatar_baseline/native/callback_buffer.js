// Diagnostic-only native recorder. No reads from element/page pointer targets.
if (Process.arch !== 'x64' || Process.pointerSize !== 8) throw new Error('Linux x64 recorder ABI required');
const selfTestOnly = globalThis.RECORDER_SELF_TEST_ONLY === true;
const image = Process.getModuleByName('chromium');
const offsets = {allocate: 0x5ab0350, pool: 0x5ab0550, receiver: 0x100cce80,
  shutdown: 0x100208d0, destroy: 0x5aa4490, release: 0x5ab09d0};
const names = {1:'allocate',2:'pool',3:'receiver',4:'shutdown',5:'destroy',6:'release',99:'__selftest'};
const kindIds = {allocate:1,pool:2,receiver:3,shutdown:4,destroy:5,release:6};
const source = String.raw`
#include <gum/guminterceptor.h>
extern int recorder_clock(int id, void *stamp);
extern int recorder_tid(void);
extern void recorder_lock(void *mutex);
extern void recorder_unlock(void *mutex);
extern void *recorder_thread_new(const char *name, void *(*fn)(void *), void *arg);
extern void *recorder_thread_join(void *thread);
#define MAX_RECORDS 50000
#define NIL_GROUP 0xffffffffU

typedef struct { long seconds; long nanos; } Stamp;
typedef struct {
  guint64 begin_ns, ready_ns, end_ns, backend, address, thread;
  guint32 kind, phase_id, phase_type, document, group, absent;
} Record;
typedef struct { Record record; guint32 enabled; } Invocation;
static Record records[MAX_RECORDS], snapshot_records[MAX_RECORDS];
/* System GLib GMutex is zero-initialized and pointer-aligned; storage is 16 bytes. */
static unsigned long mutex_storage[2];
static guint32 count, dropped, inflight, limit=MAX_RECORDS;
static guint32 phase_id, phase_type, document, phase_group=NIL_GROUP, cursor;
static guint32 snapshot_count, snapshot_dropped, snapshot_pending, snapshot_limit;
static guint64 snapshot_end;
static guint64 now_ns(void) {
  Stamp stamp;
  if (recorder_clock(1, &stamp) != 0) return 0;
  return ((guint64) stamp.seconds)*1000000000ULL + (guint64) stamp.nanos;
}
guint64 get_clock(void) { return now_ns(); }
guint32 record_size(void) { return sizeof(Record); }
void set_phase(guint32 id, guint32 type, guint32 doc, guint32 group) {
  recorder_lock(mutex_storage);
  phase_id=id; phase_type=type; document=doc; phase_group=group;
  if (type==1 || type==3) cursor=0;
  recorder_unlock(mutex_storage);
}
static void begin_record(Invocation *inv, guint32 kind, guint64 backend, guint64 address) {
  inv->enabled=0;
  Record *e=&inv->record;
  e->begin_ns=now_ns();
  e->backend=backend; e->address=address; e->thread=(guint64) recorder_tid();
  e->kind=kind; e->end_ns=0; e->absent=2;
  recorder_lock(mutex_storage);
  if (kind==3 && phase_type!=1 && phase_type!=2 && phase_type!=3) {
    recorder_unlock(mutex_storage); return;
  }
  e->phase_id=phase_id; e->phase_type=phase_type; e->document=document; e->group=phase_group;
  if (kind==3 && (phase_type==1 || phase_type==3)) e->group=(cursor++)/32;
  inflight++; inv->enabled=1;
  recorder_unlock(mutex_storage);
  e->ready_ns=now_ns();
}
static void end_record(Invocation *inv, guint64 value) {
  if (!inv->enabled) return;
  Record *e=&inv->record;
  e->end_ns=now_ns();
  if (e->kind==1) e->address=value; /* Copy integer return VALUE, never a recycled wrapper. */
  if (e->kind==3) e->absent=(value==0);
  recorder_lock(mutex_storage);
  if (count<limit) { records[count]=*e; count++; } else dropped++;
  inflight--;
  recorder_unlock(mutex_storage);
}
void on_enter(GumInvocationContext *ic) {
  guint32 kind=(guint32)(guintptr) gum_invocation_context_get_listener_function_data(ic);
  Invocation *inv=gum_invocation_context_get_listener_invocation_data(ic,sizeof(Invocation));
  guint64 first=(guint64)(guintptr) gum_invocation_context_get_nth_argument(ic,0);
  guint64 backend=kind==3 ? 0 : first;
  guint64 address=kind==2 ? (guint64)(guintptr) gum_invocation_context_get_nth_argument(ic,1)
    : (kind==3 || kind==4 || kind==5) ? first : 0;
  begin_record(inv,kind,backend,address);
}
void on_leave(GumInvocationContext *ic) {
  Invocation *inv=gum_invocation_context_get_listener_invocation_data(ic,sizeof(Invocation));
  end_record(inv,(guint64)(guintptr) gum_invocation_context_get_return_value(ic));
}
guint32 snapshot(void) {
  recorder_lock(mutex_storage);
  snapshot_count=count; snapshot_dropped=dropped; snapshot_pending=inflight; snapshot_limit=limit;
  snapshot_end=now_ns();
  for (guint32 i=0;i<count;i++) snapshot_records[i]=records[i];
  recorder_unlock(mutex_storage);
  return snapshot_count;
}
void *snapshot_buffer(void) { return snapshot_records; }
guint32 get_dropped(void) { return snapshot_dropped; }
guint32 get_pending(void) { return snapshot_pending; }
guint32 get_limit(void) { return snapshot_limit; }
guint64 get_snapshot_end(void) { return snapshot_end; }
typedef struct { guint32 worker, iterations; } Task;
static void *test_worker(void *data) {
  Task *task=data;
  for (guint32 i=1;i<=task->iterations;i++) {
    guint32 id=task->worker*100000+i;
    set_phase(id,1,id,0);
    guint64 value=(((guint64)task->worker)<<32)|i;
    Invocation inv;
    begin_record(&inv,99,value^0x5a5aULL,value);
    end_record(&inv,value);
    value=0; /* Reuse local storage; exported values must remain immutable copies. */
  }
  return 0;
}
int run_test(guint32 workers, guint32 iterations, guint32 test_limit) {
  if (workers!=4 || iterations==0 || iterations>10000 || test_limit==0 || test_limit>MAX_RECORDS) return -1;
  recorder_lock(mutex_storage);
  if (inflight) { recorder_unlock(mutex_storage); return -2; }
  count=0; dropped=0; limit=test_limit;
  recorder_unlock(mutex_storage);
  Task tasks[4]; void *threads[4];
  for (guint32 i=0;i<workers;i++) {
    tasks[i].worker=i+1; tasks[i].iterations=iterations;
    threads[i]=recorder_thread_new("recorder-proof",test_worker,&tasks[i]);
  }
  for (guint32 i=0;i<workers;i++) recorder_thread_join(threads[i]);
  return 0;
}
`;
const externalNames = {
  recorder_clock:'clock_gettime',recorder_tid:'gettid',recorder_lock:'g_mutex_lock',
  recorder_unlock:'g_mutex_unlock',recorder_thread_new:'g_thread_new',recorder_thread_join:'g_thread_join',
  memcpy:'memcpy',memset:'memset'};
const symbols = {};
for (const [key,name] of Object.entries(externalNames)) symbols[key]=Module.getGlobalExportByName(name);
const module = new CModule(source,symbols,{toolchain:'internal'});
const snapshot = new NativeFunction(module.snapshot,'uint',[]);
const buffer = new NativeFunction(module.snapshot_buffer,'pointer',[]);
const size = new NativeFunction(module.record_size,'uint',[]);
const setPhase = new NativeFunction(module.set_phase,'void',['uint','uint','uint','uint']);
const clock = new NativeFunction(module.get_clock,'uint64',[]);
const dropped = new NativeFunction(module.get_dropped,'uint',[]);
const pending = new NativeFunction(module.get_pending,'uint',[]);
const limit = new NativeFunction(module.get_limit,'uint',[]);
const snapshotEnd = new NativeFunction(module.get_snapshot_end,'uint64',[]);
const test = new NativeFunction(module.run_test,'int',['uint','uint','uint']);
if (size()!==72) throw new Error('Unexpected native record ABI');
let phaseText='attached', phaseSerial=0;
const phases=['attached'], references=[];
function safe(value) { const n=Number(value); if (!Number.isSafeInteger(n)||n<0) throw new Error('Unsafe native integer'); return n; }
function now() { return safe(clock()); }
function result() {
  const n=snapshot(), ptr=buffer(), events=[];
  for (let i=0;i<n;i++) {
    const p=ptr.add(i*72), kind=p.add(48).readU32(), serial=p.add(52).readU32();
    const type=p.add(56).readU32(), doc=p.add(60).readU32(), group=p.add(64).readU32();
    let phase=phases[serial];
    if (kind===3 && (type===1||type===3)) phase='census:'+doc+':'+(['avatar:0','avatar:1','other:0','other:1'][group]||'overflow');
    if (kind===99) phase='selftest:'+serial;
    if (phase===undefined) throw new Error('Unknown captured phase');
    events.push({kind:names[kind],phase,begin_ns:safe(p.readU64()),callback_ready_ns:safe(p.add(8).readU64()),
      returned_ns:safe(p.add(16).readU64()),thread:safe(p.add(40).readU64()),
      backend:kind===3?null:p.add(24).readPointer().toString(),address:kind===6?null:p.add(32).readPointer().toString(),
      attribute_absent:kind===3?p.add(68).readU32()===1:null,
      phase_id:serial,phase_type:type,phase_document:doc,receiver_group:group});
  }
  const all=events.concat(references).sort((a,b)=>a.returned_ns-b.returned_ns);
  return {module:image.path,offsets,page_size:131072,address_encoding:'native-u64-buffer-v1',
    recorder_backend:'cmodule-buffer-v1',record_size:72,record_capacity:50000,record_limit:limit(),
    snapshot_end_ns:safe(snapshotEnd()),pending_at_snapshot:pending(),dropped:dropped(),events:all,
    abi:'linux-x64-gum-invocation-v1',clock_domain:'CLOCK_MONOTONIC',toolchain:'internal',
    mutex_module:Process.findModuleByAddress(symbols.recorder_lock).path};
}
if (!selfTestOnly) {
  for (const [kind,offset] of Object.entries(offsets))
    Interceptor.attach(image.base.add(offset),{onEnter:module.on_enter,onLeave:module.on_leave},ptr(kindIds[kind]));
}
rpc.exports={
  setphase(value) {
    phaseText=value;const parts=value.split(':');
    const type={navigation:1,census:2,batch:3,reference:4}[parts[0]]||0;
    const doc=type?Number(parts[1]):0;
    const group=type===2 ? (parts[2]==='avatar'?0:2)+Number(parts[3]) : 0xffffffff;
    phases.push(value);phaseSerial=phases.length-1;setPhase(phaseSerial,type,doc,group);
  },
  enablereference() {
    if (selfTestOnly||offsets.reference) throw new Error('Reference unavailable');offsets.reference=0x100b1880;
    Interceptor.attach(image.base.add(offsets.reference),{
      onEnter(args) { this.enabled=phaseText.startsWith('reference:');if(!this.enabled)return;
        this.begin=now();this.phase=phaseText;this.address=args[0].toString();this.ready=now(); },
      onLeave(retval) { if(this.enabled) references.push({kind:'reference',phase:this.phase,begin_ns:this.begin,
        callback_ready_ns:this.ready,returned_ns:now(),thread:Process.getCurrentThreadId(),backend:null,address:this.address}); }
    });
  },
  clock:now,
  selftest(workers,iterations,testLimit) { if(!selfTestOnly)throw new Error('Self-test forbidden in live capture');
    if(test(workers,iterations,testLimit)!==0)throw new Error('Native self-test failed');return result(); },
  result
};
send({ready:!selfTestOnly,selftest_ready:selfTestOnly,pid:Process.id,module:image.path,recorder_backend:'cmodule-buffer-v1'});
