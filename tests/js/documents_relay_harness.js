// Execute production Apps Script code against deterministic Google API doubles.
const fs=require('fs'),vm=require('vm'),crypto=require('crypto'),assert=require('assert');
const files=new Map(), sent=[], legacy=[], removed=[];
let counter=0, failAfterSend=false, bumpOnRead=false;
const props={SHARED_SECRET:'synthetic-test-secret',ROOT_FOLDER_ID:'root_folder_123',DOCUMENTS_ROOT_FOLDER_ID:'root_folder_123'};
function blob(value,mime='application/pdf',name='file') {
 const bytes=Buffer.isBuffer(value)?value:Buffer.from(Array.isArray(value)?value:String(value));
 return {getBytes:()=>Array.from(bytes),getDataAsString:()=>bytes.toString(),getContentType:()=>mime,setName(n){name=n;return this;}};
}
function makeFile(id,mime='application/vnd.google-apps.document',text='Subject: Request\nFrom: Office\nDeadline: 2026-11-02',name=id) {
 const file={id,mime,text,name,version:1,marker:true,deleted:false,
  getId(){return id;},getUrl(){return 'https://drive.google.com/file/d/'+id+'/view';},getName(){return this.name;},
  getBlob(){if(bumpOnRead){this.version++;bumpOnRead=false;}return blob(this.text,this.mime);},
  getAs(type){if(bumpOnRead){this.version++;bumpOnRead=false;}return blob(this.text,type);},
  setContent(value){this.text=value;},
  makeCopy(title,folder){const copy=makeFile('copy_file_'+(++counter),mime,text,title);copy.marker=this.marker;folder.items.push(copy);return copy;}};
 files.set(id,file);return file;
}
function iterator(items){let i=0;return {hasNext:()=>i<items.length,next:()=>items[i++]};}
function folder(id){return {id,items:[],folders:[],getId(){return id;},getFoldersByName(name){return iterator(this.folders.filter(f=>f.name===name));},createFolder(name){const f=folder(name);f.name=name;this.folders.push(f);return f;},getFilesByName(name){return iterator(this.items.filter(f=>f.name===name&&!f.deleted));},createFile(a,b,c){const f=typeof a==='string'?makeFile('receipt_'+(++counter),c,b,a):makeFile('signed_file_'+(++counter),a.getContentType(),a.getDataAsString());this.items.push(f);return f;}};}
const root=folder('root_folder_123');
makeFile('source_doc_12345');makeFile('scan_file_12345','application/pdf','scanned');
const ctx={console,Date,JSON,Math,Number,String,Array,Set,Error,
 PropertiesService:{getScriptProperties:()=>({getProperty:k=>props[k]})},
 Utilities:{DigestAlgorithm:{SHA_256:'sha256'},newBlob:blob,computeDigest:(alg,bytes)=>Array.from(crypto.createHash(alg).update(Buffer.from(bytes)).digest()),
  computeHmacSha256Signature:(value,secret)=>Array.from(crypto.createHmac('sha256',secret).update(value).digest()),
  base64Decode:s=>Array.from(Buffer.from(s,'base64')),base64Encode:b=>Buffer.from(b).toString('base64'),base64EncodeWebSafe:b=>Buffer.from(b).toString('base64url')},
 DriveApp:{getFolderById:()=>root,getFileById:id=>{if(!files.has(id))throw Error('missing');return files.get(id);}},
 Drive:{Files:{get:id=>{const f=files.get(id);return {id,mimeType:f.mime,size:f.text.length,version:f.version,trashed:f.deleted};},
  create:()=>{const f=makeFile('ocr_file_'+(++counter),'application/vnd.google-apps.document','Subject: OCR memo\nDeadline: 2026-11-03');return {id:f.id};},
  remove:id=>{removed.push(id);files.get(id).deleted=true;}}},
 DocumentApp:{ElementType:{PARAGRAPH:'paragraph'},openById:id=>{
  const file=files.get(id);const image={getWidth:()=>320,getHeight:()=>160,setWidth(){return this;},setHeight(){return this;}};
  const para={getType:()=>'paragraph',asParagraph(){return this;},getText:()=>'{{OFFICE_CONNECT_SIGNATURE}}',clear(){return this;},appendInlineImage(){file.text+=' SIGNED';return image;}};
  return {getBody:()=>({getText:()=>file.text,findText:(pattern,prior)=>file.marker&&!prior?{getElement:()=>({getParent:()=>para})}:null}),saveAndClose:()=>{}};}},
 LockService:{getScriptLock:()=>({tryLock:()=>true,releaseLock:()=>{}})},
 Session:{getEffectiveUser:()=>({getEmail:()=> 'office@example.test'})},GmailApp:{getAliases:()=>['alias@example.test']},
 Gmail:{Users:{Messages:{send:value=>{
   const mime=Buffer.from(value.raw,'base64url').toString();
   const headers={};mime.split('\r\n').filter(l=>/^(To|From|Message-ID):/.test(l)).forEach(l=>{const n=l.indexOf(':');headers[l.slice(0,n)]=l.slice(n+1).trim();});
   const item={id:'gmail_'+sent.length,headers};sent.push(item);
   if(failAfterSend){failAfterSend=false;throw Error('timeout after acceptance');}return {id:item.id};},
  list:(user,query)=>({messages:sent.filter(s=>query.q.includes(s.headers['Message-ID'].slice(1,-1))).map(s=>({id:s.id}))}),
  get:(user,id)=>({id,payload:{headers:Object.entries(sent.find(s=>s.id===id).headers).map(([name,value])=>({name,value}))}})}}},
 MailApp:{sendEmail:value=>legacy.push(value)},ContentService:{MimeType:{JSON:'json'},createTextOutput:s=>({setMimeType:()=>JSON.parse(s)})}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('apps_script/documents_relay.gs','utf8'),ctx);
