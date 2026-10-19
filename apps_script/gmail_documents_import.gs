// Phase 3 importer. Requires gmail_documents.gs, Gmail v1 and Drive v3.
// The two opt-in switches must be enabled separately. Never sends email.
function gdiHash_(value) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, Utilities.newBlob(value).getBytes())
    .map(function(b) {return ('0'+(b&255).toString(16)).slice(-2);}).join('');
}
function gdiImportConfig_() {
  const props=PropertiesService.getScriptProperties();
  if (props.getProperty('GMAIL_DOCUMENTS_IMPORT_ENABLED')!=='true') throw new Error('gmail_import_disabled');
  const config=gdiConfig_();
  config.folder=String(props.getProperty('GMAIL_DOCUMENTS_FOLDER_ID') || '');
  config.endpoint=String(props.getProperty('GMAIL_DOCUMENTS_INTAKE_URL') || '');
  config.secret=String(props.getProperty('CSS_GMAIL_INTAKE_SECRET') || '');
  if (!/^[A-Za-z0-9_-]{10,200}$/.test(config.folder) ||
      !/^https:\/\/[A-Za-z0-9.-]+(?::443)?\/integrations\/gmail\/documents$/.test(config.endpoint) || config.secret.length<32) throw new Error('gmail_import_config');
  if(String(Gmail.Users.getProfile('me').emailAddress || '').toLowerCase()!==config.mailbox) throw new Error('gmail_import_mailbox_mismatch');
  // Limit each invocation to five messages; walk pages across invocations.
  config.pageSize=Math.min(config.pageSize,5);
  const folder=Drive.Files.get(config.folder,{fields:'id,mimeType,trashed,capabilities(canAddChildren)',supportsAllDrives:true});
  if (folder.trashed || folder.mimeType!=='application/vnd.google-apps.folder' || !folder.capabilities.canAddChildren) throw new Error('gmail_import_folder');
  config.binding=gdiHash_(JSON.stringify([config.mailbox,config.folder,config.endpoint]));
  return config;
}
function gdiNewId_() { return Drive.Files.generateIds({count:1,space:'drive',type:'files'}).ids[0]; }
function gdiGet_(id) {
  try { return Drive.Files.get(id,{fields:'id,trashed,parents,appProperties,size,md5Checksum',supportsAllDrives:true}); }
  catch(err) {
    // Only a definite not-found permits creation with the RESERVED ID. Other
    // failures (permission, quota, timeout) never justify allocating another ID.
    if (/\b404\b|File not found:/i.test(String(err.message || ''))) return null;
    throw new Error('drive_read_unconfirmed');
  }
}
function gdiSaveReceipt_(id, receipt) {
  Drive.Files.update({},id,Utilities.newBlob(JSON.stringify(receipt),'application/json'),{fields:'id',supportsAllDrives:true});
}
function gdiReceipt_(config,candidate) {
  const props=PropertiesService.getScriptProperties();
  const key='GDI_RECEIPT_'+gdiHash_(config.mailbox+'\n'+candidate.message_id);
  let id=props.getProperty(key);
  if (!id) {
    id=gdiNewId_();
    // Tiny durable index entry, BEFORE any Drive create. Quota failure stops here.
    props.setProperty(key,id);
  }
  let meta=gdiGet_(id);
  if (!meta) {
    const receipt={binding:config.binding,mailbox:config.mailbox,message_id:candidate.message_id,
      state:'pending',candidate:candidate,files:[],payload:null,document_id:null};
    Drive.Files.create({id:id,name:key+'.json',mimeType:'application/json',parents:[config.folder],
      properties:{office_intake:'gmail_receipt'},appProperties:{gdi_receipt:key}},Utilities.newBlob(JSON.stringify(receipt),'application/json'),{fields:'id',supportsAllDrives:true});
    meta=gdiGet_(id);
  }
  if (!meta || meta.trashed || !(meta.parents || []).includes(config.folder) || (meta.appProperties || {}).gdi_receipt!==key) throw new Error('receipt_location_conflict');
  const receipt=JSON.parse(DriveApp.getFileById(id).getBlob().getDataAsString('UTF-8'));
  if (receipt.binding!==config.binding || receipt.mailbox!==config.mailbox || receipt.message_id!==candidate.message_id) throw new Error('receipt_binding_conflict');
  return {id:id,value:receipt};
}
function gdiUpload_(config, saved, attachment) {
  const receipt=saved.value;
  let file=receipt.files.find(function(item) {return item.attachment_id===attachment.attachment_id;});
  if (!file) {
    file={attachment_id:attachment.attachment_id,id:gdiNewId_(),uploaded:false};
    receipt.files.push(file);
    gdiSaveReceipt_(saved.id,receipt); // reserve before upload
  }
  const identity=gdiHash_(config.mailbox+'\n'+receipt.message_id+'\n'+attachment.attachment_id);
  let meta=gdiGet_(file.id);
  if (!meta) {
    if (file.uploaded) throw new Error('imported_file_missing');
    const data=Gmail.Users.Messages.Attachments.get('me',receipt.message_id,attachment.attachment_id);
    if (typeof data.data!=='string' || data.data.length>Math.ceil(GDI_MAX_BYTES/3)*4+4) throw new Error('attachment_size');
    const bytes=Utilities.base64DecodeWebSafe(data.data);
    if (bytes.length!==attachment.size || bytes.length>GDI_MAX_BYTES || bytes.length===0) throw new Error('attachment_size');
    file.md5=Utilities.computeDigest(Utilities.DigestAlgorithm.MD5,bytes)
      .map(function(b) {return ('0'+(b&255).toString(16)).slice(-2);}).join('');
    gdiSaveReceipt_(saved.id,receipt); // checksum before external effect
    Drive.Files.create({id:file.id,name:attachment.filename || 'Document',mimeType:attachment.mime_type,
      parents:[config.folder],properties:{office_intake:'gmail_attachment'},appProperties:{gdi_attachment:identity}},
      Utilities.newBlob(bytes,attachment.mime_type,attachment.filename || 'Document'),{fields:'id',supportsAllDrives:true});
    meta=gdiGet_(file.id);
  }
  if (!meta || meta.trashed || !(meta.parents || []).includes(config.folder) ||
      (meta.appProperties || {}).gdi_attachment!==identity || Number(meta.size)!==attachment.size ||
      !file.md5 || meta.md5Checksum!==file.md5) throw new Error('attachment_conflict');
  file.uploaded=true;
  gdiSaveReceipt_(saved.id,receipt);
  return {attachment_id:attachment.attachment_id,drive_url:'https://drive.google.com/file/d/'+file.id+'/view'};
}
function gdiSubmit_(config,payload) {
  const body=JSON.stringify(payload);
  if (Utilities.newBlob(body).getBytes().length>64*1024) throw new Error('intake_payload_size');
  const ts=String(Math.floor(Date.now()/1000));
  const sig=Utilities.computeHmacSha256Signature(ts+'.'+body,config.secret)
    .map(function(b) {return ('0'+(b&255).toString(16)).slice(-2);}).join('');
  const response=UrlFetchApp.fetch(config.endpoint,{method:'post',contentType:'application/json',payload:body,
    headers:{'X-CSS-Timestamp':ts,'X-CSS-Signature':sig},followRedirects:false,muteHttpExceptions:true});
  const code=response.getResponseCode();
  if (code!==200 && code!==201) throw new Error('intake_http_'+code);
  const text=response.getContentText();
  if (text.length>4096) throw new Error('intake_reply_invalid');
  const result=JSON.parse(text);
  const queued=result.state==='queued' && Number.isSafeInteger(result.intake_id) && result.intake_id>0;
  const registered=Number.isSafeInteger(result.document_id) && result.document_id>0;
  if ((!queued && !registered) || typeof result.duplicate!=='boolean') throw new Error('intake_reply_invalid');
  return result;
}
// Read body only at import time; discovery and health logs remain metadata-only.
function gdiBodyText_(messageId) {
  const payload=Gmail.Users.Messages.get('me',messageId,{format:'full'}).payload;
  let visited=0;
  function decode(part) {
    const body=part.body || {};
    if(Number(body.size || 0)>128*1024)throw new Error('gmail_body_too_large');
    const data=body.attachmentId ? Gmail.Users.Messages.Attachments.get('me',messageId,body.attachmentId).data : body.data;
    if(typeof data!=='string' || data.length>180000)throw new Error('gmail_body_unavailable');
    return Utilities.newBlob(Utilities.base64DecodeWebSafe(data)).getDataAsString('UTF-8');
  }
  function walk(part,depth) {
    if(!part || ++visited>500 || depth>20)throw new Error('gmail_body_structure');
    if(part.filename || /^attachment\b/i.test(gdiHeader_(part,'content-disposition')) || part.mimeType==='message/rfc822')return '';
    if(part.mimeType==='text/plain')return decode(part);
    if(part.mimeType==='text/html') {
      return decode(part).replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>/gi,'')
        .replace(/<br\s*\/?\s*>|<\/(p|div|li|tr|h[1-6])\s*>/gi,'\n').replace(/<[^>]*>/g,'')
        .replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi,function(all,key){
          if(key[0]==='#') {const n=key[1].toLowerCase()==='x'?parseInt(key.slice(2),16):parseInt(key.slice(1),10);return n>0 && n<=0x10ffff?String.fromCodePoint(n):'\ufffd';}
          return {amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' '}[key.toLowerCase()];
        });
    }
    const parts=part.parts || [];
    if(part.mimeType==='multipart/alternative') {
      const plain=parts.find(function(p){return p.mimeType==='text/plain';});
      if(plain)return walk(plain,depth+1);
      const html=parts.find(function(p){return p.mimeType==='text/html';});
      if(html)return walk(html,depth+1);
    }
    return parts.map(function(p){return walk(p,depth+1);}).filter(Boolean).join('\n\n');
  }
  const text=walk(payload,0).replace(/\r\n?/g,'\n').trim();
  if(!text)throw new Error('gmail_body_empty');
  if(text.length>16000)throw new Error('gmail_body_too_large');
  return text;
}

