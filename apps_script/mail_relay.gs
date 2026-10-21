// Source for the EXISTING Office Connect mail relay deployment.
// Keep the existing SHARED_SECRET value. Optionally move it into Script Properties
// under SHARED_SECRET; no secret is committed here. Add documents_relay.gs beside
// this file for durable official dispatch. Legacy MailApp requests stay compatible.
function mailSecret_() { return PropertiesService.getScriptProperties().getProperty('SHARED_SECRET'); }
function mailReply_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}
function mailSigned_(env,secret) {
  if (!secret || !env || !env.ts || !env.payload || !env.sig || !Number.isFinite(Number(env.ts)) || Math.abs(Date.now()-Number(env.ts))>5*60*1000) return false;
  const bytes=Utilities.computeHmacSha256Signature(env.ts+'.'+env.payload,secret);
  const hex=bytes.map(function (b) {return ('0'+(b&255).toString(16)).slice(-2);}).join('');
  return hex===String(env.sig);
}
function doPost(e) {
  try {
    const body=JSON.parse(e.postData.contents), secret=mailSecret_();
    if (body.payload !== undefined) {
      if (!mailSigned_(body,secret)) return mailReply_({ok:false,error:'unauthorized'});
      const req=JSON.parse(body.payload);
      return mailReply_(documentOperation_(req,['dispatch','status']));
    }
    if (!secret || body.secret!==secret) return mailReply_({ok:false,error:'unauthorized'});
    if (!body.to || !body.subject) return mailReply_({ok:false,error:'missing to/subject'});
    const message={to:body.to,subject:body.subject,body:body.text || '',name:body.fromName || 'Office Connect'};
    if (body.html) message.htmlBody=body.html;
    if (body.replyTo) message.replyTo=String(body.replyTo);
    if (body.attachments && body.attachments.length) message.attachments=body.attachments.map(function (a) {
      return Utilities.newBlob(Utilities.base64Decode(a.base64),a.mimeType,a.name);
    });
    MailApp.sendEmail(message);
    return mailReply_({ok:true});
  } catch (err) { return mailReply_({ok:false,error:'mail_operation_failed'}); }
}
