'use strict';
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{
 const child=spawn(process.env.PYTHON||'python3',['ledger.py','--demo','--no-open'],{cwd:root,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const url=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(new Error('Startup timed out')),20000);child.on('error',reject);child.on('exit',code=>reject(new Error('Server exited '+code)));child.stdout.on('data',b=>{text+=b;const m=text.match(/http:\/\/127\.0\.0\.1:\d+\/#[A-Za-z0-9_-]+/);if(m){clearTimeout(timer);resolve(m[0]);}});});
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));const remote=[];await page.route('**/*',r=>{if(!r.request().url().startsWith(new URL(url).origin+'/')){remote.push(r.request().url());return r.abort();}return r.continue();});
  await page.context().grantPermissions(['clipboard-read','clipboard-write'],{origin:new URL(url).origin});
  await page.goto(url);await page.waitForSelector('.project-shortcut');assert.equal(await page.locator('#usage-review').isVisible(),false);
  await page.getByRole('button',{name:'Continue atlas',exact:true}).click();await page.waitForSelector('.brief-source');assert.match(await page.locator('#briefing-sources').innerText(),/SQLite/);
  await page.click('#build-handoff');await page.fill('#handoff-goal','Finish keyboard navigation and validate the release.');await page.click('#copy-handoff');await page.waitForFunction(()=>document.getElementById('handoff-status').textContent.startsWith('Copied.'));
  const copied=await page.evaluate(()=>navigator.clipboard.readText());assert.match(copied,/Finish keyboard/);assert.match(copied,/message:/);assert.match(copied,/historical/);
  await page.click('#save-handoff');await page.waitForFunction(()=>document.getElementById('handoff-status').textContent.startsWith('Saved to this project'));
  for(const width of [1440,736,360]){await page.setViewportSize({width,height:1100});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Briefing overflow '+width);if(process.argv.includes('--screenshots'))await page.screenshot({path:path.join(root,'docs/screenshots/demo-briefing-'+width+'.png'),fullPage:true});}
  await page.selectOption('#project','/demo/studio');await page.waitForFunction(()=>document.getElementById('briefing-title').textContent==='Continue studio'&&!document.getElementById('build-handoff').disabled);await page.click('#build-handoff');assert.equal(await page.inputValue('#handoff-goal'),'');
  await page.selectOption('#project','/demo/atlas');await page.waitForFunction(()=>document.getElementById('handoff-goal').value.startsWith('Finish keyboard'));assert.match(await page.inputValue('#handoff-text'),/SQLite/);
  await page.fill('#handoff-goal','Finish the updated objective.');await page.click('#save-handoff');await page.waitForFunction(()=>document.getElementById('handoff-status').textContent.startsWith('Saved to this project'));
  await page.click('[data-page=notes]');await page.waitForSelector('.saved-note');assert.equal(await page.locator('.saved-note').count(),1);assert.match(await page.locator('#notes-list').innerText(),/updated objective/);
  await page.setViewportSize({width:1440,height:1100});await page.click('[data-page=home]');await page.waitForSelector('.brief-source');await page.locator('.brief-source button').first().click();await page.waitForSelector('.selected-message');assert.match(await page.locator('#reader').innerText(),/Historical conversation/);
  assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);console.log('Briefing flow passed: project recovery, source citations, copied editable handoff, saved update without duplicates, project draft isolation, source navigation, mobile layouts, no external requests.');
 }finally{if(browser)await browser.close();child.kill('SIGINT');}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
