const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const files=new Map();let serial=0,moves=0,loseReply=false;
const folder=(id,parent,name)=>({id,name,mimeType:'application/vnd.google-apps.folder',driveId:'office_drive',parents:parent?[parent]:[],version:'1'});
files.set('inbox_folder_123',folder('inbox_folder_123',null,'To Review'));
files.set('filed_folder_123',folder('filed_folder_123',null,'Filed'));
files.set('scan_file_123456',{id:'scan_file_123456',name:'scan.pdf',mimeType:'application/pdf',parents:['inbox_folder_123'],version:'1',size:'42',md5Checksum:'original-content'});
const properties={DOCUMENTS_INTAKE_FOLDER_ID:'inbox_folder_123',DOCUMENTS_FILED_FOLDER_ID:'filed_folder_123'};
const ctx={console,Date,JSON,Math,Number,String,Array,Set,Error,
 PropertiesService:{getScriptProperties:()=>({getProperty:k=>properties[k]})},
 Utilities:{DigestAlgorithm:{SHA_256:'sha256'},newBlob:x=>({getBytes:()=>Buffer.from(x)}),computeDigest:(alg,x)=>Array.from(crypto.createHash(alg).update(Buffer.from(x)).digest())},
 LockService:{getScriptLock:()=>({tryLock:()=>true,releaseLock:()=>{}})},
 Drive:{Files:{
  get:id=>JSON.parse(JSON.stringify(files.get(id))),
  list:opts=>{assert.equal(opts.corpora,files.get('inbox_folder_123').driveId?'drive':'user');if(opts.corpora==='user')assert(!('driveId' in opts));const parent=opts.q.match(/^'([^']+)' in parents/)[1];const match=opts.q.match(/and name = '([^']+)'/);return {files:[...files.values()].filter(f=>f.parents.includes(parent)&&(!match||f.name===match[1])&&(!opts.q.includes("mimeType !=")||f.mimeType!=='application/vnd.google-apps.folder'))};},
  create:meta=>{const id='new_folder_'+(++serial);const f=folder(id,meta.parents[0],meta.name);if(!files.get(meta.parents[0]).driveId)delete f.driveId;files.set(id,f);return {id};},
  update:(meta,id,blob,opts)=>{const f=files.get(id);Object.assign(f,meta,{parents:[opts.addParents],version:String(Number(f.version)+1)});moves++;if(loseReply){loseReply=false;throw Error('lost response after update');}return {id};}
 }}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('apps_script/documents_relay.gs','utf8'),ctx);
const allowed=['intake_list','intake_check','intake_file'];let op=0;
function req(kind,fields={}){return {action:'document_'+kind,actor_id:7,operation_id:'00000000-0000-4000-8000-'+String(++op).padStart(12,'0'),inbox:'inbox_folder_123',...fields};}
function run(r){return ctx.documentOperation_(r,allowed);}
assert.equal(run(req('intake_list')).files.length,1);
// Public source markers work when importer and relay use different projects.
files.get('scan_file_123456').properties={office_intake:'gmail_attachment'};
assert.equal(run(req('intake_list')).files[0].email_attachment,true);
files.get('scan_file_123456').properties={office_intake:'gmail_receipt'};
assert.equal(run(req('intake_list')).files[0].email_receipt,true);
files.get('scan_file_123456').properties={};

assert.equal(run(req('intake_list',{inbox:'wrong_folder_123'})).error,'not_configured');
const source={file_id:'scan_file_123456',fingerprint:'drive-v3:scan_file_123456:1'};
assert.equal(run(req('intake_check',source)).state,'confirmed');
assert.equal(run(req('intake_check',{...source,fingerprint:'stale'})).error,'version_changed');
const filing=req('intake_file',{...source,filed:'filed_folder_123',number:'BLHSD-IN-2026-000001',direction:'IN',year:'2026',ordinal:1});
loseReply=true;assert.equal(run(filing).ok,false);assert.equal(moves,1);
const retried=run(filing);assert.equal(retried.state,'confirmed');assert.equal(moves,1);assert.equal(serial,2);
assert.equal(files.get(source.file_id).name,'BLHSD-IN-2026-000001 - Original Scan.pdf');
assert.equal(run(req('intake_list')).files.length,0);
assert.equal(run({...filing,number:'BLHSD-IN-2026-000002'}).error,'operation_conflict');
files.get(source.file_id).md5Checksum='changed';assert.equal(run(filing).error,'operation_conflict');
// The office uses shared folders inside My Drive; run the same filing path.
for(const f of files.values())delete f.driveId;
files.set('mydrive_scan_12345',{id:'mydrive_scan_12345',name:'office.pdf',mimeType:'application/pdf',parents:['inbox_folder_123'],version:'1',size:'42',md5Checksum:'office-content'});
assert.equal(run(req('intake_list')).files.length,1);
const mySource={file_id:'mydrive_scan_12345',fingerprint:'drive-v3:mydrive_scan_12345:1'};
assert.equal(run(req('intake_check',mySource)).state,'confirmed');
const myFiling=req('intake_file',{...mySource,filed:'filed_folder_123',number:'BLHSD-IN-2026-000002',direction:'IN',year:'2026',ordinal:1});
const before=moves;loseReply=true;assert.equal(run(myFiling).ok,false);
assert.equal(run(myFiling).state,'confirmed');assert.equal(moves,before+1);
files.get('filed_folder_123').driveId='another_drive';
assert.equal(run({...myFiling,operation_id:'00000000-0000-4000-8000-999999999999'}).error,'bad_folder');
console.log('Drive intake: discovery, boundaries, stale source, move/rename and lost-reply recovery passed');
