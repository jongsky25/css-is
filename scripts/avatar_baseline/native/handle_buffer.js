// Diagnostic only. Native callbacks, no per-event JavaScript or V8 API calls.
if(Process.arch!=='x64'||Process.pointerSize!==8)throw new Error('Linux x64 required');
const selfOnly=globalThis.HANDLE_BUFFER_SELFTEST===true;
const image=Process.getModuleByName('chromium');
const offsets={state_ctor:0xfd46290,state_dispose:0xfd46800,state_dtor:0xfd46690,
 state_dissociate:0xfd46990,per_ctor:0xfd4bac0,per_dtor:0xfd4bc10,
 extension_ctor:0xad479b0,extension_invalidate:0xad48db0,extension_dtor:0xad48610,
 holder_set:0xd32f710,holder_dtor:0xd32f660,global_create:0x5142d10,
 global_release:0x5143060,global_weak_direct:0x5143150,
 global_weak_field:0x51431a0,gc_epilogue:0x51184b0};
const names=['',...Object.keys(offsets)];names[99]='__selftest';
const source=String.raw`
#include <gum/guminterceptor.h>
extern int hb_clock(int id, void *stamp);
extern int hb_tid(void);
extern void hb_lock(void *mutex);
extern void hb_unlock(void *mutex);
extern void *hb_thread_new(const char *name,void *(*fn)(void *),void *arg);
extern void *hb_thread_join(void *thread);
#define CAPACITY 50000
typedef struct {long seconds,nanos;} Stamp;
typedef struct {
 guint64 begin_ns,ready_ns,end_ns,a0,a1,value,caller,thread;
 guint32 kind,serial;
} Record;
typedef struct {Record record;} Invocation;
typedef struct {
 Record records[CAPACITY],copied[CAPACITY];
 unsigned long mutex[2];
 guint32 count,dropped,pending,limit,serial;
 guint32 copied_count,copied_dropped,copied_pending,copied_limit;
 guint64 copied_end,canary;
} State;
extern State hb_state;
guint32 state_size(void){return sizeof(State);}
guint32 record_size(void){return sizeof(Record);}
guint64 canary_read(void){return hb_state.canary;}
void canary_write(guint64 value){hb_state.canary=value;}
void initialize(void){hb_state.limit=CAPACITY;}
guint64 clock_now(void){Stamp stamp;if(hb_clock(1,&stamp)!=0)return 0;
 return (guint64)stamp.seconds*1000000000ULL+(guint64)stamp.nanos;}
static void begin(Invocation *inv,guint32 kind,guint64 a0,guint64 a1,guint64 caller){
 Record *r=&inv->record;r->begin_ns=clock_now();r->a0=a0;r->a1=a1;
 r->caller=caller;r->thread=(guint64)hb_tid();r->kind=kind;r->value=0;
 hb_lock(hb_state.mutex);r->serial=++hb_state.serial;hb_state.pending++;
 hb_unlock(hb_state.mutex);r->ready_ns=clock_now();
}
static void end(Invocation *inv,guint64 value){
 Record *r=&inv->record;r->end_ns=clock_now();r->value=value;
 hb_lock(hb_state.mutex);
 if(hb_state.count<hb_state.limit)hb_state.records[hb_state.count++]=*r;
 else hb_state.dropped++;
 hb_state.pending--;hb_unlock(hb_state.mutex);
}
void on_enter(GumInvocationContext *ic){
 guint32 kind=(guint32)(guintptr)gum_invocation_context_get_listener_function_data(ic);
 Invocation *inv=gum_invocation_context_get_listener_invocation_data(ic,sizeof(Invocation));
 guint64 a0=(guint64)(guintptr)gum_invocation_context_get_nth_argument(ic,0);
 guint64 a1=kind==12?(guint64)(guintptr)gum_invocation_context_get_nth_argument(ic,1):0;
 /* Sole data read: the live Address** argument cell, never an object field. */
 if(kind==15&&a0)a1=*((guint64*)(guintptr)a0);
 begin(inv,kind,a0,a1,(guint64)(guintptr)gum_invocation_context_get_return_address(ic));
}
void on_leave(GumInvocationContext *ic){
 Invocation *inv=gum_invocation_context_get_listener_invocation_data(ic,sizeof(Invocation));
 end(inv,inv->record.kind==12?(guint64)(guintptr)gum_invocation_context_get_return_value(ic):0);
}
guint32 snapshot(void){
 hb_lock(hb_state.mutex);
 hb_state.copied_count=hb_state.count;hb_state.copied_dropped=hb_state.dropped;
 hb_state.copied_pending=hb_state.pending;hb_state.copied_limit=hb_state.limit;
 hb_state.copied_end=clock_now();
 for(guint32 i=0;i<hb_state.count;i++)hb_state.copied[i]=hb_state.records[i];
 hb_unlock(hb_state.mutex);return hb_state.copied_count;
}
void *buffer(void){return hb_state.copied;}
guint32 dropped(void){return hb_state.copied_dropped;}
guint32 pending(void){return hb_state.copied_pending;}
guint32 limit(void){return hb_state.copied_limit;}
guint64 snapshot_end(void){return hb_state.copied_end;}
typedef struct {guint32 worker,iterations;} Task;
static void *worker(void *value){
 Task *task=value;
 for(guint32 i=1;i<=task->iterations;i++){
  guint64 token=(((guint64)task->worker)<<32)|i;
  Invocation inv;begin(&inv,99,token,token^0x5a5aULL,task->worker);
  end(&inv,token);token=0;
 }
 return 0;
}
int selftest(guint32 workers,guint32 iterations,guint32 requested_limit){
 if(workers!=4||iterations==0||iterations>10000||requested_limit==0||requested_limit>CAPACITY)return -1;
 hb_lock(hb_state.mutex);
 if(hb_state.pending){hb_unlock(hb_state.mutex);return -2;}
 hb_state.count=0;hb_state.dropped=0;hb_state.serial=0;hb_state.limit=requested_limit;
 hb_unlock(hb_state.mutex);
 Task tasks[4];void *threads[4];
 for(guint32 i=0;i<4;i++){
  tasks[i].worker=i+1;tasks[i].iterations=iterations;
  threads[i]=hb_thread_new("handle-proof",worker,&tasks[i]);
 }
 for(guint32 i=0;i<4;i++)hb_thread_join(threads[i]);return 0;
}`;
const symbols={};
for(const [name,exportName] of Object.entries({hb_clock:'clock_gettime',hb_tid:'gettid',
 hb_lock:'g_mutex_lock',hb_unlock:'g_mutex_unlock',hb_thread_new:'g_thread_new',
 hb_thread_join:'g_thread_join',memcpy:'memcpy',memset:'memset'}))symbols[name]=Module.getGlobalExportByName(exportName);
