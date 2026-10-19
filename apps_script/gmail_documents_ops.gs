// Phase 5 operations. Add beside discovery/import scripts in the SAME project.
// Only bounded error codes/IDs enter health reports. Receipt metadata stays in Drive.
function gdiErrorCode_(err) {
  const code=String(err && err.message || '');
  return /^(intake_http_\d{3}|intake_reply_invalid|intake_payload_size|attachment_conflict|attachment_size|imported_file_missing|receipt_binding_conflict|receipt_location_conflict|drive_read_unconfirmed|gmail_[a-z_]+)$/.test(code) ? code : 'import_incomplete';
}
function gdiHistory_(receipt,action,code) {
  receipt.history=(receipt.history || []).concat([{at:new Date().toISOString(),action:action,code:code || ''}]).slice(-30);
}
function gdiHealth_(patch) {
  const props=PropertiesService.getScriptProperties();
  const previous=JSON.parse(props.getProperty('GDI_HEALTH') || '{}');
  const next=Object.assign(previous,patch);
  props.setProperty('GDI_HEALTH',JSON.stringify(next));
  if(patch.last_finished_at) {
    const runs=JSON.parse(props.getProperty('GDI_RUNS') || '[]');
    props.setProperty('GDI_RUNS',JSON.stringify(runs.concat([{at:patch.last_finished_at,state:patch.state,
      error:patch.last_error || '',queued:patch.report ? patch.report.queued || 0 : 0,registered:patch.report ? patch.report.registered : 0,
      errors:patch.report ? patch.report.errors.length : 0}]).slice(-20)));
  }
  return next;
}
function gdiAttempt_(config,candidate) {
  let saved;
  try {
    saved=gdiReceipt_(config,candidate);
    const r=saved.value;
    if(r.state==='queued')return 'already_queued';
    if(r.state==='registered')return 'already_registered';
    if(r.state==='needs_attention')return 'needs_attention';
    if(r.next_attempt_at && Date.parse(r.next_attempt_at)>Date.now())return 'deferred';
    // A terminated invocation leaves the attempt and retry time recorded.
    r.attempts=(r.attempts || 0)+1;
    r.last_attempt_at=new Date().toISOString();
    r.next_attempt_at=new Date(Date.now()+Math.min(3600000,60000*Math.pow(2,Math.min(r.attempts-1,6)))).toISOString();
    if(r.attempts>8){r.state='needs_attention';gdiHistory_(r,'blocked','retry_limit');gdiSaveReceipt_(saved.id,r);return 'needs_attention';}
    gdiHistory_(r,'attempt','');gdiSaveReceipt_(saved.id,r);
    const result=gdiImportOne_(config,candidate);
    // Reload the registered receipt, never overwrite a successful checkpoint
    // with the pre-upload copy retained above.
    saved=gdiReceipt_(config,candidate);
    saved.value.last_error='';saved.value.next_attempt_at=null;
    gdiHistory_(saved.value,saved.value.state,'');gdiSaveReceipt_(saved.id,saved.value);
    return result;
  } catch(err) {
    const code=gdiErrorCode_(err);
    if(saved) {
      try {
        const current=gdiReceipt_(config,candidate);
        if(!['registered','queued'].includes(current.value.state)) {
          const blocked=/^intake_http_(400|401|403|404|409|413)$/.test(code) ||
            ['attachment_conflict','attachment_size','imported_file_missing','receipt_binding_conflict','receipt_location_conflict'].includes(code);
          current.value.state=blocked || current.value.attempts>=8 ? 'needs_attention' : 'pending';
          current.value.last_error=code;
          gdiHistory_(current.value,'failed',code);gdiSaveReceipt_(current.id,current.value);
        }
      } catch(ignore) { /* Do not mask the original failure; the reserved index remains. */ }
    }
    throw new Error(code);
  }
}
function gdiPendingPage_(config) {
  const props=PropertiesService.getScriptProperties(), all=props.getProperties();
  const keys=Object.keys(all).filter(function(k){return k.indexOf('GDI_RECEIPT_')===0;}).sort();
  const offset=Number(props.getProperty('GDI_RECOVERY_OFFSET') || 0);
  const start=Number.isSafeInteger(offset) && offset>=0 && offset<keys.length ? offset : 0;
  const selected=keys.slice(start,start+20), result={candidates:[],errors:[],needs_attention:0,waiting:0,examined:selected.length};
  selected.forEach(function(key){
    try {
      const meta=gdiGet_(all[key]);
      if(!meta || meta.trashed)throw new Error('receipt_location_conflict');
      if(!(meta.parents || []).includes(config.folder) || (meta.appProperties || {}).gdi_receipt!==key)throw new Error('receipt_location_conflict');
      const r=JSON.parse(DriveApp.getFileById(all[key]).getBlob().getDataAsString('UTF-8'));
      if(r.binding!==config.binding)throw new Error('receipt_binding_conflict');
      if(r.state==='needs_attention')result.needs_attention++;
      if(r.state==='pending' && r.next_attempt_at && Date.parse(r.next_attempt_at)>Date.now())result.waiting++;
      if(r.state==='pending' && r.candidate && (!r.next_attempt_at || Date.parse(r.next_attempt_at)<=Date.now()))result.candidates.push(r.candidate);
    } catch(err){result.errors.push({receipt_id:all[key],reason:gdiErrorCode_(err)});}
  });
  return {result:result,next:start+selected.length>=keys.length ? 0 : start+selected.length};
}

