// Office Connect Documents companion. Add this file to BOTH existing Apps Script
// projects (travel Docs and mail). No doPost is declared here. Drive API v3 and
// Gmail API v1 (mail project only) must be enabled. See DOCUMENT_MANAGEMENT_SETUP.
// No new account or endpoint is required. No automatic ACL changes are made.
const DM_MAX_BYTES = 20 * 1024 * 1024;
const DM_MAX_TEXT = 100000;

function dmError_(code) { const error = new Error(code); error.dmCode = code; throw error; }
function dmDigest_(bytes) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes)
    .map(function (b) { return ('0' + (b & 255).toString(16)).slice(-2); }).join('');
}
function dmHash_(value) { return dmDigest_(Utilities.newBlob(JSON.stringify(value)).getBytes()); }
function dmRequestHash_(req) {
  // Stable semantic identity; transient signature bytes must never be persisted.
  const clean = {};
  Object.keys(req).sort().forEach(function (key) {
    if (!['action', 'kind', 'signature_base64', 'signature_mime'].includes(key)) clean[key] = req[key];
  });
  return dmHash_(clean);
}
function dmRoot_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('DOCUMENTS_ROOT_FOLDER_ID');
  if (!id) dmError_('not_configured');
  return DriveApp.getFolderById(id);
}
function dmSubfolder_(root, name) {
  const found = root.getFoldersByName(name);
  return found.hasNext() ? found.next() : root.createFolder(name);
}
function dmReceiptFile_(folder, id) {
  const found = folder.getFilesByName('operation-' + id + '.json');
  return found.hasNext() ? found.next() : null;
}
function dmReadReceipt_(folder, id) {
  const file = dmReceiptFile_(folder, id);
  return file ? JSON.parse(file.getBlob().getDataAsString('UTF-8')) : null;
}
function dmSaveReceipt_(folder, receipt) {
  const name = 'operation-' + receipt.operation_id + '.json';
  const content = JSON.stringify(receipt);
  const file = dmReceiptFile_(folder, receipt.operation_id);
  if (file) file.setContent(content);
  else folder.createFile(name, content, 'application/json');
}
function dmMeta_(id) {
  if (!/^[A-Za-z0-9_-]{10,200}$/.test(String(id))) dmError_('bad_file');
  const meta = Drive.Files.get(id, {fields:'id,mimeType,size,version,trashed,name', supportsAllDrives:true});
  if (meta.trashed || !meta.version) dmError_('bad_file');
  if (Number(meta.size || 0) > DM_MAX_BYTES) dmError_('input_too_large');
  return meta;
}
function dmFingerprint_(meta) { return 'drive-v3:' + meta.id + ':' + String(meta.version); }
function dmExpect_(id, fingerprint) {
  const meta = dmMeta_(id);
  if (dmFingerprint_(meta) !== fingerprint) dmError_('version_changed');
  return meta;
}
function dmBlob_(meta) {
  const file = DriveApp.getFileById(meta.id);
  const native = meta.mimeType.indexOf('application/vnd.google-apps.') === 0;
  if (native && !['application/vnd.google-apps.document','application/vnd.google-apps.spreadsheet','application/vnd.google-apps.presentation'].includes(meta.mimeType)) dmError_('unsupported_format');
  const blob = native ? file.getAs('application/pdf') : file.getBlob();
  if (blob.getBytes().length > DM_MAX_BYTES) dmError_('input_too_large');
  return blob;
}
function dmInspect_(req) {
  const meta = dmMeta_(req.file_id);
  const blob = dmBlob_(meta);
  dmExpect_(req.file_id, dmFingerprint_(meta));
  return {ok:true, operation_id:req.operation_id, accessible:true, file_id:meta.id,
          fingerprint:dmFingerprint_(meta), size:blob.getBytes().length, mime:meta.mimeType,
          sha256:dmDigest_(blob.getBytes()),
          access_identity:'relay account only'};
}
function dmMarker_(id, opened) {
  const body = (opened || DocumentApp.openById(id)).getBody();
  const pattern = '\\{\\{OFFICE_CONNECT_SIGNATURE\\}\\}';
  const hit = body.findText(pattern);
  if (!hit || body.findText(pattern,hit)) dmError_('signature_marker');
  const para = hit.getElement().getParent();
  if (para.getType() !== DocumentApp.ElementType.PARAGRAPH || para.asParagraph().getText().trim() !== '{{OFFICE_CONNECT_SIGNATURE}}') dmError_('signature_marker');
  return para.asParagraph();
}
function dmPreview_(req) {
  const meta = dmExpect_(req.file_id, req.fingerprint);
  if (meta.mimeType !== 'application/vnd.google-apps.document') dmError_('unsupported_format');
  dmMarker_(req.file_id);
  dmExpect_(req.file_id, req.fingerprint);
  return {ok:true, operation_id:req.operation_id, state:'confirmed', fingerprint:req.fingerprint,
          url:DriveApp.getFileById(req.file_id).getUrl(), marker:'{{OFFICE_CONNECT_SIGNATURE}}', width:160, max_height:80};
}
function dmExtract_(req) {
  const intake=req.intake===true;
  const meta = intake ? dmIntakeOcrSource_(req) : dmMeta_(req.file_id), fingerprint = dmFingerprint_(meta);
  if (!intake && req.fingerprint && fingerprint!==req.fingerprint) dmError_('version_changed');
  let sourceBlob=null;
  if (intake) {
    if (!['application/pdf','image/png','image/jpeg','image/gif','text/plain'].includes(meta.mimeType)) dmError_('unsupported_format');
    sourceBlob=dmBlob_(meta);
    // Verify the actual bytes handed to OCR, in addition to metadata before/after.
    const checksum=Utilities.computeDigest(Utilities.DigestAlgorithm.MD5,sourceBlob.getBytes())
      .map(function(b){return ('0'+(b&255).toString(16)).slice(-2);}).join('');
    if (checksum!==req.content_key) dmError_('version_changed');
  }
  let text = '', temp = null;
  try {
    if (meta.mimeType === 'application/vnd.google-apps.document') {
      text = DocumentApp.openById(meta.id).getBody().getText();
    } else if (meta.mimeType === 'application/vnd.google-apps.spreadsheet') {
      let cells = 0;
      SpreadsheetApp.openById(meta.id).getSheets().forEach(function (sheet) {
        cells += sheet.getLastRow() * sheet.getLastColumn();
        if (cells > 20000) dmError_('input_too_large');
        text += sheet.getDataRange().getDisplayValues().map(function (r) {return r.join(' ');}).join('\n') + '\n';
      });
    } else if (meta.mimeType === 'text/plain') {
      text = (sourceBlob || dmBlob_(meta)).getDataAsString('UTF-8');
    } else if (['application/pdf','image/png','image/jpeg','image/gif'].includes(meta.mimeType)) {
      // Google Drive's import conversion performs OCR. No document text is sent
      // to another vendor. Imported OCR artifacts are permanently removed below.
      const converted = Drive.Files.create({name:'temporary-ocr-' + req.operation_id,
        mimeType:'application/vnd.google-apps.document',
        appProperties:{office_connect_transient:'ocr',operation_id:req.operation_id}},
        sourceBlob || dmBlob_(meta), {ocrLanguage:'en',fields:'id'});
      temp = converted.id;
      text = DocumentApp.openById(temp).getBody().getText();
    } else dmError_('unsupported_format');
    if (!text.trim()) dmError_('extraction_failed');
    if (text.length > DM_MAX_TEXT) dmError_('input_too_large');
    const current=intake ? dmIntakeOcrSource_(req) : dmExpect_(meta.id,fingerprint);
    if (intake && current.mimeType!==meta.mimeType) dmError_('version_changed');
    if (req.return_text===true) return {ok:true,operation_id:req.operation_id,state:'confirmed',
      file_id:current.id,fingerprint:dmFingerprint_(current),mime:current.mimeType,text:text};
    return Object.assign({ok:true, operation_id:req.operation_id, state:'confirmed'}, dmSuggest_(text),
      intake ? {file_id:current.id,content_key:current.md5Checksum,fingerprint:dmFingerprint_(current)} : {});
  } finally {
    // Failure to remove temporary content fails the operation visibly; do not
    // silently report successful transient processing if cleanup failed.
    if (temp) Drive.Files.remove(temp);
  }
}
function dmText_(req) {
  if (req.intake===true || !req.fingerprint) dmError_('bad_request');
  return dmExtract_(Object.assign({},req,{return_text:true}));
}
// Parse only labelled metadata. OCR can flatten table cells or split labels/values.
function dmSuggest_(text) {
  const lines=text.replace(/\u00a0/g,' ').split(/\r?\n/).map(function(s){return s.trim();}).filter(Boolean);
  const suggestions={}, warnings=['Suggestions are unverified. Compare with the source before confirming.'];
  const labels='type of document|document type|originating office|document date|date of document|due date|deadline|on or before|subject|sender|from|date|type|keywords|reference(?:s| no\\.?)?';
  const boundary=new RegExp('\\s+(?=(?:'+labels+')\\s*:)','ig');
  const parts=lines.join('\n').replace(boundary,'\n').split('\n');
  const anyLabel=new RegExp('^(?:'+labels+')\\s*[:\\-]','i');
  function values(label) {
    const prefix=new RegExp('^(?:'+label+')\\s*[:\\-]\\s*','i'), found=[];
    parts.forEach(function(line,i) {
      if (!prefix.test(line)) return;
      let value=line.replace(prefix,'').trim();
      // A value on the next line is common in OCR tables; never swallow another label/header.
      if (!value && parts[i+1] && !anyLabel.test(parts[i+1]) &&
          !/^(?:DATE|FROM|TO|DUE DATE|NAME|ACTION REQUIRED|ROUTING SLIP)$/i.test(parts[i+1])) value=parts[i+1];
      if (value) found.push(value.slice(0,1000));
    });
    return Array.from(new Set(found));
  }
  function field(key,label) {
    const found=values(label);
    if (found.length===1) suggestions[key]=found[0];
    else if(found.length>1) warnings.push('Multiple '+key.replace('_',' ')+' values found; choose the correct one from the source.');
  }
  field('subject','subject');
  field('sender','originating office|sender');
  if (!suggestions.sender && !values('originating office|sender').length) field('sender','from');
  field('type','type of document|document type|type');
  field('keywords','keywords');
  // Include wrapped subject/office text until the next label or routing-table heading.
  ['subject','sender'].forEach(function(key) {
    if (!suggestions[key]) return;
    const i=parts.findIndex(function(line){return line.endsWith(suggestions[key]);});
    if (i<0) return;
    for(let j=i+1;j<Math.min(parts.length,i+4);j++) {
      const next=parts[j];
      if(anyLabel.test(next) || /^(?:DATE|FROM|TO|NAME|DUE DATE|ACTION|ROUTING|MEMORANDUM|DEPARTMENT|REPUBLIC)\b/i.test(next) || (/^\d/.test(next) && !/^20\d{2}$/.test(next))) break;
      suggestions[key]+=' '+next;
    }
    suggestions[key]=suggestions[key].slice(0,500);
  });
  const refs=values('reference(?:s| no\\.?)?');
  if (/\bDTRAK\b/i.test(text)) {
    (text.match(/\b\d{4}-\d{7,12}\b/g)||[]).forEach(function(id){refs.push('DTRAK: '+id);});
  }
  if(refs.length) suggestions.references=Array.from(new Set(refs)).slice(0,8).join('\n').slice(0,1000);
  function dateField(key,candidates) {
    const dates=[], ambiguous=[];
    candidates.forEach(function(value) {
      const parsed=dmSuggestionDates_(value);
      dates.push.apply(dates,parsed.dates); if(parsed.ambiguous) ambiguous.push(value);
    });
    const unique=Array.from(new Set(dates));
    if(unique.length===1 && !ambiguous.length) suggestions[key]=unique[0];
    else if(candidates.length) warnings.push('Confirm '+key.replace('_',' ')+': the source has conflicting, ambiguous or unreadable dates.');
  }
  // The routing-slip document date belongs to the originating-office header.
  // Stop before the next metadata field/table; later page and routing dates are unrelated.
  const headerDates=[];
  let hasOfficeHeader=false;
  parts.forEach(function(line,i) {
    if(!/^originating office\s*(?::|$)/i.test(line)) return;
    hasOfficeHeader=true;
    let found=false;
    for(let j=i+1;j<Math.min(parts.length,i+9);j++) {
      const next=parts[j];
      const match=next.match(/^date\s*(?::\s*(.*)|$)/i);
      if(match) {
        let value=(match[1]||'').trim();
        if(!value && parts[j+1] && !anyLabel.test(parts[j+1]) &&
            !/^(?:FROM|TO|NAME|DUE DATE|ACTION|TYPE OF DOCUMENT|SUBJECT)\b/i.test(parts[j+1])) value=parts[j+1];
        headerDates.push(value);found=true;break;
      }
      if(anyLabel.test(next) || /^(?:DATE|FROM|TO|NAME|DUE DATE|ACTION|TYPE OF DOCUMENT|SUBJECT)\b/i.test(next)) break;
    }
    if(!found) headerDates.push('');
  });
  const explicit=values('document date|date of document');
  dateField('document_date',hasOfficeHeader?headerDates:(explicit.length?explicit:values('date')));
  const deadlines=values('due date|deadline|on or before');
  // Also accept a clearly stated deadline in prose, not a date somewhere in a routing table.
  parts.forEach(function(line){const m=line.match(/\b(?:on or before|deadline(?: is)?|due date(?: is)?)\s+(?!:)(.+)/i);if(m) deadlines.push(m[1]);});
  dateField('due_date',deadlines);
  if(!suggestions.due_date) warnings.push('No clear current deadline captured. Check the source; routing-history dates may refer to earlier actions.');
  warnings.push('Confirm Incoming or Outgoing and the actual office receipt time manually.');
  return {suggestions:suggestions,excerpts:lines.slice(0,10).map(function(s){return s.slice(0,1000);}),warnings:warnings};
}
function dmSuggestionDates_(value) {
  const dates=[];let ambiguous=false;
  function add(year,month,day) {
    const iso=String(year)+'-'+String(month).padStart(2,'0')+'-'+String(day).padStart(2,'0');
    const parsed=new Date(iso+'T00:00:00Z');
    if(!isNaN(parsed.getTime()) && parsed.toISOString().slice(0,10)===iso) dates.push(iso);
    else ambiguous=true;
  }
  (value.match(/\b\d{4}-\d{2}-\d{2}\b/g)||[]).forEach(function(v){const p=v.split('-');add(+p[0],+p[1],+p[2]);});
  (value.match(/\b\d{1,2}\/\d{1,2}\/\d{4}\b/g)||[]).forEach(function(v){
    const p=v.split('/').map(Number);
    if(p[0]<=12 && p[1]>12) add(p[2],p[0],p[1]);
    else if(p[0]>12 && p[1]<=12) add(p[2],p[1],p[0]);
    else if(p[0]===p[1]) add(p[2],p[0],p[1]);
    else ambiguous=true;
  });
  const months='jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?';
  const names=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'];
  const patterns=[new RegExp('\\b('+months+')\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?[,]?\\s+(\\d{4})\\b','ig'),new RegExp('\\b(\\d{1,2})\\s+('+months+')\\.?[,]?\\s+(\\d{4})\\b','ig')];
  patterns.forEach(function(re,index){let m;while((m=re.exec(value))!==null){add(+m[3],names.indexOf(m[index?2:1].slice(0,3).toLowerCase())+1,+m[index?1:2]);}});
  if(!dates.length) ambiguous=true;
  return {dates:dates,ambiguous:ambiguous};
}

