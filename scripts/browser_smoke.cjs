/* Optional developer check. Requires Playwright; the application itself does not. */
'use strict';
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');

(async()=>{
  const child=spawn(process.env.PYTHON || (process.platform==='win32'?'python':'python3'),['report.py','--demo','--no-open'],{cwd:root,stdio:['ignore','pipe','pipe']});
  let browser;
  try {
    const url=await new Promise((resolve,reject)=>{
      let text='';const timer=setTimeout(()=>reject(new Error('Demo server startup timed out')),20000);
      child.on('error',reject);child.on('exit',code=>reject(new Error('Demo server exited: '+code)));
      child.stdout.on('data',chunk=>{text+=chunk;const match=text.match(/http:\/\/127\.0\.0\.1:\d+\/#[A-Za-z0-9_-]+/);if(match){clearTimeout(timer);resolve(match[0]);}});
    });
    browser=await chromium.launch({headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1,colorScheme:'light'});
    const errors=[],remote=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>{
      if(!route.request().url().startsWith(new URL(url).origin+'/')){remote.push('Unexpected nonlocal request');return route.abort();}
      return route.continue();
    });
    await page.goto(url);
    const ready=()=>page.waitForFunction(()=>document.getElementById('status').textContent.toLowerCase().includes('ready'));
    await ready();
    await page.click('[data-page=usage]');
    await ready();
    await page.locator('.skip-link').focus();
    assert.equal(await page.locator('.skip-link').evaluate(node=>node===document.activeElement),true);
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('.session').count(),7);
    assert.equal(await page.locator('.bar').count(),18);
    assert.equal(await page.locator('.session[aria-pressed=true]').count(),1);
    assert.equal(await page.locator('#measure').inputValue(),'context');
    assert.match(await page.locator('#usage-explanation').innerText(),/input sent to the model/);
    assert.match(await page.locator('#context-summary').innerText(),/Peak context sent/);
    assert.equal(await page.locator('#context-rows tr').count(),18);
    assert.match(await page.locator('#usage-explanation').innerText(),/available estimated credits/);
    await page.locator('.largest-responses button').first().click();
    await page.waitForFunction(()=>document.getElementById('response').selectedIndex===17);
    await page.locator('.bar').nth(2).click();
    await page.waitForFunction(()=>document.getElementById('response').selectedIndex===2);
    assert.match(await page.locator('#context-readout').innerText(),/Change: \+5,300/);
    await page.locator('.request-table summary').click();
    await page.locator('#context-rows button').nth(3).click();
    await page.waitForFunction(()=>document.getElementById('response').selectedIndex===3);
    await page.locator('.request-table summary').click();
    await page.locator('.bar').nth(2).click();
    await page.locator('#evidence summary').first().click();
    await page.waitForFunction(()=>document.querySelector('#evidence pre').textContent.includes('<script>'));
    assert.equal(await page.evaluate(()=>window.demoInjection),undefined);
    await page.click('#tab-findings');
    assert.equal(await page.locator('#view-response').isVisible(),false);
    assert.equal(await page.locator('#view-findings').isVisible(),true);
    await page.locator('#findings button').first().click();
    await page.waitForFunction(()=>document.getElementById('tab-response').getAttribute('aria-selected')==='true');
    await page.locator('#tab-response').focus();await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#tab-conversation').getAttribute('aria-selected'),'true');
    await page.keyboard.press('End');
    assert.equal(await page.locator('#tab-coverage').getAttribute('aria-selected'),'true');
    await page.keyboard.press('Home');
    assert.equal(await page.locator('#tab-response').getAttribute('aria-selected'),'true');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('#view-response').evaluate(node=>node===document.activeElement),true);
    await page.selectOption('#measure','credits');
    await page.locator('.bar').nth(5).focus();await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.getElementById('response').selectedIndex===5);
    await page.selectOption('#turn',{index:1});
    await page.waitForFunction(()=>document.querySelectorAll('.bar').length===6);
    await page.selectOption('#turn','');
    await page.waitForFunction(()=>document.querySelectorAll('.bar').length===18);
    await page.selectOption('#measure','context');await page.selectOption('#response',{index:0});
    await page.waitForFunction(()=>document.getElementById('detail').textContent.includes('10,000'));
    // Agent comparison, tool breakdown, compaction markers and the conversation replay.
    assert.equal(await page.locator('#providers .provider').count(),2);
    const compare=await page.locator('#agent-compare').innerText();
    assert.match(compare,/Claude Code/);assert.match(compare,/Codex/);
    assert.match(compare,/No verified credit rate/);
    await page.selectOption('#agent','claude');await ready();
    await page.waitForFunction(()=>document.getElementById('agent-compare').hidden===true);
    await page.selectOption('#agent','');await ready();
    await page.locator('.session').first().click();
    await page.waitForFunction(()=>document.querySelectorAll('.bar').length===18);
    assert.equal(await page.locator('.compaction').count()>0,true);
    await page.click('#tab-tools');
    await page.waitForFunction(()=>document.querySelectorAll('#tool-rows tr').length>0);
    assert.match(await page.locator('#tool-metrics').innerText(),/Failed results/);
    assert.equal(await page.locator('#tool-rows .tool-failed').count()>0,true);
    const scoped=await page.locator('#tool-rows tr').count();
    await page.check('#tools-all');
    await page.waitForFunction(count=>document.querySelectorAll('#tool-rows tr').length>count,scoped);
    await page.uncheck('#tools-all');
    await page.waitForFunction(count=>document.querySelectorAll('#tool-rows tr').length===count,scoped);
    await page.click('#tab-conversation');
    await page.waitForFunction(()=>document.querySelectorAll('#conversation .turn').length>0);
    assert.match(await page.locator('#conversation').innerText(),/Running total/);
    assert.match(await page.locator('#conversation-summary').innerText(),/recorded messages/);
    assert.equal(await page.locator('#conversation-prev').isDisabled(),true);
    assert.equal(await page.locator('.turn-compact').count()>0,true);
    await page.click('#tab-response');
    await page.waitForFunction(()=>document.getElementById('view-response').hidden===false);
    for(const width of [1440,1024,736,360]){
      await page.setViewportSize({width,height:1100});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Horizontal overflow at '+width);
      if(width<=800){
        assert.equal(await page.locator('#session-browser').isVisible(),false);
        await page.click('#session-toggle');
        assert.equal(await page.locator('#session-browser').isVisible(),true);
        await page.click('#session-toggle');
      }
      await page.evaluate(()=>window.scrollTo(0,0));
      if(process.argv.includes('--screenshots'))await page.screenshot({path:path.join(root,'docs/screenshots/demo-'+width+'.png'),fullPage:width!==1440,animations:'disabled'});
    }
    await page.setViewportSize({width:1440,height:1100});await page.click('#theme');
    assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
    await page.evaluate(()=>window.scrollTo(0,0));
    if(process.argv.includes('--screenshots'))await page.screenshot({path:path.join(root,'docs/screenshots/demo-dark.png'),fullPage:false,animations:'disabled'});
    await page.click('#astra');await page.waitForFunction(()=>document.querySelectorAll('.session').length===1);
    assert.match(await page.locator('#metrics').innerText(),/18/);
    await page.click('#refresh');await page.waitForFunction(()=>!document.getElementById('refresh').disabled);await ready();
    assert.equal(await page.locator('.bar').count(),18);
    await page.click('#tab-activity');await page.waitForFunction(()=>document.querySelectorAll('#all-activity .activity').length>0);
    await page.selectOption('#model','example-unpriced-model');await ready();
    await page.waitForFunction(()=>document.getElementById('session-title').textContent.includes('Explore'));
    assert.match(await page.locator('#metrics').innerText(),/Unavailable/);
    await page.fill('#from','2099-01-01');await page.locator('#from').dispatchEvent('change');
    await page.waitForFunction(()=>document.querySelectorAll('.session').length===0);
    await page.click('#all-dates');await ready();
    assert.equal(await page.locator('.session').count(),1);
    assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
    console.log('Browser checks passed: selectors, keyboard, filters, refresh, evidence, inert text, empty state, themes, 360/736/1024/1440 widths, no remote requests.');
  } finally {
    if(browser)await browser.close();
    child.kill('SIGINT');
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
