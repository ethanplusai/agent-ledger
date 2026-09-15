/* Synthetic browser exercise: no installed model is invoked. */
'use strict';
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{
  const child=spawn(process.env.PYTHON||'python3',['ledger.py','--demo','--no-open'],{cwd:root,stdio:['ignore','pipe','pipe']});let browser;
  try{
    const url=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('Demo startup timeout')),20000);child.on('error',reject);child.stdout.on('data',chunk=>{out+=chunk;const match=out.match(/http:\/\/127\.0\.0\.1:\d+\/#[A-Za-z0-9_-]+/);if(match){clearTimeout(timer);resolve(match[0]);}});});
    browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>{assert.ok(route.request().url().startsWith(new URL(url).origin+'/'));return route.continue();});
    await page.goto(url);await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Ready'));
    await page.click('[data-page=ask]');assert.equal(await page.locator('#ask-find').isEnabled(),false);
    await page.selectOption('#project','/demo/atlas');await page.fill('#ask-question','Why did we choose SQLite instead of a hosted database?');
    await page.click('#ask-find');await page.waitForSelector('#ask-sources .ask-source');assert.match(await page.locator('#ask-status').innerText(),/Nothing has been sent/);
    assert.equal(await page.locator('#ask-answer').isVisible(),false);await page.click('#ask-run');
    await page.waitForSelector('#ask-answer:not([hidden])');assert.match(await page.locator('#ask-answer-text').innerText(),/no AI was called/);
    assert.ok(await page.locator('.citation-link').count());
    await page.locator('.citation-link').first().click();await page.waitForSelector('#reader:not([hidden])');
    await page.click('[data-page=ask]');assert.equal(await page.locator('#ask-answer').isVisible(),true);
    await page.click('#ask-save');assert.match(await page.locator('#note-status').innerText(),/AI draft/);
    assert.equal(await page.locator('#notes-list .saved-note').count(),0);
    await page.click('#note-form button[type=submit]');await page.waitForFunction(()=>document.querySelectorAll('#notes-list .saved-note').length===1);
    await page.click('[data-page=ask]');await page.selectOption('#project','/demo/studio');assert.equal(await page.locator('#ask-answer').isVisible(),false);assert.equal(await page.locator('#ask-question').inputValue(),'');
    await page.selectOption('#project','/demo/atlas');assert.equal(await page.locator('#ask-answer').isVisible(),true);
    await page.fill('#ask-question','What constraints mattered?');await page.click('#ask-find');await page.waitForSelector('#ask-sources .ask-source');await page.click('#ask-run');await page.waitForSelector('#ask-answer:not([hidden])');
    for(const width of [1440,360]){await page.setViewportSize({width,height:1000});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));if(process.argv.includes('--screenshots'))await page.screenshot({path:path.join(root,'docs/screenshots/demo-ask-'+width+'.png'),fullPage:true});}
    await page.click('[data-page=usage]');await page.waitForSelector('.usage-driver');assert.match(await page.locator('#session-review').innerText(),/Opportunities to investigate/);await page.locator('.optimization summary').first().click();assert.match(await page.locator('.optimization').first().innerText(),/Try next time/);
    await page.locator('.optimization button').first().click();await page.waitForFunction(()=>document.querySelector('#tab-response').getAttribute('aria-selected')==='true');
    await page.locator('.usage-driver button').first().click();await page.waitForFunction(()=>document.querySelector('#turn').value!==''&&document.querySelectorAll('.usage-driver').length===1);
    assert.deepEqual(errors,[]);console.log('Ask flows passed: project isolation, local evidence, synthetic answers, citations, follow-up, reviewed saves, optimization evidence, desktop/mobile, no external requests.');
  }finally{if(browser)await browser.close();child.kill('SIGINT');}
})().catch(error=>{console.error(error);process.exitCode=1;});