function dmSign_(req, folder, receipt) {
  if (req.actor_id !== req.signatory_id || !Number.isInteger(req.actor_id) || !req.signature_base64) dmError_('unauthorized');
  if (!['image/png','image/jpeg'].includes(req.signature_mime) || req.signature_base64.length > 700000) dmError_('bad_signature');
  const bytes = Utilities.base64Decode(req.signature_base64);
  if (bytes.length > 512*1024 || dmDigest_(bytes) !== req.signature_hash) dmError_('bad_signature');
  const meta = dmExpect_(req.file_id, req.fingerprint);
  if (meta.mimeType !== 'application/vnd.google-apps.document') dmError_('unsupported_format');
  dmMarker_(req.file_id);
  dmBlob_(meta);
  dmExpect_(req.file_id,req.fingerprint);
  let copy = null;
  try {
    const output = dmSubfolder_(dmRoot_(),'signed_documents');
    copy = DriveApp.getFileById(req.file_id).makeCopy('Signing ' + req.operation_id, output);
    receipt.working_file_id = copy.getId(); dmSaveReceipt_(folder,receipt);
    // Once copied, work on a pinned snapshot. Edits to the source before the
    // snapshot completes invalidate it; later edits cannot change that snapshot.
    dmExpect_(req.file_id,req.fingerprint);
    const doc = DocumentApp.openById(copy.getId());
    const para = dmMarker_(copy.getId(),doc);
    const image = para.clear().appendInlineImage(Utilities.newBlob(bytes,req.signature_mime));
    const scale = Math.min(160/image.getWidth(),80/image.getHeight());
    image.setWidth(Math.max(1,Math.round(image.getWidth()*scale))).setHeight(Math.max(1,Math.round(image.getHeight()*scale)));
    doc.saveAndClose();
    const blob = copy.getAs('application/pdf').setName('Signed-' + req.operation_id + '.pdf');
    const signed = output.createFile(blob);
    receipt.output_file_id = signed.getId(); dmSaveReceipt_(folder,receipt);
    const result = {ok:true, operation_id:req.operation_id, state:'confirmed',
      source_fingerprint:req.fingerprint, signatory_id:req.signatory_id, url:signed.getUrl(),
      fingerprint:dmFingerprint_(dmMeta_(signed.getId())), evidence:'Stored profile signature applied; signed PDF '+signed.getId()};
    return result;
  } finally {
    // Original is untouched. The signed PDF and operation evidence remain.
    if (copy) Drive.Files.remove(copy.getId());
  }
}
function dmSender_(sender) {
  const own = Session.getEffectiveUser().getEmail().toLowerCase();
  const aliases = GmailApp.getAliases().map(function (s) {return s.toLowerCase();});
  sender = String(sender || '').toLowerCase();
  if (!sender || (sender !== own && !aliases.includes(sender))) dmError_('sender_mismatch');
  return sender;
}
function dmBase64Lines_(bytes) {
  return (Utilities.base64Encode(bytes).match(/.{1,76}/g) || []).join('\r\n');
}
function dmMime_(req, recipient, blob, messageId) {
  // Header inputs never contain CR/LF. Each message has exactly one recipient.
  if (!/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(recipient) || /[\r\n]/.test(req.sender)) dmError_('bad_recipient');
  const chars = Array.from(String(req.subject || 'Official correspondence').slice(0,500));
  const words = [];
  for (let i=0;i<chars.length;i+=10) {
    words.push('=?UTF-8?B?'+Utilities.base64Encode(Utilities.newBlob(chars.slice(i,i+10).join('')).getBytes())+'?=');
  }
  const subject = words.join('\r\n ');
  const boundary = 'oc_' + req.operation_id.replace(/-/g,'');
  const body = dmBase64Lines_(Utilities.newBlob(String(req.message || 'Please see the attached official correspondence.')).getBytes());
  const mime = ['From: '+req.sender, 'To: '+recipient, 'Subject: '+subject,
    'Message-ID: <'+messageId+'>', 'MIME-Version: 1.0', 'Content-Type: multipart/mixed; boundary="'+boundary+'"','',
    '--'+boundary,'Content-Type: text/plain; charset=UTF-8','Content-Transfer-Encoding: base64','',body,
    '--'+boundary,'Content-Type: '+blob.getContentType(), 'Content-Disposition: attachment; filename="official-document'+(blob.getContentType()==='application/pdf'?'.pdf':'')+'"',
    'Content-Transfer-Encoding: base64','',dmBase64Lines_(blob.getBytes()),'--'+boundary+'--',''].join('\r\n');
  return Utilities.base64EncodeWebSafe(Utilities.newBlob(mime).getBytes()).replace(/=+$/,'');
}
function dmDispatch_(req,folder,receipt) {
  dmSender_(req.sender);
  if (!Array.isArray(req.recipients) || !req.recipients.length || req.recipients.length>100 || new Set(req.recipients).size!==req.recipients.length) dmError_('bad_recipient');
  const meta = dmExpect_(req.file_id,req.fingerprint);
  const blob = dmBlob_(meta);
  dmExpect_(req.file_id,req.fingerprint); // attachment bytes are now pinned
  receipt.recipients = {};
  req.recipients.forEach(function (recipient,index) {
    // Prepare every MIME before the first irreversible send.
    const messageId = 'officeconnect.'+req.operation_id+'.'+index+'@'+req.sender.split('@')[1];
    dmMime_(req,recipient,blob,messageId);
    receipt.recipients[recipient] = {outcome:'pending',message_id:messageId};
  });
  dmSaveReceipt_(folder,receipt);
  req.recipients.forEach(function (recipient) {
    const item = receipt.recipients[recipient];
    item.outcome = 'unknown'; dmSaveReceipt_(folder,receipt); // write BEFORE send
    try {
      const sent = Gmail.Users.Messages.send({raw:dmMime_(req,recipient,blob,item.message_id)},'me');
      if (!sent.id) dmError_('unconfirmed');
      item.outcome='accepted'; item.evidence='Gmail message '+sent.id; item.gmail_id=sent.id;
    } catch (err) {
      // Even an exception may follow acceptance. Stop; do not blindly send the
      // rest or classify a timeout as a confirmed failure.
      dmSaveReceipt_(folder,receipt); throw err;
    }
    dmSaveReceipt_(folder,receipt);
  });
  return dmDispatchResult_(receipt);
}
function dmDispatchResult_(receipt) {
  const outcomes = {};
  Object.keys(receipt.recipients || {}).forEach(function (recipient) {
    const item = receipt.recipients[recipient];
    outcomes[recipient] = {outcome:item.outcome,evidence:item.evidence || ''};
  });
  return {ok:true,operation_id:receipt.operation_id,state:'confirmed',fingerprint:receipt.fingerprint,
    sender:receipt.sender,recipients:outcomes,evidence:'Durable Gmail API send receipts; not recipient acknowledgment'};
}
function dmStatus_(req,folder,receipt) {
  if (!receipt) dmError_('not_found');
  if (receipt.actor_id !== req.actor_id || receipt.kind !== req.kind) dmError_('operation_conflict');
  if (receipt.state === 'confirmed') return receipt.result;
  if (receipt.kind === 'dispatch' && receipt.recipients) {
    Object.keys(receipt.recipients).forEach(function (recipient) {
      const item=receipt.recipients[recipient];
      if (item.outcome === 'pending') {
        item.outcome='failed'; item.evidence='Not attempted: prior recipient outcome interrupted operation';
      } else if (item.outcome === 'unknown') {
        // Read-only reconciliation. An absent search hit is NOT proof of no send.
        const matches=Gmail.Users.Messages.list('me',{q:'in:sent rfc822msgid:'+item.message_id,maxResults:2});
        if (matches.messages && matches.messages.length===1) {
          const message=Gmail.Users.Messages.get('me',matches.messages[0].id,{format:'metadata',metadataHeaders:['To','From','Message-ID']});
          const headers={}; (message.payload.headers || []).forEach(function (h) {headers[h.name.toLowerCase()]=h.value;});
          if (headers['message-id']==='<'+item.message_id+'>' && headers.to===recipient && headers.from===receipt.sender) {
            item.outcome='accepted';item.evidence='Reconciled Gmail message '+message.id;item.gmail_id=message.id;
          }
        }
      }
    });
    if (Object.keys(receipt.recipients).every(function (r) {return ['accepted','failed'].includes(receipt.recipients[r].outcome);})) {
      receipt.result=dmDispatchResult_(receipt);receipt.state='confirmed';
    }
    dmSaveReceipt_(folder,receipt);
  }
  return receipt.state==='confirmed' ? receipt.result : {ok:true,operation_id:req.operation_id,state:'unknown'};
}
function documentOperation_(req,allowed) {
  try {
    const kind=String(req.action || '').replace(/^document_/,'');
    if (!allowed.includes(kind) || !/^[a-f0-9-]{36}$/.test(String(req.operation_id)) || !Number.isInteger(req.actor_id) || req.actor_id<1) dmError_('bad_request');
    if (kind==='intake_list') return dmIntakeList_(req);
    if (kind==='intake_check') return dmIntakeCheck_(req);
    if (kind==='intake_file') return dmIntakeFile_(req);
    if (kind==='inspect') return dmInspect_(req);
    if (kind==='preview') return dmPreview_(req);
    if (kind==='extract') return dmExtract_(req);
    if (kind==='text') return dmText_(req);
    const lock=LockService.getScriptLock();
    if (!lock.tryLock(1000)) dmError_('busy');
    try {
      const folder=dmSubfolder_(dmRoot_(),'document_operation_receipts');
      let receipt=dmReadReceipt_(folder,req.operation_id);
      if (kind==='status') {
        if (!['sign','dispatch'].includes(req.kind) || !allowed.includes(req.kind)) dmError_('unauthorized');
        return dmStatus_(req,folder,receipt);
      }
      const hash=dmRequestHash_(req);
      if (receipt) {
        if (receipt.request_hash!==hash) dmError_('operation_conflict');
        return receipt.state==='confirmed' ? receipt.result : {ok:true,operation_id:req.operation_id,state:'unknown'};
      }
      receipt={operation_id:req.operation_id,kind:kind,actor_id:req.actor_id,request_hash:hash,state:'running',
        fingerprint:req.fingerprint,sender:req.sender || '',created_at:new Date().toISOString()};
      dmSaveReceipt_(folder,receipt);
      receipt.result=kind==='sign' ? dmSign_(req,folder,receipt) : dmDispatch_(req,folder,receipt);
      receipt.state='confirmed';dmSaveReceipt_(folder,receipt);
      return receipt.result;
    } finally {lock.releaseLock();}
  } catch (err) {
    // No source text, signature, tokens or arbitrary provider response in errors.
    return {ok:false,operation_id:req.operation_id,error:err.dmCode || 'unconfirmed'};
  }
}

