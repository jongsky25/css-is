// Optional PDF_TEST_FILE exercises a locally supplied PDF; it is never copied into the repository.
const {chromium,webkit}=require('playwright');
const {spawn}=require('child_process');
const fs=require('fs'),assert=require('assert'),path=require('path');
const root=path.resolve(__dirname,'../..');
(async()=>{
 const server=spawn('python',['tests/browser/pdf_page_server.py'],{cwd:root,stdio:['ignore','inherit','inherit']});let browser;
 try {
  const base='http://127.0.0.1:8899';
  for(let i=0;i<60;i++){try{if((await fetch(base+'/counts')).ok)break;}catch{}await new Promise(r=>setTimeout(r,300));}
  browser=await (process.env.PDF_BROWSER === 'webkit' ? webkit : chromium).launch({headless:true,executablePath:process.env.PDF_BROWSER === 'webkit' ? undefined : process.env.CHROMIUM_EXECUTABLE});
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.context().addCookies([{name:'css_session',value:'synthetic',url:base}]);
  await page.goto(base+'/fixture');
  const code=fs.readFileSync(path.join(root,'static/js/app.js'),'utf8');
  const end=code.indexOf('/* Searchable combobox');
  const start=code.lastIndexOf('(function () {',code.indexOf('function enhance(input)',code.indexOf('function shortFmt')));
  await page.addScriptTag({content:code.slice(start,end)});
  assert(await page.locator('#intake-details').isHidden());
  if(process.env.PDF_TEST_FILE){
   await page.locator('#intake-pdf').setInputFiles(process.env.PDF_TEST_FILE);
   await page.waitForFunction(()=>document.querySelector('[name=document_date]').value==='2026-10-14',{},{timeout:60000});
   await page.waitForFunction(()=>document.getElementById('intake-form').dataset.pageBusy==='false');
   assert((await page.locator('[name=subject]').inputValue()).endsWith('Diagnostic Algorithm'));
   const region = page.locator('[name=subject]').locator('..').locator('details').filter({hasText:'DTRAK subject box read'});
   await region.locator('summary').click();
   assert(await region.locator('img').isVisible());
   assert((await region.locator('pre').innerText()).includes('Diagnostic Algorithm'));
   assert.equal(await page.locator('[name=type]').inputValue(),'Memorandum');
   assert.equal(await page.locator('[name=due_date]').inputValue(),'2026-10-16');
   assert.equal(await page.locator('[name=sender]').inputValue(),'BLHSD - Health Systems Development Division (HSDD)');
   assert((await page.locator('[name=references]').inputValue()).includes('2026-000118314'));
   assert.equal(await page.locator('[name=document_date]').evaluate(e=>e.parentNode.querySelector('.datefix-disp').textContent),'14 Oct 2026');
  }else{
   await page.locator('#intake-skip').click();
   await page.locator('[name=subject]').fill('Synthetic correspondence');
   await page.locator('[name=type]').fill('Memorandum');
  }
  assert.equal(await page.getByRole('button',{name:'Use this suggestion',exact:true}).count(),0);
  await page.locator('#intake-approve').click();
  assert(await page.locator('#intake-work').isVisible());
  await page.locator('[name=confirmed]').check();
  assert(await page.locator('#intake-register').isVisible());
  await page.locator('[name=subject]').fill('Manually corrected subject');
  assert(await page.locator('#intake-work').isHidden());
  await page.locator('#intake-approve').click();
  assert(await page.locator('#intake-register').isVisible());
  if(process.env.PDF_TEST_FILE){
   await page.locator('#intake-pdf').setInputFiles({name:'replacement.pdf',mimeType:'application/pdf',buffer:fs.readFileSync(process.env.PDF_TEST_FILE)});
   await page.waitForFunction(()=>document.querySelector('[name=document_date]').value==='2026-10-14',{},{timeout:60000});
   await page.waitForFunction(()=>document.getElementById('intake-form').dataset.pageBusy==='false');
   assert.equal(await page.locator('[name=subject]').inputValue(),'Manually corrected subject');
   assert(await page.locator('#intake-register').isHidden());
  }
  const reconcile = async texts => page.evaluate(async texts => {
   const form=document.getElementById('intake-form');
   const response=await fetch('/documents/intake/pages-result',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':form.elements.csrf.value},body:JSON.stringify({pages:texts.map((text,i)=>({page:i+1,text,ocr:true}))})});
   if(!response.ok) throw Error('Aggregate failed');
   form.dispatchEvent(new CustomEvent('intake-reading-result',{detail:await response.json()}));
  },texts);
  await page.locator('[name=subject]').fill('');
  await reconcile(['Subject: Submission of comments on the updated service guidelines','Subject: SUBMISSION OF COMMENTS ON THE UPDATED']);
  assert.equal(await page.locator('[name=subject]').inputValue(),'Submission of comments on the updated service guidelines');
  await reconcile(['Subject: Approve the proposal','Subject: Reject the proposal']);
  assert.equal(await page.locator('[name=subject]').inputValue(),'');
  assert((await page.locator('[name=subject]').locator('..').innerText()).includes('Page 2: Reject the proposal'));
  await page.locator('[name=subject]').fill('Reviewed subject');
  await reconcile(['Subject: Approve the proposal','Subject: Reject the proposal']);
  assert.equal(await page.locator('[name=subject]').inputValue(),'Reviewed subject');
  await page.evaluate(()=>document.getElementById('intake-form').dispatchEvent(new CustomEvent('intake-reading-result',{detail:null})));
  assert((await page.locator('#intake-read-status').innerText()).includes('could not be displayed'));
  assert.equal(await page.locator('[name=subject]').inputValue(),'Reviewed subject');
  await page.evaluate(()=>document.getElementById('intake-form').dispatchEvent(new CustomEvent('intake-reading-result',{detail:{scope:'selected_pages',suggestions:{},evidence:{},warnings:[],text_preview:[],field_readings:{subject:[{page:1,status:'failed',method:'dtrak_subject_cell',raw:'',reason:'Subject reading timed out.'}]}}})));
  assert((await page.locator('[name=subject]').locator('..').innerText()).includes('Subject reading timed out.'));
  assert((await page.locator('#intake-suggestions').innerText()).includes('no page-text preview'));
  assert.equal(await page.locator('[name=subject]').inputValue(),'Reviewed subject');
  if(process.env.PDF_TEST_FILE){
   await page.getByRole('button',{name:'Retry this page',exact:true}).click();
   await page.waitForFunction(()=>document.getElementById('intake-form').dataset.pageBusy==='false',{},{timeout:60000});
   assert.equal(await page.locator('[name=subject]').inputValue(),'Reviewed subject');
   assert((await page.locator('[name=subject]').locator('..').textContent()).includes('DTRAK subject box read'));
  }
  assert.deepEqual(errors,[]);
  console.log('Automatic reading, visible dates, inline fields, approval invalidation and preserved edits passed.');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
