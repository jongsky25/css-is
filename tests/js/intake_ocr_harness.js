// Real extraction code with content/version changes injected around source reads.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
let version=1,text='Original scan bytes',mode='',created=0;const removed=[];
let parents=['inbox_folder_123'];
const checksum=()=>crypto.createHash('md5').update(text).digest('hex');
const asBlob=value=>({getBytes:()=>Array.from(Buffer.from(value)),getDataAsString:()=>value});
const props={DOCUMENTS_INTAKE_FOLDER_ID:'inbox_folder_123'};
const ctx={console,Date,JSON,Math,Number,String,Array,Set,Error,
 PropertiesService:{getScriptProperties:()=>({getProperty:k=>props[k]})},
 Utilities:{DigestAlgorithm:{MD5:'md5',SHA_256:'sha256'},newBlob:asBlob,
  computeDigest:(alg,data)=>Array.from(crypto.createHash(alg).update(Buffer.from(data)).digest())},
 Drive:{Files:{get:id=>id==='inbox_folder_123'?{id,mimeType:'application/vnd.google-apps.folder',trashed:false}:
  {id,name:'scan.pdf',mimeType:'application/pdf',size:Buffer.byteLength(text),version:String(version),md5Checksum:checksum(),parents:[...parents],trashed:false},
  create:()=>{created++;if(mode==='content_during_ocr') {text+=' changed during OCR';version++;}if(mode==='metadata_during_ocr')version++;return {id:'temp_ocr_'+created};},
  remove:id=>removed.push(id)}},
 DriveApp:{getFileById:()=>({getBlob:()=>{
  if(mode==='metadata_on_read'){version++;mode='';}
  if(mode==='content_on_read'){text='Different content';version++;mode='';}
  return asBlob(text);
 }})},
 DocumentApp:{openById:()=>({getBody:()=>({getText:()=> 'Subject: Extracted request\nFrom: Regional Office'})})}
};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('apps_script/documents_relay.gs','utf8'),ctx);
let op=0;
const req=fields=>({action:'document_extract',actor_id:7,operation_id:'00000000-0000-4000-8000-'+String(++op).padStart(12,'0'),
 file_id:'scan_file_12345',intake:true,inbox:'inbox_folder_123',content_key:checksum(),fingerprint:'stale-version',...fields});
const run=r=>ctx.documentOperation_(r,['extract']);
let r=run(req());assert.equal(r.state,'confirmed');assert.equal(r.suggestions.subject,'Extracted request');assert.equal(r.content_key,checksum());
assert.equal(r.fingerprint,'drive-v3:scan_file_12345:1');
mode='metadata_on_read';r=run(req());assert.equal(r.state,'confirmed');assert.equal(r.fingerprint,'drive-v3:scan_file_12345:2');
mode='metadata_during_ocr';r=run(req());assert.equal(r.state,'confirmed');assert.equal(r.fingerprint,'drive-v3:scan_file_12345:3');mode='';
let call=req();text='Replacement before reading';assert.equal(run(call).error,'version_changed');
call=req();mode='content_on_read';const before=created;assert.equal(run(call).error,'version_changed');assert.equal(created,before);
mode='content_during_ocr';call=req();assert.equal(run(call).error,'version_changed');assert(removed.includes('temp_ocr_'+created));mode='';
call=req();parents=['outside_folder_123'];assert.equal(run(call).error,'version_changed');parents=['inbox_folder_123'];
assert.equal(run(req({inbox:'wrong_folder_123'})).error,'not_configured');
// Registered/legacy extraction still rejects metadata version changes, including during reading.
assert.equal(run(req({intake:false,fingerprint:'stale-version'})).error,'version_changed');
mode='metadata_on_read';call=req({intake:false,fingerprint:'drive-v3:scan_file_12345:'+version});assert.equal(run(call).error,'version_changed');
assert.equal(removed.length,created);
console.log('Intake OCR: content-bound reads, metadata drift, source replacements, folder binding, strict legacy checks and cleanup passed');
