const fs=require('fs'),vm=require('vm'),crypto=require('crypto'),assert=require('assert');
const secret='test-only-secret-with-at-least-32-characters';
let offset=0,runCount=0;
class Clock extends Date {constructor(...args){super(...(args.length?args:[Date.now()+offset]));}static now(){return Date.now()+offset;}}
let props,files,counter,requests,downloads,failCreate,failPost,failSave,locked,permissionFailure,replyCode,scanPage,queueReply;
const hash=(alg,b)=>crypto.createHash(alg).update(Buffer.from(b)).digest();
function blob(value,mime,name){const b=Buffer.from(Array.isArray(value)?value:String(value));return {bytes:b,getBytes:()=>Array.from(b),getDataAsString:()=>b.toString()};}
const candidate={mailbox:'office@example.test',message_id:'19abc123',subject:'Mémo for review',sender:'Office A',received_at:'2026-10-17T00:00:00Z',ready_for_import:true,
 attachments:[{attachment_id:'attachment1',filename:'memo.pdf',mime_type:'application/pdf',size:4},{attachment_id:'attachment2',filename:'memo2.pdf',mime_type:'application/pdf',size:4}]};
function reset(){
 offset=0;runCount=0;
 props={GMAIL_DOCUMENTS_IMPORT_ENABLED:'true',GMAIL_DOCUMENTS_FOLDER_ID:'private_folder123',GMAIL_DOCUMENTS_INTAKE_URL:'https://css.example.test/integrations/gmail/documents',CSS_GMAIL_INTAKE_SECRET:secret};
 files=new Map();counter=0;requests=[];downloads=0;failCreate='';failPost=false;failSave=false;locked=false;permissionFailure=false;replyCode=201;queueReply=false;
 scanPage={candidates:[candidate],excluded:[],errors:[],next_page_token:null};
}
reset();
const context={Date:Clock,JSON,Math,Number,String,Array,Set,Error,console:{log:()=>{}},
 GDI_MAX_BYTES:20*1024*1024,
 gdiHeader_:(part,name)=>(part.headers || []).find(h=>h.name.toLowerCase()===name)?.value || '',
 gdiConfig_:()=>({mailbox:'office@example.test',label:'CSS-Documents',startMs:0,pageSize:25}),
 gdiDiscoverPage_:()=>scanPage,
 PropertiesService:{getScriptProperties:()=>({getProperties:()=>({...props}),getProperty:k=>props[k],setProperty:(k,v)=>{props[k]=v;},deleteProperty:k=>{delete props[k];}})},
 Session:{getEffectiveUser:()=>({getEmail:()=> 'operator@example.test'})},
 LockService:{getScriptLock:()=>({tryLock:()=>!locked,releaseLock:()=>{}})},
 Utilities:{DigestAlgorithm:{SHA_256:'sha256',MD5:'md5'},newBlob:blob,
 computeDigest:(alg,bytes)=>Array.from(hash(alg,bytes)),base64DecodeWebSafe:s=>Array.from(Buffer.from(s,'base64url')),
 computeHmacSha256Signature:(body,key)=>Array.from(crypto.createHmac('sha256',key).update(body).digest())},
 Gmail:{Users:{getProfile:()=>({emailAddress:'office@example.test'}),Messages:{Attachments:{get:()=>{downloads++;return {data:Buffer.from('DATA').toString('base64url')};}}}}},
 Drive:{Files:{generateIds:()=>({ids:['reserved_file_'+(++counter)]}),
 get:id=>{
  if(id==='private_folder123')return {mimeType:'application/vnd.google-apps.folder',capabilities:{canAddChildren:true}};
  if(permissionFailure)throw Error('permission denied');
  if(!files.has(id))throw Error('File not found: '+id);
  return files.get(id).meta;
 },
 create:(meta,b)=>{
  if(files.has(meta.id))throw Error('409 conflict');
  files.set(meta.id,{meta:{...meta,size:b.bytes.length,md5Checksum:hash('md5',b.bytes).toString('hex')},body:b.bytes.toString()});
  if(failCreate && ((failCreate==='attachment' && meta.appProperties.gdi_attachment) || (failCreate==='receipt' && meta.appProperties.gdi_receipt))){failCreate='';throw Error('Timeout after create');}
  return {id:meta.id};
 },
 update:(_,id,b)=>{
  const parsed=JSON.parse(b.bytes.toString());
  if(failSave && ['registered','queued'].includes(parsed.state)){failSave=false;throw Error('Receipt write failed');}
  files.get(id).body=b.bytes.toString();return {id};
 }}},
 DriveApp:{getFileById:id=>({getBlob:()=>blob(files.get(id).body)})},
 UrlFetchApp:{fetch:(url,options)=>{
  assert.equal(url,props.GMAIL_DOCUMENTS_INTAKE_URL);assert.equal(options.followRedirects,false);
  const ts=options.headers['X-CSS-Timestamp'];
  assert.equal(options.headers['X-CSS-Signature'],crypto.createHmac('sha256',secret).update(ts+'.'+options.payload).digest('hex'));
  requests.push(options);
  if(failPost){failPost=false;throw Error('Timeout AFTER registry commit');}
  return {getResponseCode:()=>replyCode,getContentText:()=>JSON.stringify(queueReply ? {intake_id:456,state:'queued',duplicate:requests.length>1} : {document_id:123,duplicate:requests.length>1})};
 }}
};
vm.createContext(context);vm.runInContext(fs.readFileSync('apps_script/gmail_documents_import.gs','utf8'),context);
vm.runInContext(fs.readFileSync('apps_script/gmail_documents_ops.gs','utf8'),context);
const run=()=>{if(runCount++)offset+=3600000;return JSON.parse(JSON.stringify(context.importGmailDocuments()));};
function retry(){props.GMAIL_DOCUMENTS_OPERATOR_REASON='Issue resolved';props.GMAIL_DOCUMENTS_RETRY_RECEIPT_ID=Object.entries(props).find(([k,v])=>k.startsWith('GDI_RECEIPT_'))[1];context.retryGmailDocument();}
let count=0;
function check(name,fn){reset();fn();count++;if(!process.argv.includes('--envelope'))console.log('PASS '+name);}
function attachmentCount(){return [...files.values()].filter(f=>f.meta.appProperties.gdi_attachment).length;}
check('uploads and registers once; completed replay does nothing',()=>{
 assert.equal(run().registered,1);assert.equal(attachmentCount(),2);assert.equal(downloads,2);assert.equal(requests.length,1);
 assert.equal(run().already_registered,1);assert.equal(downloads,2);assert.equal(requests.length,1);
 const body=JSON.parse(requests[0].payload);assert.equal(body.attachments.length,2);assert.equal(body.subject,candidate.subject);
});
check('timeout after attachment create reuses reserved file',()=>{
 failCreate='attachment';assert(run().errors.length>=1);assert.equal(attachmentCount(),1);
 assert.equal(run().registered,1);assert.equal(attachmentCount(),2);assert.equal(downloads,2);
});
check('timeout after receipt creation reuses receipt ID',()=>{
 failCreate='receipt';assert(run().errors.length>=1);assert.equal(run().registered,1);
 assert.equal([...files.values()].filter(f=>f.meta.appProperties.gdi_receipt).length,1);
});
check('timeout after registry commit retries exact payload',()=>{
 failPost=true;assert(run().errors.length>=1);assert.equal(run().already_registered,1);
 assert.equal(requests[0].payload,requests[1].payload);assert.equal(downloads,2);assert.equal(attachmentCount(),2);
});
check('failed final checkpoint retries exact request',()=>{
 failSave=true;assert(run().errors.length>=1);assert.equal(run().already_registered,1);
 assert.equal(requests[0].payload,requests[1].payload);assert.equal(attachmentCount(),2);
});
check('disabled and busy imports make no writes',()=>{
 delete props.GMAIL_DOCUMENTS_IMPORT_ENABLED;assert.equal(run().state,'paused');assert.equal(files.size,0);
 props.GMAIL_DOCUMENTS_IMPORT_ENABLED='true';locked=true;assert.equal(run().state,'busy');assert.equal(files.size,0);
});
check('permission failure does not allocate alternate files',()=>{
 permissionFailure=true;assert(run().errors.length>=1);assert.equal(files.size,0);
 const reserved=counter;assert(run().errors.length>=1);assert.equal(counter,reserved);
});
check('HTTP errors remain retryable without uploads',()=>{
 replyCode=409;assert.equal(run().errors[0].reason,'intake_http_409');const size=files.size;
 replyCode=201;retry();assert.equal(run().already_registered,1);assert.equal(files.size,size);assert.equal(downloads,2);
});
check('changed endpoint rejected for an unfinished receipt',()=>{
 failPost=true;run();props.GMAIL_DOCUMENTS_INTAKE_URL='https://other.example.test/integrations/gmail/documents';
 assert(run().errors.length>=1);assert.equal(requests.length,1);assert.equal(attachmentCount(),2);
});
check('missing metadata skipped; cursor advances and resets',()=>{
 scanPage={candidates:[{...candidate,ready_for_import:false}],excluded:[],errors:[],next_page_token:'page2'};
 assert.equal(run().needs_review,1);assert.equal(files.size,0);assert(Object.values(props).includes('page2'));
 scanPage.next_page_token=null;run();assert(!Object.values(props).includes('page2'));
});
check('checksum detects a changed file after interrupted upload',()=>{
 failCreate='attachment';run();const file=[...files.values()].find(f=>f.meta.appProperties.gdi_attachment);file.meta.md5Checksum='changed';
 assert(run().errors.length>=1);assert.equal(requests.length,0);assert.equal(attachmentCount(),1);
});
check('wrong byte count never uploads attachment',()=>{
 scanPage.candidates=[{...candidate,attachments:[{...candidate.attachments[0],size:10}]}];
 assert(run().errors.length>=1);assert.equal(attachmentCount(),0);assert.equal(requests.length,0);
});
check('redirect is not followed and leaves submission pending',()=>{
 replyCode=302;assert.equal(run().errors[0].reason,'intake_http_302');assert.equal(requests.length,1);
 replyCode=200;assert.equal(run().already_registered,1);assert.equal(requests[0].payload,requests[1].payload);
});
check('metadata changes cannot alter a previously submitted payload',()=>{
 failPost=true;run();scanPage.candidates=[{...candidate,subject:'Changed after timeout'}];
 assert.equal(run().already_registered,1);assert.equal(requests[0].payload,requests[1].payload);
});
check('backoff prevents immediate retries and health records failure',()=>{
 failPost=true;run();const report=JSON.parse(JSON.stringify(context.importGmailDocuments()));
 assert.equal(requests.length,1);assert(report.deferred>=1);assert.equal(JSON.parse(props.GDI_HEALTH).state,'waiting_retry');
 const status=context.gmailDocumentsStatus();assert.equal(status.receipts[0].attempts,1);
 assert(status.receipts[0].history.some(h=>h.action==='failed'));assert(status.runs.length>=2);
 assert(!JSON.stringify(status).includes(secret));
});
check('recovery succeeds when Gmail no longer returns the message',()=>{
 failPost=true;run();scanPage.candidates=[];assert.equal(run().already_registered,1);
 assert.equal(requests[0].payload,requests[1].payload);assert.equal(attachmentCount(),2);
});
check('recovery succeeds even when discovery fails',()=>{
 failPost=true;run();const discover=context.gdiDiscoverPage_;context.gdiDiscoverPage_=()=>{throw Error('SECRET_PROVIDER_ERROR');};
 const r=run();context.gdiDiscoverPage_=discover;
 assert.equal(r.already_registered,1);assert(r.errors.some(e=>e.reason==='gmail_discovery_failed'));
 assert(!props.GDI_HEALTH.includes('SECRET_PROVIDER_ERROR'));
});
check('eight failed attempts stop automatic retries until operator action',()=>{
 replyCode=500;for(let i=0;i<8;i++)run();const status=context.gmailDocumentsStatus();
 assert.equal(status.receipts[0].state,'needs_attention');assert.equal(requests.length,8);
 run();assert.equal(requests.length,8);replyCode=200;retry();assert.equal(run().already_registered,1);
 assert.equal(requests[0].payload,requests[8].payload);
});
check('pause and resume require reason and preserve receipts',()=>{
 run();assert.throws(()=>context.pauseGmailDocuments(),/reason/);
 props.GMAIL_DOCUMENTS_OPERATOR_REASON='Maintenance';assert.equal(context.pauseGmailDocuments().state,'paused');
 const total=files.size;assert.equal(run().state,'paused');assert.equal(files.size,total);
 props.GMAIL_DOCUMENTS_OPERATOR_REASON='Maintenance completed';assert.equal(context.resumeGmailDocuments().state,'ready');
 assert.equal(run().already_registered,1);assert.equal(requests.length,1);
 const controls=context.gmailDocumentsStatus().controls;assert.equal(controls.length,2);assert.equal(controls[0].actor,'operator@example.test');
});
check('operator cannot reset a completed or unknown receipt',()=>{
 run();assert.throws(retry,/already_registered/);props.GMAIL_DOCUMENTS_RETRY_RECEIPT_ID='unknown';
 assert.throws(()=>context.retryGmailDocument(),/unknown_receipt/);assert.equal(requests.length,1);
});
check('stale trigger is visible and failed resume stays paused',()=>{
 run();offset+=20*60*1000;assert(context.gmailDocumentsStatus().stale);
 props.GMAIL_DOCUMENTS_OPERATOR_REASON='Pause';context.pauseGmailDocuments();
 props.GMAIL_DOCUMENTS_OPERATOR_REASON='Resume';props.GMAIL_DOCUMENTS_INTAKE_URL='http://bad';
 assert.throws(()=>context.resumeGmailDocuments(),/config/);assert.equal(props.GMAIL_DOCUMENTS_IMPORT_ENABLED,'false');
});
check('pending scan stays bounded and reports unreadable checkpoints',()=>{
 for(let i=0;i<25;i++)props['GDI_RECEIPT_test'+String(i).padStart(2,'0')]='missing_'+i;
 scanPage.candidates=[];const r=run();assert.equal(r.errors.length,20);assert.equal(props.GDI_RECOVERY_OFFSET,'20');
 assert.equal(run().errors.length,5);assert.equal(props.GDI_RECOVERY_OFFSET,'0');
});
check('wrong mailbox stops recovery before any external effect',()=>{
 failPost=true;run();const profile=context.Gmail.Users.getProfile;
 context.Gmail.Users.getProfile=()=>({emailAddress:'wrong@example.test'});
 assert.throws(run,/mailbox_mismatch/);assert.equal(requests.length,1);assert.equal(attachmentCount(),2);
 context.Gmail.Users.getProfile=profile;
});
check('queue handoff is terminal and reports its intake ID',()=>{
 queueReply=true;assert.equal(run().queued,1);
 assert.equal(run().already_queued,1);assert.equal(requests.length,1);assert.equal(downloads,2);
 const status=context.gmailDocumentsStatus();assert.equal(status.receipts[0].intake_id,456);
 assert.equal(status.receipts[0].state,'queued');assert.throws(retry,/already_queued/);
 assert([...files.values()].every(f=>['gmail_attachment','gmail_receipt'].includes(f.meta.properties.office_intake)));
});
check('lost queue acknowledgement retries exact request without reupload',()=>{
 queueReply=true;failPost=true;assert(run().errors.length>=1);
 assert.equal(run().already_queued,1);assert.equal(requests[0].payload,requests[1].payload);
 assert.equal(attachmentCount(),2);assert.equal(downloads,2);
});
check('failed queued checkpoint recovers even after attachments are filed',()=>{
 queueReply=true;failSave=true;assert(run().errors.length>=1);
 [...files.values()].filter(f=>f.meta.appProperties.gdi_attachment).forEach(f=>f.meta.parents=['filed_folder']);
 assert.equal(run().already_queued,1);assert.equal(downloads,2);assert.equal(requests.length,2);
});
check('body-only import pins body, skips uploads, and recovers without rereading mail',()=>{
 queueReply=true;scanPage.candidates=[{...candidate,attachments:[],body_only:true}];
 let reads=0;context.Gmail.Users.Messages.get=()=>{reads++;return {payload:{mimeType:'multipart/alternative',parts:[
 {mimeType:'text/html',body:{data:Buffer.from('<p>HTML fallback</p>').toString('base64url')}},
 {mimeType:'text/plain',body:{data:Buffer.from('Please review.\nThank you.').toString('base64url')}}]}};};
 failPost=true;assert(run().errors.length);assert.equal(run().already_queued,1);
 assert.equal(reads,1);assert.equal(downloads,0);assert.equal(attachmentCount(),0);
 assert.equal(JSON.parse(requests[0].payload).body_text,'Please review.\nThank you.');
 assert.equal(requests[0].payload,requests[1].payload);
 assert(!JSON.stringify(context.gmailDocumentsStatus()).includes('Please review.'));
});
check('HTML-only body is converted to text and oversized content is not truncated',()=>{
 context.Gmail.Users.Messages.get=()=>({payload:{mimeType:'text/html',body:{data:Buffer.from('<style>hidden</style><p>Hello &amp; welcome</p><script>bad()</script><p>Next</p>').toString('base64url')}}});
 assert.equal(context.gdiBodyText_('19abc'),'Hello & welcome\nNext');
 context.Gmail.Users.Messages.get=()=>({payload:{mimeType:'text/plain',body:{data:Buffer.from('x'.repeat(16001)).toString('base64url')}}});
 assert.throws(()=>context.gdiBodyText_('19abc'),/too_large/);
});
if(process.argv.includes('--envelope')){
 reset();run();console.log(JSON.stringify({body:requests[0].payload,headers:requests[0].headers}));
}else console.log(count+' Gmail importer contracts passed');