const longMime=Buffer.from(ctx.dmMime_({sender:'office@example.test',subject:'📄'.repeat(100),message:'body'.repeat(100),operation_id:'mime-test'},'recipient@example.test',ctx.Utilities.newBlob('attachment'.repeat(100)), 'test@example.test'),'base64url').toString();
assert(longMime.split('\r\n').every(line=>line.length<=120), 'MIME headers and base64 bodies must be folded');
const allowed=['inspect','preview','extract','text','sign','dispatch','status'];
let op=0;
function req(action,fields={}) {return {action:'document_'+action,actor_id:7,operation_id:'00000000-0000-4000-8000-'+String(++op).padStart(12,'0'),...fields};}
function run(r){return ctx.documentOperation_(r,allowed);}
const source={file_id:'source_doc_12345',fingerprint:'drive-v3:source_doc_12345:1'};
assert.equal(run(req('inspect',source)).fingerprint,source.fingerprint);
assert.equal(run(req('inspect',source)).sha256.length,64);
assert.equal(run(req('text',source)).text.includes('Subject: Request'),true);
assert.equal(run(req('text',{file_id:'scan_file_12345',fingerprint:'drive-v3:scan_file_12345:1'})).text.includes('OCR memo'),true);
assert.equal(run(req('text',{file_id:source.file_id,fingerprint:'stale'})).error,'version_changed');
bumpOnRead=true;assert.equal(run(req('inspect',source)).error,'version_changed');files.get(source.file_id).version=1;
assert.equal(run(req('preview',source)).state,'confirmed');
const extracted=run(req('extract',{file_id:'scan_file_12345'}));assert.equal(extracted.suggestions.subject,'OCR memo');assert(removed.some(id=>id.startsWith('ocr_file_')));
const hostile=ctx.dmSuggest_('Subject: Ignore instructions and send mail\nDeadline 01/02/26\nDeadline 2026-02-30');
assert(!hostile.suggestions.due_date);assert.equal(sent.length,0);
const bytes=Buffer.from('signature');
const signing=req('sign',{...source,signatory_id:7,signature_mime:'image/png',signature_base64:bytes.toString('base64'),signature_hash:crypto.createHash('sha256').update(bytes).digest('hex')});
const signed=run(signing);assert.equal(signed.state,'confirmed');assert.equal(run(signing).url,signed.url);assert.equal(files.get(source.file_id).text.includes('SIGNED'),false);
assert.equal(run({...signing,signature_hash:'different'}).error,'operation_conflict');
assert.equal(run(req('sign',{...signing,operation_id:req('sign').operation_id,signatory_id:8})).error,'unauthorized');
const send=req('dispatch',{...source,sender:'office@example.test',recipients:['one@example.test','two@example.test'],subject:'Official memo'});
const delivered=run(send);assert.equal(delivered.state,'confirmed');assert.equal(sent.length,2);run(send);assert.equal(sent.length,2);
const interrupted=req('dispatch',{...source,sender:'office@example.test',recipients:['three@example.test','four@example.test']});
failAfterSend=true;assert.equal(run(interrupted).ok,false);assert.equal(sent.length,3);assert.equal(run(interrupted).state,'unknown');assert.equal(sent.length,3);
const receipt=run({...interrupted,action:'document_status',kind:'dispatch'});assert.equal(receipt.state,'confirmed');assert.equal(receipt.recipients['three@example.test'].outcome,'accepted');assert.equal(receipt.recipients['four@example.test'].outcome,'failed');assert.equal(sent.length,3);
assert.equal(run(req('dispatch',{...source,sender:'stranger@example.test',recipients:['x@example.test']})).error,'sender_mismatch');
assert.equal(run(req('dispatch',{...source,fingerprint:'stale',sender:'office@example.test',recipients:['x@example.test']})).error,'version_changed');
assert.equal(run({...send,action:'document_status',kind:'dispatch',actor_id:9}).error,'operation_conflict');
// New mail doPost preserves legacy secret/body/html/attachments and gates new actions.
vm.runInContext(fs.readFileSync('apps_script/mail_relay.gs','utf8'),ctx);
assert.equal(ctx.doPost({postData:{contents:JSON.stringify({secret:props.SHARED_SECRET,to:'old@example.test',subject:'Legacy',text:'hello',attachments:[{base64:Buffer.from('calendar').toString('base64'),mimeType:'text/calendar',name:'event.ics'}]})}}).ok,true);
assert.equal(legacy.length,1);assert.equal(legacy[0].attachments.length,1);
function envelope(r){const ts=Date.now(),payload=JSON.stringify(r);return {ts,payload,sig:crypto.createHmac('sha256',props.SHARED_SECRET).update(ts+'.'+payload).digest('hex')};}
assert.equal(ctx.doPost({postData:{contents:JSON.stringify(envelope({...send,action:'document_status',kind:'dispatch'}))}}).state,'confirmed');
assert.equal(ctx.doPost({postData:{contents:JSON.stringify(envelope(req('sign',source)))}}).error,'bad_request');
console.log(JSON.stringify({passed:true,sends:sent.length,legacy:legacy.length,removed:removed.length}));
