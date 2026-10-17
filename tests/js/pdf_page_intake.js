// Requires Playwright, Python runtime dependencies and Tesseract. Uses synthetic data only.
const {chromium} = require('playwright');
const {spawn} = require('child_process');
const path = require('path');
const assert = require('assert');
const root = path.resolve(__dirname, '../..');
(async()=>{
 const server = spawn('python',['tests/browser/pdf_page_server.py'],{cwd:root,stdio:['ignore','inherit','inherit']});
 let browser;
 try {
  const base='http://127.0.0.1:8899';
  let response;
  for(let i=0;i<60;i++) { try {response=await fetch(base+'/counts');if(response.ok)break;}catch{} await new Promise(r=>setTimeout(r,300)); }
  assert(response?.ok,'Synthetic server did not start');
  const counts=await response.json();
  const pdf=Buffer.from(await (await fetch(base+'/fixture.pdf')).arrayBuffer());
  assert(pdf.length>20*1024*1024);
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE || undefined});
  const context=await browser.newContext({viewport:{width:390,height:844}});
  await context.addCookies([{name:'css_session',value:'synthetic',url:base}]);
  const page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let pageUploads=0, originals=0, failNext=false, delayNext=false;
  page.on('request',r=>{
   if(r.method()==='POST') {
    if(r.url().endsWith('/intake/read')) originals++;
    if(r.url().endsWith('/intake/page')) {
     pageUploads++;
     assert.equal(r.headers()['content-type'],'image/jpeg');
     assert(r.postDataBuffer().length<=2*1024*1024);
    }
   }
  });
  await page.route('**/documents/intake/page',async route=>{
   if(failNext){failNext=false;return route.fulfill({status:503,json:{error:'Synthetic retryable failure'}});}
   if(delayNext){delayNext=false;await new Promise(r=>setTimeout(r,1200));return route.fulfill({json:{text:'Subject: Late result must be ignored'}}).catch(()=>{});}
   await route.continue();
  });
  await page.goto(base+'/fixture');
  await page.locator('#intake-pdf').setInputFiles({name:'large-scanned.pdf',mimeType:'application/pdf',buffer:pdf});
  await page.locator('#pdf-open').click();
  await page.waitForFunction(()=>document.getElementById('pdf-progress').textContent.includes('Preview ready'),{},{timeout:30000});
  assert((await page.locator('#pdf-info').innerText()).includes('3 pages'));
  assert.equal(originals,0);
  await page.locator('#pdf-selection').fill('2');
  failNext=true;
  await page.locator('#pdf-read-pages').click();
  await page.waitForFunction(()=>document.getElementById('pdf-results').textContent.includes('Synthetic retryable failure'));
  await page.waitForFunction(()=>!document.getElementById('pdf-retry').disabled);
  await page.locator('#pdf-retry').click();
  await page.waitForFunction(()=>document.getElementById('pdf-results').textContent.includes('Page 2: read with OCR'),{},{timeout:30000});
  await page.waitForFunction(()=>!document.getElementById('pdf-read-pages').disabled);
  assert.equal(await page.locator('[name=subject]').inputValue(),'Staff orientation');
  assert((await page.locator('#intake-suggestions').innerText()).includes('Page 2:'));
  // Cancellation preserves earlier pages and ignores late OCR output.
  await page.locator('#pdf-selection').fill('3');delayNext=true;
  const waiting=page.waitForRequest(r=>r.url().endsWith('/intake/page'));
  await page.locator('#pdf-read-pages').click();await waiting;
  await page.locator('#pdf-cancel').click();
  await page.waitForTimeout(1500);
  assert((await page.locator('#pdf-results').innerText()).includes('Page 2: read with OCR'));
  assert((await page.locator('#pdf-results').innerText()).includes('Page 3: not processed'));
  assert.equal(await page.locator('[name=subject]').inputValue(),'Staff orientation');
  await page.locator('#pdf-read-pages').click();
  await page.waitForFunction(()=>document.getElementById('pdf-results').textContent.includes('Page 3: read with OCR'),{},{timeout:30000});
  await page.waitForFunction(()=>!document.getElementById('pdf-read-pages').disabled);
  await page.locator('#pdf-selection').fill('1');
  const uploadsBefore=pageUploads;
  await page.locator('#pdf-read-pages').click();
  await page.waitForFunction(()=>document.getElementById('pdf-results').textContent.includes('Page 1: read directly'));
  await page.waitForFunction(()=>!document.getElementById('pdf-read-pages').disabled);
  assert.equal(pageUploads,uploadsBefore,'Native text should not upload a page image');
  assert.equal(originals,0,'Original large PDF must never be uploaded');
  assert.deepEqual(await (await fetch(base+'/counts')).json(),counts);
  await page.locator('#intake-remove').click();
  assert(await page.locator('#pdf-pages').isHidden());
  assert.equal(await page.locator('#intake-pdf').inputValue(),'');
  assert.deepEqual(errors,[]);
  console.log('Real large PDF preview, OCR, native text, original page evidence, retry, cancel, removal and zero persistence passed at 390px.');
 } finally {await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
