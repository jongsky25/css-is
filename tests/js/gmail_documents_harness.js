const fs=require('fs'),vm=require('vm'),assert=require('assert');
const props={GMAIL_DOCUMENTS_PREVIEW_ENABLED:'true',GMAIL_DOCUMENTS_MAILBOX:'office@example.test',
 GMAIL_DOCUMENTS_LABEL:'CSS-Documents',GMAIL_DOCUMENTS_START_AT:'2026-10-17T00:00:00+08:00'};
let mailbox='office@example.test', labels=[{id:'Label_1',name:'CSS-Documents',type:'user'}], messages={}, page={}, calls=[];
const fail=()=>{throw Error('Unexpected write or download');};
const ctx={console:{log:fail},Date,JSON,Math,Number,String,Array,Set,Error,
 PropertiesService:{getScriptProperties:()=>({getProperty:k=>props[k],setProperty:fail})},
 DriveApp:new Proxy({},{get:()=>fail}),UrlFetchApp:{fetch:fail},MailApp:{sendEmail:fail},
 Gmail:{Users:{getProfile:()=>({emailAddress:mailbox}),Labels:{list:()=>({labels}),create:fail},
 Messages:{list:(user,options)=>{calls.push(options);return page;},get:(user,id)=>{if(messages[id] instanceof Error)throw messages[id];return messages[id];},
 modify:fail,send:fail,Attachments:{get:fail}}}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('apps_script/gmail_documents.gs','utf8'),ctx);
const run=(token)=>JSON.parse(JSON.stringify(ctx.previewGmailDocumentsPage(token)));
function attachment(name='memo.pdf',mime='application/pdf',id='attachment1',size=1024,headers=[]){return {filename:name,mimeType:mime,body:{attachmentId:id,size},headers};}
function message(parts=[attachment()],extra={}) {return {internalDate:String(Date.parse(props.GMAIL_DOCUMENTS_START_AT)),labelIds:['Label_1','INBOX'],
 payload:{mimeType:'multipart/mixed',headers:[{name:'Subject',value:'Memo'},{name:'From',value:'Sender <sender@example.test>'}],
 parts:[{mimeType:'text/plain',body:{data:'PRIVATE_BODY_SENTINEL',size:10}},...parts]},...extra};}
function set(items){messages=items;page={messages:Object.keys(items).map(id=>({id}))};calls=[];}
let checks=0;
function check(name,fn){fn();checks++;console.log('PASS '+name);}
check('nested attachment and metadata only',()=>{
 set({abc:message([{mimeType:'multipart/related',parts:[attachment(),attachment('logo.png','image/png','logo',100,[{name:'Content-Disposition',value:'inline'}])]}])});
 const r=run();assert.equal(r.candidates.length,1);assert.equal(r.candidates[0].attachments.length,1);
 assert.equal(r.candidates[0].excluded_attachments[0].reason,'inline_attachment');assert(r.candidates[0].ready_for_import);
 assert(!JSON.stringify(r).includes('PRIVATE_BODY_SENTINEL'));
 assert.deepEqual(calls[0].labelIds,['Label_1']);assert.equal(calls[0].maxResults,25);
 assert(calls[0].q.includes('after:'+(Date.parse(props.GMAIL_DOCUMENTS_START_AT)/1000-1)));
});
check('message-level label, date and folder checks',()=>{
 set({a:message([], {internalDate:String(Date.parse(props.GMAIL_DOCUMENTS_START_AT)-1)}),b:message(undefined,{labelIds:['Label_1','SENT']}),
 c:message(undefined,{labelIds:['INBOX']}),d:message(undefined,{labelIds:['Label_1','DRAFT']})});
 const r=run();assert.equal(r.candidates.length,0);assert.equal(r.excluded.length,4);
});
check('unsupported, oversized, inline CID and missing attachment IDs',()=>{
 set({abc:message([attachment('zip.zip','application/zip'),attachment('large.pdf','application/pdf','large',20*1024*1024+1),
 attachment('logo.png','image/png','logo',100,[{name:'Content-ID',value:'<logo>'}]),attachment('memo.pdf','application/pdf','')])});
 const r=run();assert.equal(r.excluded[0].reason,'no_supported_attachments');assert.equal(r.excluded[0].attachments.length,4);
});
check('pagination is explicit and bounded',()=>{
 set({abc:message(),def:message()});props.GMAIL_DOCUMENTS_PAGE_SIZE='1';page.nextPageToken='next';
 const r=run('previous');assert.equal(r.candidates.length,1);assert.equal(r.next_page_token,'next');
 assert.equal(calls[0].pageToken,'previous');delete props.GMAIL_DOCUMENTS_PAGE_SIZE;
});
check('missing headers are candidates requiring review',()=>{
 const m=message();m.payload.headers=[];set({abc:m});const r=run();assert(!r.candidates[0].ready_for_import);assert.equal(r.candidates[0].warnings.length,2);
});
check('excess attachments and duplicates require review',()=>{
 set({abc:message(Array.from({length:21},()=>attachment()))});const r=run();assert(!r.candidates[0].ready_for_import);
 assert(r.candidates[0].warnings.includes('too_many_attachments'));assert(r.candidates[0].warnings.includes('duplicate_attachment_id'));
});
check('provider error isolated without leaking provider text',()=>{
 set({abc:new Error('SECRET_PROVIDER_TEXT'),def:message()});const r=run();assert.equal(r.errors.length,1);assert.equal(r.candidates.length,1);
 assert(!JSON.stringify(r).includes('SECRET_PROVIDER_TEXT'));
});
check('disabled by default and mailbox identity required',()=>{
 delete props.GMAIL_DOCUMENTS_PREVIEW_ENABLED;assert.throws(run,/disabled/);props.GMAIL_DOCUMENTS_PREVIEW_ENABLED='true';
 mailbox='wrong@example.test';assert.throws(run,/mailbox_mismatch/);mailbox='office@example.test';
 labels=[];assert.throws(run,/label_missing/);labels=[{id:'Label_1',name:'CSS-Documents',type:'user'}];
});
check('explicit valid start date and page size required',()=>{
 for(const value of ['', '2026-02-30T00:00:00Z','2026-10-17','invalid']){props.GMAIL_DOCUMENTS_START_AT=value;assert.throws(run,/start/);}
 props.GMAIL_DOCUMENTS_START_AT='2026-10-17T00:00:00+08:00';
 for(const value of ['0','101','abc']){props.GMAIL_DOCUMENTS_PAGE_SIZE=value;assert.throws(run,/page_size/);}
 delete props.GMAIL_DOCUMENTS_PAGE_SIZE;assert.throws(()=>run({}),/page_token/);
});
check('duplicate list entries, empty mailbox and attached emails',()=>{
 set({abc:message([attachment('forward.eml','message/rfc822')])});page.messages.push({id:'abc'});assert.equal(run().excluded.length,1);
 set({});assert.equal(run().candidates.length,0);
});
console.log(checks+' Gmail discovery contracts passed');
