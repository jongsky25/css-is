// Separate diagnostic. No V8 API calls, snapshots, GC requests or object writes.
if (Process.arch !== 'x64' || Process.pointerSize !== 8) throw new Error('Linux x64 required');
const image = Process.getModuleByName('chromium');
const offsets = {state_ctor:0xfd46290,state_dispose:0xfd46800,state_dtor:0xfd46690,
  state_dissociate:0xfd46990,per_ctor:0xfd4bac0,per_dtor:0xfd4bc10,
  extension_ctor:0xad479b0,extension_invalidate:0xad48db0,extension_dtor:0xad48610,
  holder_set:0xd32f710,holder_dtor:0xd32f660,global_create:0x5142d10,
  global_release:0x5143060,global_weak_direct:0x5143150,
  global_weak_field:0x51431a0,gc_epilogue:0x51184b0};
const capacity = 30000, events = [], stacks = new Map(), tracked = new Map();
const constructors = new Set(['state_ctor','per_ctor','extension_ctor','holder_set']);
let serial = 0, dropped = 0, unknownRelease = 0;
const stamp = Memory.alloc(16);
const getTime = new NativeFunction(Module.getGlobalExportByName('clock_gettime'),
  'int',['int','pointer'],{scheduling:'exclusive'});
function clock() {
  if (getTime(1,stamp)!==0) throw new Error('Monotonic clock failed');
  const value=Number(stamp.readS64())*1000000000+Number(stamp.add(8).readS64());
  if (!Number.isSafeInteger(value)||value<=0) throw new Error('Unsafe native clock');
  return value;
}
function add(kind, values={}) {
  if (events.length===capacity) { dropped++; return null; }
  const e={id:++serial,kind,begin_ns:clock(),end_ns:null,
    thread:Process.getCurrentThreadId(),...values};
  events.push(e); return e;
}
function scope(thread) { return stacks.get(thread)||[]; }
function finish(e) { if(e)e.end_ns=clock(); }
for (const [kind,offset] of Object.entries(offsets)) {
  const address=image.base.add(offset);
  if (Array.from(new Uint8Array(address.readByteArray(4))).map(n=>n.toString(16).padStart(2,'0')).join('')!=='f30f1efa')
    throw new Error('Unexpected function entry: '+kind);
  if (kind==='global_create') {
    Interceptor.attach(address,{
      onEnter(args) {
        const scopes=scope(Process.getCurrentThreadId());
        const parent=[...scopes].reverse().find(e=>constructors.has(e.kind));
        this.event=parent?add(kind,{parent:parent.id,owner:parent.owner,object_value:args[1].toString()}):null;
      },
      onLeave(retval) {
        if (!this.event) return;
        this.event.slot=retval.toString();
        if (tracked.has(this.event.slot)) this.event.overlap_with=tracked.get(this.event.slot);
        tracked.set(this.event.slot,this.event.id); finish(this.event);
      }
    });
  } else if (kind==='global_release'||kind==='global_weak_direct'||kind==='global_weak_field') {
    Interceptor.attach(address,{
      onEnter(args) {
        // The sole data read is the live Address** API argument cell. Never read
        // a V8 object, owner field or deferred pointer target.
        const slot=(kind==='global_weak_field'?args[0].readPointer():args[0]).toString();
        this.slot=slot; this.creation=tracked.get(slot);
        const scopes=scope(Process.getCurrentThreadId()), parent=scopes[scopes.length-1];
        this.event=this.creation?add(kind,{slot,creation:this.creation,parent:parent?.id||0}):null;
        if(kind==='global_release'&&!this.creation)unknownRelease++;
      },
      onLeave() {
        finish(this.event);
        if(kind==='global_release'&&this.creation&&tracked.get(this.slot)===this.creation)tracked.delete(this.slot);
      }
    });
  } else {
    Interceptor.attach(address,{
      onEnter(args) {
        const thread=Process.getCurrentThreadId(), scopes=scope(thread);
        const parent=scopes[scopes.length-1];
        this.event=add(kind,{owner:args[0].toString(),argument:args[1].toString(),parent:parent?.id||0});
        if(this.event){scopes.push(this.event);stacks.set(thread,scopes);}
      },
      onLeave() {
        if(!this.event)return;
        const scopes=scope(this.event.thread);
        if(scopes.pop()!==this.event)throw new Error('Context scope nesting changed');
        finish(this.event);
      }
    });
  }
}
rpc.exports={clock,result(){
  return {protocol:'context-handle-journal-v1',pid:Process.id,offsets,
    clock_domain:'CLOCK_MONOTONIC',capacity,dropped,unknown_release_calls:unknownRelease,
    pending:events.filter(e=>e.end_ns===null).length,events,
    memory_read_policy:'only live Address** API argument cell; no V8 object/owner-field reads',
    snapshot_requested:false,gc_requested:false};
}};
send({context_journal_ready:true,pid:Process.id,offsets});
