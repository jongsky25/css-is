const { chromium } = require('playwright');
const path = require('path');
const {execFileSync} = require('child_process');
const root = path.resolve(__dirname, '../..');
const html = execFileSync('python', ['-c', `
from jinja2 import Environment, FileSystemLoader
import work_intake
env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
source = open('templates/documents/new.html').read().replace('{% extends \"documents/base.html\" %}', '')
print(env.from_string(source).render(enabled=True, csrf='token', values={}, work_enabled=False, scenarios=work_intake.SCENARIOS, preview=None, people=[], units=[]))
`], {cwd:root, encoding:'utf8'});
const assert = require('assert');
(async () => {
 const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE || undefined});
 const page = await browser.newPage({viewport:{width:390,height:844}});
 let calls=0, delayed=false, outcome='success';
 await page.route('http://intake.test/**', async route => {
  if(route.request().url().endsWith('/documents/intake/read')) {
   calls++;
   if(outcome === 'timeout') return;
   if(outcome === 'error') return route.fulfill({status:400,json:{error:'No readable text was found. Try a clearer scan.'}});
   if(outcome === 'html') return route.fulfill({status:502,contentType:'text/html',body:'Gateway error'});
   if(outcome === 'network') return route.abort('failed');
   if(outcome === 'empty') return route.fulfill({json:{suggestions:{},evidence:{},warnings:[],notice:'Review',reading:{page_count:1,ocr_pages:[]},text_preview:[{page:1,text:'Unlabelled document text',truncated:false}]}});
   if(delayed) await new Promise(r=>setTimeout(r,400));
   return route.fulfill({json:{suggestions:{sender:'Training Office'},evidence:{},warnings:[],notice:'Review values',
    reading:{page_count:1,ocr_pages:[1]},text_preview:[{page:1,text:'<script>window.injected=true</script>\nFrom: Training Office',truncated:false}]}}).catch(()=>{});
  }
  if(route.request().url().endsWith('.js')) return route.fulfill({body:'',contentType:'application/javascript'});
  return route.fulfill({body:html,contentType:'text/html'});
 });
 await page.goto('http://intake.test/');
 await page.addScriptTag({path:path.join(root,'static/js/work-intake.js')});
 const file=page.locator('#intake-pdf'), status=page.locator('#intake-read-status');
 await file.setInputFiles({name:'large.pdf',mimeType:'application/pdf',buffer:Buffer.alloc(7*1024*1024)});
 assert((await status.innerText()).includes('OCR did not run'));
 await page.locator('#intake-read').click(); assert.equal(calls,0);
 await page.locator('#intake-remove').click(); assert.equal(await file.inputValue(),'');
 await file.setInputFiles({name:'scan.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-test')});
 assert((await status.innerText()).includes('Reading has not started'));
 await page.locator('#intake-read').click();
 await page.waitForFunction(()=>document.getElementById('intake-read-status').textContent.includes('OCR ran on page(s) 1'));
 await page.locator('#intake-suggestions summary').click();
 assert((await page.locator('#intake-suggestions pre').innerText()).includes('From: Training Office'));
 assert.equal(await page.evaluate(()=>window.injected),undefined);
 assert((await file.inputValue()).endsWith('scan.pdf'));
 assert((await status.innerText()).includes('1 empty field(s) pre-filled'));
 await page.locator('#intake-remove').click();
 assert(await page.locator('#intake-suggestions').isHidden());
 assert.equal(await page.locator('[name=sender]').inputValue(),'Training Office');
 await page.locator('[name=sender]').fill('');
 delayed=true;
 await file.setInputFiles({name:'scan.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-test')});
 await page.locator('#intake-read').click();
 await page.locator('#intake-remove').click();
 await page.waitForTimeout(700);
 assert.equal(await page.locator('[name=sender]').inputValue(),'');
 assert(await page.locator('#intake-suggestions').isHidden());
 assert(await page.locator('#intake-read').isEnabled());
 delayed=false;
 for(const kind of ['error','html','network','empty']) {
  outcome=kind;
  await file.setInputFiles({name:'retry.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-test')});
  await page.locator('#intake-read').click();
  await page.waitForFunction(()=>!document.getElementById('intake-read').disabled);
  assert((await file.inputValue()).endsWith('retry.pdf'));
  assert.equal(await page.locator('[name=sender]').inputValue(),'');
  if(kind==='empty') {
   assert((await status.innerText()).includes('no form fields could be identified'));
   assert(await page.locator('#intake-suggestions pre').isVisible());
  } else {
   assert((await status.innerText()).includes('Reading did not complete'));
  }
 }
 outcome='success';
 await page.locator('#intake-read').click();
 await page.waitForFunction(()=>!document.getElementById('intake-read').disabled);
 assert.equal(await page.locator('[name=sender]').inputValue(),'Training Office');
 assert((await file.inputValue()).endsWith('retry.pdf'));
 await page.locator('#intake-read').click();
 await page.waitForFunction(()=>!document.getElementById('intake-read').disabled);
 assert((await status.innerText()).includes('0 empty field(s) pre-filled'));
 await page.clock.install();
 outcome='timeout';
 await page.locator('#intake-read').click();
 await page.clock.fastForward(90001);
 await page.waitForFunction(()=>document.getElementById('intake-read-status').textContent.includes('Reading timed out'));
 assert((await file.inputValue()).endsWith('retry.pdf'));
 assert(await page.locator('#intake-read').isEnabled());
 console.log('Mobile selection, success/no-match/error/timeout outcomes, retry, removal and stale-result checks passed.');
 await browser.close();
})();