// Recovery after an Apps Script termination or ambiguous Drive import response.
// Configure an hourly time-driven trigger in the travel Docs project. It removes
// only this module's tagged OCR imports older than one hour, never source files.
function cleanupDocumentOcrTemps() {
  const cutoff=new Date(Date.now()-60*60*1000).toISOString();
  let token;
  do {
    const page=Drive.Files.list({q:"trashed = false and appProperties has { key='office_connect_transient' and value='ocr' } and createdTime < '"+cutoff+"'",
      fields:'files(id),nextPageToken',pageSize:100,pageToken:token});
    (page.files || []).forEach(function (file) {Drive.Files.remove(file.id);});
    token=page.nextPageToken;
  } while (token);
}

// Office Drive intake (My Drive folders or an actual Shared Drive). These operations never send mail or copy source files.
function dmIntakeRoots_(req, filing) {
  const props=PropertiesService.getScriptProperties();
  const inbox=props.getProperty('DOCUMENTS_INTAKE_FOLDER_ID');
  const filed=props.getProperty('DOCUMENTS_FILED_FOLDER_ID');
  if (!inbox || req.inbox!==inbox || (filing && (!filed || req.filed!==filed || filed===inbox))) dmError_('not_configured');
  const source=Drive.Files.get(inbox,{fields:'id,mimeType,driveId,trashed',supportsAllDrives:true});
  if (source.trashed || source.mimeType!=='application/vnd.google-apps.folder') dmError_('bad_folder');
  if (filing) {
    const destination=Drive.Files.get(filed,{fields:'id,mimeType,driveId,trashed',supportsAllDrives:true});
    if (destination.trashed || destination.mimeType!=='application/vnd.google-apps.folder' || (destination.driveId || null)!==(source.driveId || null)) dmError_('bad_folder');
  }
  return {inbox:inbox,filed:filed,driveId:source.driveId};
}
function dmIntakeMeta_(id) {
  if (!/^[A-Za-z0-9_-]{10,200}$/.test(String(id))) dmError_('bad_file');
  const m=Drive.Files.get(id,{fields:'id,name,mimeType,size,version,md5Checksum,parents,appProperties,trashed',supportsAllDrives:true});
  if (m.trashed) dmError_('bad_file');
  return m;
}
function dmIntakeOcrSource_(req) {
  const roots=dmIntakeRoots_(req,false);
  if (typeof req.content_key!=='string' || !/^[a-f0-9]{32}$/.test(req.content_key)) dmError_('bad_request');
  const meta=dmIntakeMeta_(req.file_id);
  if (!(meta.parents || []).includes(roots.inbox) || meta.md5Checksum!==req.content_key) dmError_('version_changed');
  return meta;
}
function dmIntakeList_(req) {
  const roots=dmIntakeRoots_(req,false);
  const options={q:"'"+roots.inbox+"' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder' and not properties has { key='office_intake' and value='gmail_receipt' }",
    corpora:roots.driveId?'drive':'user',includeItemsFromAllDrives:true,supportsAllDrives:true,
    pageSize:100,orderBy:'createdTime',fields:'nextPageToken,files(id,name,mimeType,size,version,md5Checksum,appProperties,properties)'};
  if (roots.driveId) options.driveId=roots.driveId;
  if (req.cursor) options.pageToken=String(req.cursor);
  const result=Drive.Files.list(options);
  return {ok:true,operation_id:req.operation_id,inbox:roots.inbox,next_cursor:result.nextPageToken || '',
    files:(result.files || []).map(function(m) {return {id:m.id,name:m.name,mime_type:m.mimeType,
      email_attachment:!!(m.appProperties || {}).gdi_attachment || (m.properties || {}).office_intake==='gmail_attachment',email_receipt:!!(m.appProperties || {}).gdi_receipt || (m.properties || {}).office_intake==='gmail_receipt',
      size:Number(m.size || 0),fingerprint:dmFingerprint_(m),content_key:m.md5Checksum || dmFingerprint_(m)};})};
}
function dmIntakeCheck_(req) {
  const roots=dmIntakeRoots_(req,false), m=dmIntakeMeta_(req.file_id);
  if (!(m.parents || []).includes(roots.inbox) || dmFingerprint_(m)!==req.fingerprint) dmError_('version_changed');
  if (!m.md5Checksum || Number(m.size || 0)>DM_MAX_BYTES) dmError_('unsupported_format');
  return {ok:true,operation_id:req.operation_id,state:'confirmed',fingerprint:dmFingerprint_(m)};
}
function dmIntakeFolder_(parent,name,driveId) {
  const options={q:"'"+parent+"' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder' and name = '"+name+"'",
    corpora:driveId?'drive':'user',includeItemsFromAllDrives:true,supportsAllDrives:true,pageSize:2,fields:'files(id)'};
  if (driveId) options.driveId=driveId;
  const result=Drive.Files.list(options);
  if ((result.files || []).length>1) dmError_('duplicate_folder');
  return result.files && result.files.length ? result.files[0].id :
    Drive.Files.create({name:name,mimeType:'application/vnd.google-apps.folder',parents:[parent]},null,{fields:'id',supportsAllDrives:true}).id;
}
function dmIntakeFile_(req) {
  const roots=dmIntakeRoots_(req,true);
  if (!/^[0-9]{4}$/.test(String(req.year)) || !['IN','OUT'].includes(req.direction) ||
      !new RegExp('^BLHSD-'+req.direction+'-'+req.year+'-[0-9]{6,}$').test(String(req.number)) ||
      !Number.isInteger(req.ordinal) || req.ordinal<1 || req.ordinal>20) dmError_('bad_request');
  const lock=LockService.getScriptLock();
  if (!lock.tryLock(1000)) dmError_('busy');
  try {
    let m=dmIntakeMeta_(req.file_id);
    const props=m.appProperties || {}, hash=dmRequestHash_(req);
    if (props.oc_intake_op) {
      if (props.oc_intake_op!==req.operation_id || props.oc_intake_hash!==hash || props.oc_intake_content!==m.md5Checksum) dmError_('operation_conflict');
      if (!(m.parents || []).includes(props.oc_intake_folder)) dmError_('operation_conflict');
    } else {
      if (!(m.parents || []).includes(roots.inbox) || dmFingerprint_(m)!==req.fingerprint) dmError_('version_changed');
      if (!m.md5Checksum || Number(m.size || 0)>DM_MAX_BYTES) dmError_('unsupported_format');
      const year=dmIntakeFolder_(roots.filed,String(req.year),roots.driveId);
      const folder=dmIntakeFolder_(year,req.direction==='IN'?'Incoming':'Outgoing',roots.driveId);
      const extensions={'application/pdf':'.pdf','image/png':'.png','image/jpeg':'.jpg','image/gif':'.gif','text/plain':'.txt',
        'application/msword':'.doc','application/vnd.ms-excel':'.xls','application/vnd.ms-powerpoint':'.ppt',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document':'.docx',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'.xlsx',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation':'.pptx'};
      if (!extensions[m.mimeType]) dmError_('unsupported_format');
      const name=req.number+' - '+(req.ordinal===1?'Original Scan':'Attachment '+req.ordinal)+extensions[m.mimeType];
      // Rename, move and receipt marker are one Drive metadata update. A repeated
      // call reconciles that marker instead of creating another file or folder.
      Drive.Files.update({name:name,appProperties:Object.assign({},props,{oc_intake_op:req.operation_id,
        oc_intake_hash:hash,oc_intake_content:m.md5Checksum,oc_intake_folder:folder})},m.id,null,
        {addParents:folder,removeParents:roots.inbox,supportsAllDrives:true,fields:'id'});
      m=dmIntakeMeta_(m.id);
      if (m.appProperties.oc_intake_hash!==hash || m.appProperties.oc_intake_content!==m.md5Checksum ||
          !(m.parents || []).includes(folder)) dmError_('operation_conflict');
    }
    return {ok:true,operation_id:req.operation_id,state:'confirmed',file_id:m.id,fingerprint:dmFingerprint_(m)};
  } finally {lock.releaseLock();}
}