const allocated=72*50000*2+256,state=Memory.alloc(allocated);
state.add(72*50000*2).writeByteArray(new Uint8Array(256));symbols.hb_state=state;
const module=new CModule(source,symbols,{toolchain:'internal'});
const fn=(name,type,args=[])=>new NativeFunction(module[name],type,args);
const stateSize=fn('state_size','uint')(),recordSize=fn('record_size','uint')();
if(stateSize>allocated||recordSize!==72)throw new Error('Unexpected handle buffer ABI');
fn('initialize','void')();
const cell=state.add(stateSize-8);cell.writeU64(uint64('0x123456789abcdef'));
if(fn('canary_read','uint64')().toString(16)!=='123456789abcdef')throw new Error('Owned buffer JS-to-C canary failed');
fn('canary_write','void',['uint64'])(uint64('0x1122334455667788'));
if(cell.readU64().toString(16)!=='1122334455667788')throw new Error('Owned buffer C-to-JS canary failed');
const snap=fn('snapshot','uint'),buffer=fn('buffer','pointer'),dropped=fn('dropped','uint'),
 pending=fn('pending','uint'),limit=fn('limit','uint'),end=fn('snapshot_end','uint64'),
 clock=fn('clock_now','uint64'),test=fn('selftest','int',['uint','uint','uint']);
function safe(value){const n=Number(value);if(!Number.isSafeInteger(n)||n<0)throw new Error('Unsafe native integer');return n;}
function result(){
 const count=snap(),base=buffer(),events=[];
 for(let i=0;i<count;i++){
  const p=base.add(i*72),caller=p.add(48).readPointer();
  const own=caller.compare(image.base)>=0&&caller.compare(image.base.add(image.size))<0;
  events.push({id:p.add(68).readU32(),kind:names[p.add(64).readU32()],
   begin_ns:safe(p.readU64()),ready_ns:safe(p.add(8).readU64()),end_ns:safe(p.add(16).readU64()),
   a0:p.add(24).readPointer().toString(),a1:p.add(32).readPointer().toString(),
   value:p.add(40).readPointer().toString(),caller:caller.toString(),
   caller_offset:own?parseInt(caller.sub(image.base).toString(),16):null,
   thread:safe(p.add(56).readU64())});
 }
 events.sort((a,b)=>a.id-b.id);
 return {protocol:'native-handle-buffer-v1',pid:Process.id,offsets,events,
  record_size:72,capacity:50000,limit:limit(),dropped:dropped(),pending:pending(),
  snapshot_end_ns:safe(end()),clock_domain:'CLOCK_MONOTONIC',toolchain:'internal',
  storage:{allocated_bytes:allocated,state_bytes:stateSize,canary_verified:true},
  per_event_javascript:false,runtime_subscription_added:false,snapshot_requested:false,gc_requested:false};
}
if(!selfOnly){
 for(const [kind,offset] of Object.entries(offsets)){
  const address=image.base.add(offset);
  const bytes=Array.from(new Uint8Array(address.readByteArray(4))).map(x=>x.toString(16).padStart(2,'0')).join('');
  if(bytes!=='f30f1efa')throw new Error('Wrong entry: '+kind);
  Interceptor.attach(address,{onEnter:module.on_enter,onLeave:module.on_leave},ptr(names.indexOf(kind)));
 }
}
rpc.exports={clock:()=>safe(clock()),result,selftest(workers,iterations,requestedLimit){
 if(!selfOnly)throw new Error('Selftest forbidden in live capture');
 if(test(workers,iterations,requestedLimit)!==0)throw new Error('Handle buffer selftest failed');return result();
}};
send({handle_buffer_ready:!selfOnly,selftest_ready:selfOnly,pid:Process.id});