function gdiImportOne_(config,candidate) {
  const saved=gdiReceipt_(config,candidate), receipt=saved.value;
  if (receipt.state==='queued') return 'already_queued';
  if (receipt.state==='registered') return 'already_registered';
  const pinned=receipt.candidate;
  if (!receipt.payload) {
    const attachments=pinned.attachments.map(function(item) {return gdiUpload_(config,saved,item);});
    receipt.payload={mailbox:receipt.mailbox,message_id:receipt.message_id,subject:pinned.subject,
      sender:pinned.sender,received_at:pinned.received_at,attachments:attachments};
    if(!attachments.length)receipt.payload.body_text=gdiBodyText_(receipt.message_id);
    gdiSaveReceipt_(saved.id,receipt); // pin exact request before HTTP
  }
  const result=gdiSubmit_(config,receipt.payload);
  receipt.document_id=result.document_id || null;
  receipt.intake_id=result.intake_id || null;
  receipt.state=result.state==='queued' ? 'queued' : 'registered';
  gdiSaveReceipt_(saved.id,receipt);
  return result.duplicate ? 'already_'+receipt.state : receipt.state;
}

// Run manually for acceptance, then optionally add a five-minute time trigger.
function importGmailDocuments() {
  const lock=LockService.getScriptLock();
  if (!lock.tryLock(1000)) return {state:'busy'};
  const props=PropertiesService.getScriptProperties();
  try {
    if(props.getProperty('GMAIL_DOCUMENTS_IMPORT_ENABLED')!=='true') {
      gdiHealth_({state:'paused',last_run_at:new Date().toISOString()});return {state:'paused'};
    }
    const started=Date.now();
    gdiHealth_({state:'running',last_run_at:new Date().toISOString()});
    const config=gdiImportConfig_();
    const recovery=gdiPendingPage_(config);
    const scanKey='GDI_SCAN_'+gdiHash_(JSON.stringify([config.binding,config.label,config.startMs,config.pageSize]));
    const token=props.getProperty(scanKey) || undefined;
    let page,discoveryFailed=false;
    try {page=gdiDiscoverPage_(config,token);}
    catch(err) {
      if(token)props.deleteProperty(scanKey);
      discoveryFailed=true;
      page={candidates:[],excluded:[],next_page_token:null,errors:[{reason:'gmail_discovery_failed'}]};
    }
    const report={state:'complete',registered:0,already_registered:0,queued:0,already_queued:0,needs_review:0,deferred:0,
      needs_attention:recovery.result.needs_attention,waiting_receipts:recovery.result.waiting,excluded:page.excluded.length,
      excluded_attachments:page.candidates.reduce(function(n,c) {return n+(c.excluded_attachments || []).length;},0),
      errors:recovery.result.errors.concat(page.errors)};
    const seen=new Set();let attempts=0,recoveryComplete=true;
    function process(candidate) {
      if(seen.has(candidate.message_id))return true;
      if(Date.now()-started>240000 || attempts>=5){report.state='partial';return false;}
      seen.add(candidate.message_id);
      if(!candidate.ready_for_import){report.needs_review++;return true;}
      attempts++;
      try {report[gdiAttempt_(config,candidate)]++;}
      catch(err){report.errors.push({message_id:candidate.message_id,reason:gdiErrorCode_(err)});}
      return true;
    }
    for(const candidate of recovery.result.candidates) {
      if(!process(candidate)){recoveryComplete=false;break;}
    }
    if(recoveryComplete)props.setProperty('GDI_RECOVERY_OFFSET',String(recovery.next));
    for(const candidate of page.candidates) {if(!process(candidate))break;}
    if(report.state==='complete' && !discoveryFailed) {
      if(page.next_page_token)props.setProperty(scanKey,page.next_page_token);
      else props.deleteProperty(scanKey);
    }
    const state=report.errors.length || report.needs_attention ? 'degraded' :
      report.deferred || report.waiting_receipts ? 'waiting_retry' : report.needs_review ? 'needs_review' : report.state;
    const health={state:state,last_error:'',last_finished_at:new Date().toISOString(),report:report};
    if(state==='complete')health.last_success_at=health.last_finished_at;
    gdiHealth_(health);
    console.log(JSON.stringify(report));
    return report;
  } catch(err) {
    const code=gdiErrorCode_(err);
    gdiHealth_({state:'failed',last_finished_at:new Date().toISOString(),last_error:code});
    throw new Error(code);
  } finally {lock.releaseLock();}
}
