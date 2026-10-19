// Phase 2: read-only Gmail candidate discovery. Add to the existing mail project.
// Requires Gmail API v1. No doPost, Drive writes, mail mutations, or intake calls.
const GDI_MIMES = [
  'application/pdf', 'text/plain', 'image/png', 'image/jpeg', 'image/gif',
  'application/msword', 'application/vnd.ms-excel', 'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation'
];
const GDI_MAX_BYTES = 20 * 1024 * 1024;

function gdiConfig_() {
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty('GMAIL_DOCUMENTS_PREVIEW_ENABLED') !== 'true') throw new Error('gmail_preview_disabled');
  const mailbox = String(props.getProperty('GMAIL_DOCUMENTS_MAILBOX') || '').trim().toLowerCase();
  const label = String(props.getProperty('GMAIL_DOCUMENTS_LABEL') || '').trim();
  const start = String(props.getProperty('GMAIL_DOCUMENTS_START_AT') || '');
  // A deliberate instant prevents an implicit historical mailbox backfill.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(mailbox) || !label || label.length > 225 || /[\r\n]/.test(label)) throw new Error('gmail_preview_config');
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$/.test(start) || !Number.isFinite(Date.parse(start))) throw new Error('gmail_preview_start');
  const calendar = new Date(start.slice(0,10) + 'T00:00:00Z');
  if (calendar.toISOString().slice(0,10) !== start.slice(0,10)) throw new Error('gmail_preview_start');
  const pageSize = props.getProperty('GMAIL_DOCUMENTS_PAGE_SIZE') || '25';
  if (!/^\d+$/.test(pageSize) || Number(pageSize)<1 || Number(pageSize)>100) throw new Error('gmail_preview_page_size');
  return {mailbox:mailbox,label:label,startMs:Date.parse(start),pageSize:Number(pageSize)};
}

function gdiHeader_(part, name) {
  const found = (part.headers || []).find(function(h) {return String(h.name).toLowerCase()===name;});
  return found ? String(found.value || '') : '';
}

function gdiAttachments_(payload) {
  const accepted = [], excluded = [];
  let visited = 0;
  function walk(part, depth) {
    if (++visited>500 || depth>20) throw new Error('mime_structure_limit');
    const mime = String(part.mimeType || '').toLowerCase();
    if (mime === 'message/rfc822') {excluded.push({reason:'attached_email_unsupported'}); return;}
    const name = String(part.filename || '');
    const disposition = gdiHeader_(part,'content-disposition');
    const inline = /^inline\b/i.test(disposition) || (gdiHeader_(part,'content-id') && !/^attachment\b/i.test(disposition));
    if (name || /^attachment\b/i.test(disposition)) {
      let reason = '';
      const body = part.body || {};
      if (inline) reason='inline_attachment';
      else if (!GDI_MIMES.includes(mime)) reason='unsupported_type';
      else if (!Number.isSafeInteger(body.size) || body.size<=0 || body.size>GDI_MAX_BYTES) reason='attachment_size';
      else if (!body.attachmentId || !/^[A-Za-z0-9_-]{1,1024}$/.test(body.attachmentId)) reason='attachment_id_missing';
      if (reason) excluded.push({filename:name.slice(0,255),reason:reason});
      else accepted.push({attachment_id:body.attachmentId,filename:name.slice(0,255),mime_type:mime,size:body.size});
    }
    (part.parts || []).forEach(function(child) {walk(child,depth+1);});
  }
  walk(payload || {},0);
  return {accepted:accepted,excluded:excluded};
}

// Read one bounded page. Pass next_page_token to fetch another page manually.
// Result is a preview, never a durable cursor or proof a message was imported.
function previewGmailDocumentsPage(pageToken) {
  return gdiDiscoverPage_(gdiConfig_(), pageToken);
}

function gdiDiscoverPage_(config, pageToken) {
  if (pageToken !== undefined && (typeof pageToken!=='string' || pageToken.length>2048)) throw new Error('gmail_preview_page_token');
  const profile = Gmail.Users.getProfile('me');
  if (String(profile.emailAddress || '').toLowerCase()!==config.mailbox) throw new Error('gmail_preview_mailbox_mismatch');
  const labels = Gmail.Users.Labels.list('me').labels || [];
  const label = labels.find(function(item) {return item.name===config.label && item.type==='user';});
  if (!label) throw new Error('gmail_preview_label_missing');
  const options = {labelIds:[label.id],q:'after:'+String(Math.floor(config.startMs/1000)-1)+' -in:spam -in:trash -in:sent -in:drafts',
    includeSpamTrash:false,maxResults:config.pageSize};
  if (pageToken) options.pageToken=pageToken;
  const page = Gmail.Users.Messages.list('me',options);
  const result = {mode:'preview',mailbox:config.mailbox,label:config.label,start_at:new Date(config.startMs).toISOString(),
    candidates:[],excluded:[],errors:[],next_page_token:page.nextPageToken || null};
  const seen = new Set();
  (page.messages || []).slice(0,config.pageSize).forEach(function(ref) {
    if (seen.has(ref.id)) return;
    seen.add(ref.id);
    try {
      // Full MIME structure is needed for nested attachments. No attachment bytes
      // are downloaded; message bodies are ignored and never returned or logged.
      const message = Gmail.Users.Messages.get('me',ref.id,{format:'full'});
      const labels = message.labelIds || [];
      const received = Number(message.internalDate);
      let reason = '';
      if (!labels.includes(label.id)) reason='label_changed';
      else if (['SPAM','TRASH','SENT','DRAFT'].some(function(id) {return labels.includes(id);})) reason='excluded_folder';
      else if (!Number.isFinite(received) || received<=0 || received<config.startMs) reason='before_start_or_invalid_date';
      if (reason) {result.excluded.push({message_id:ref.id,reason:reason}); return;}
      const attachments = gdiAttachments_(message.payload);
      const subject = gdiHeader_(message.payload || {},'subject');
      const sender = gdiHeader_(message.payload || {},'from');
      const warnings = [];
      if (!subject.trim() || subject.length>500 || /[\x00-\x1f]/.test(subject)) warnings.push('subject_needs_review');
      if (!sender.trim() || sender.length>500 || /[\x00-\x1f]/.test(sender)) warnings.push('sender_needs_review');
      if (attachments.accepted.length>20) warnings.push('too_many_attachments');
      if (new Set(attachments.accepted.map(function(a) {return a.attachment_id;})).size!==attachments.accepted.length) warnings.push('duplicate_attachment_id');
      if (!attachments.accepted.length && attachments.excluded.some(function(a){return a.reason!=='inline_attachment';})) {result.excluded.push({message_id:ref.id,reason:'no_supported_attachments',attachments:attachments.excluded}); return;}
      result.candidates.push({mailbox:config.mailbox,message_id:ref.id,subject:subject.slice(0,500),sender:sender.slice(0,500),
        body_only:attachments.accepted.length===0,received_at:new Date(received).toISOString(),attachments:attachments.accepted,
        excluded_attachments:attachments.excluded,warnings:warnings,ready_for_import:warnings.length===0});
    } catch (err) {
      // Do not expose provider errors, email bodies or credential information.
      result.errors.push({message_id:ref.id,reason:'message_inspection_failed'});
    }
  });
  return result;
}

// Explicit operator action: prints correspondence METADATA in the execution log.
// Do not schedule this function. Preview does not upload files or call CSS-IS.
function previewGmailDocuments() {
  const result = previewGmailDocumentsPage();
  console.log(JSON.stringify(result,null,2));
  return result;
}