// Read-only operational report, including a page of receipts. No source content.
function gmailDocumentsStatus(offset) {
  const props=PropertiesService.getScriptProperties(), all=props.getProperties();
  const keys=Object.keys(all).filter(function(k){return k.indexOf('GDI_RECEIPT_')===0;}).sort();
  offset=offset===undefined ? 0 : offset;
  if(!Number.isSafeInteger(offset) || offset<0)throw new Error('invalid_status_offset');
  const report={paused:props.getProperty('GMAIL_DOCUMENTS_IMPORT_ENABLED')!=='true',
    health:JSON.parse(props.getProperty('GDI_HEALTH') || '{}'),
    controls:JSON.parse(props.getProperty('GDI_CONTROLS') || '[]'),runs:JSON.parse(props.getProperty('GDI_RUNS') || '[]'),indexed_receipts:keys.length,
    property_bytes:Utilities.newBlob(JSON.stringify(all)).getBytes().length,
    receipts:[],next_offset:offset+20<keys.length ? offset+20 : null};
  report.property_capacity_warning=report.property_bytes>400*1024;
  report.stale=!report.paused && (!report.health.last_run_at || Date.now()-Date.parse(report.health.last_run_at)>15*60*1000);
  keys.slice(offset,offset+20).forEach(function(key){
    const id=all[key];
    try {
      const r=JSON.parse(DriveApp.getFileById(id).getBlob().getDataAsString('UTF-8'));
      report.receipts.push({receipt_id:id,message_id:r.message_id,state:r.state,attempts:r.attempts || 0,
        last_attempt_at:r.last_attempt_at || null,next_attempt_at:r.next_attempt_at || null,
        last_error:r.last_error || '',document_id:r.document_id,intake_id:r.intake_id || null,history:r.history || []});
    }catch(err){report.receipts.push({receipt_id:id,state:'unreadable',last_error:'receipt_unavailable'});}
  });
  console.log(JSON.stringify(report,null,2));return report;
}
function pauseGmailDocuments() {
  return gdiControl_('pause');
}
function resumeGmailDocuments() {
  return gdiControl_('resume');
}
function gdiControl_(action) {
  const lock=LockService.getScriptLock();
  if(!lock.tryLock(1000))throw new Error('gmail_import_busy');
  try {
    const props=PropertiesService.getScriptProperties();
    const reason=String(props.getProperty('GMAIL_DOCUMENTS_OPERATOR_REASON') || '').trim();
    if(!reason || reason.length>500)throw new Error('operator_reason_required');
    if(action==='resume') {
      // Validate without leaving the switch enabled if validation fails.
      const old=props.getProperty('GMAIL_DOCUMENTS_IMPORT_ENABLED') || 'false';
      props.setProperty('GMAIL_DOCUMENTS_IMPORT_ENABLED','true');
      try {gdiImportConfig_();}catch(err){props.setProperty('GMAIL_DOCUMENTS_IMPORT_ENABLED',old);throw err;}
    }else props.setProperty('GMAIL_DOCUMENTS_IMPORT_ENABLED','false');
    const previous=JSON.parse(props.getProperty('GDI_CONTROLS') || '[]');
    props.setProperty('GDI_CONTROLS',JSON.stringify(previous.concat([{at:new Date().toISOString(),action:action,reason:reason,actor:Session.getEffectiveUser().getEmail()}]).slice(-10)));
    gdiHealth_({state:action==='pause'?'paused':'ready',control_at:new Date().toISOString()});
    props.deleteProperty('GMAIL_DOCUMENTS_OPERATOR_REASON');
    return {state:action==='pause'?'paused':'ready'};
  } finally {lock.releaseLock();}
}

// Editor-run repair action: configure receipt ID + reason, then run. It schedules
// a retry; it never changes pinned source IDs/payloads or performs an upload here.
function retryGmailDocument() {
  const lock=LockService.getScriptLock();
  if(!lock.tryLock(1000))throw new Error('gmail_import_busy');
  try {
    const props=PropertiesService.getScriptProperties();
    const id=String(props.getProperty('GMAIL_DOCUMENTS_RETRY_RECEIPT_ID') || '');
    const reason=String(props.getProperty('GMAIL_DOCUMENTS_OPERATOR_REASON') || '').trim();
    if(!reason || reason.length>500)throw new Error('operator_reason_required');
    const all=props.getProperties();
    const key=Object.keys(all).find(function(k){return k.indexOf('GDI_RECEIPT_')===0 && all[k]===id;});
    if(!key)throw new Error('unknown_receipt');
    const meta=gdiGet_(id);
    if(!meta || meta.trashed || (meta.appProperties || {}).gdi_receipt!==key)throw new Error('receipt_location_conflict');
    const r=JSON.parse(DriveApp.getFileById(id).getBlob().getDataAsString('UTF-8'));
    if(r.state==='queued')throw new Error('already_queued');
    if(r.state==='registered')throw new Error('already_registered');
    r.state='pending';r.attempts=0;r.next_attempt_at=null;r.last_error='';
    gdiHistory_(r,'operator_retry','');r.history[r.history.length-1].reason=reason;r.history[r.history.length-1].actor=Session.getEffectiveUser().getEmail();
    gdiSaveReceipt_(id,r);
    // Start recovery at the selected receipt so retry does not wait for a full cycle.
    const keys=Object.keys(all).filter(function(k){return k.indexOf('GDI_RECEIPT_')===0;}).sort();
    props.setProperty('GDI_RECOVERY_OFFSET',String(keys.indexOf(key)));
    props.deleteProperty('GMAIL_DOCUMENTS_OPERATOR_REASON');props.deleteProperty('GMAIL_DOCUMENTS_RETRY_RECEIPT_ID');
    return {state:'pending',receipt_id:id};
  } finally {lock.releaseLock();}
}
