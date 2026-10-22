// Real browser clicks against the compiled application; backend hardware is a transport fixture.
// Build development UI first. Set TARS_BROWSER_EXECUTABLE to Chrome/Edge when needed.
import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import path from 'node:path';
const root=path.resolve('ui/dist/covas-next-ui/browser');
const server=createServer(async(req,res)=>{try{const file=path.resolve(root,'.'+decodeURIComponent(req.url.split('?')[0]));if(!file.startsWith(root+path.sep)&&file!==root)throw Error();const target=file===root?path.join(root,'index.html'):file;res.setHeader('Content-Type',target.endsWith('.js')?'text/javascript':target.endsWith('.css')?'text/css':target.endsWith('.json')?'application/json':target.endsWith('.png')?'image/png':target.endsWith('.svg')?'image/svg+xml':'text/html');res.end(await readFile(target));}catch{res.statusCode=404;res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch(process.env.TARS_BROWSER_EXECUTABLE?{executablePath:process.env.TARS_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']}:{channel:'msedge',headless:true});
let checks=0;
try {
 const page=await browser.newPage({viewport:{width:1400,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&m.text().includes('ERROR '))errors.push(m.text());});
 await page.addInitScript(config=>{window.testConfig=config;window.electronAPI={invoke:async (call,opts)=>{if(call==='get_screens')return [];if(call==='send_json_line'){const command=JSON.parse(opts.jsonLine);if(command.type==='change_config'){window.testConfig={...window.testConfig,...command.config};setTimeout(()=>{window.emit({type:'config',config:window.testConfig});window.emit({type:'config_save_result',request_id:command.request_id,success:true});},10)}}return {}},onStdout:cb=>{window.emit=m=>cb({payload:JSON.stringify({...m,timestamp:new Date().toISOString()})});setTimeout(()=>{window.emit({type:'config',config});window.emit({type:'plugin_settings_configs',has_plugin_settings:true,plugin_settings_configs:{}});},100)},onStderr:()=>{},onBackendLifecycle:()=>{},onWindowClose:()=>{},userAssets:{listFiles:async()=>[]}};},JSON.parse(await readFile(new URL('./profile.json',import.meta.url))));
 await page.goto(`http://127.0.0.1:${server.address().port}`);
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 const panels=['app-general-settings','app-advanced-settings','app-tars-prompt-settings','app-plugin-settings','app-tars-diagnostics'];
 const names=['GENERAL','AI & VOICE','PERSONALITY','PLUGINS','DIAGNOSTICS'];
 for(const mode of ['config','running_config','config']) {
  await page.evaluate(mode=>window.emit({type:mode,config:window.testConfig}),mode);
  for(let i=0;i<names.length;i++) {
   const tab=page.getByRole('tab',{name:names[i],exact:true});await tab.click();
   await page.waitForFunction(({i,panel})=>document.querySelectorAll('[role=tab]')[i]?.getAttribute('aria-selected')==='true'&&document.querySelector(`.mat-mdc-tab-body-active ${panel}`)?.getBoundingClientRect().height>0,{i,panel:panels[i]});checks++;
  }
  await page.getByRole('button',{name:'TARS',exact:true}).click();await page.getByRole('button',{name:'Settings',exact:true}).click();
  assert.equal(await page.getByRole('tab',{name:'DIAGNOSTICS',exact:true}).getAttribute('aria-selected'),'true');checks++;
 }
 await page.reload();await page.getByRole('button',{name:'Settings',exact:true}).click();await page.getByRole('tab',{name:'GENERAL',exact:true}).click();
 await page.locator('.general-card-grid').waitFor();assert.equal(await page.locator('.general-card-grid > section').count(),4);assert.equal((await page.locator('.general-card-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns)).split(' ').length,2);checks++;
 if(process.env.TARS_SCREENSHOT_PATH)await page.screenshot({path:process.env.TARS_SCREENSHOT_PATH});
 await page.getByRole('tab',{name:'AI & VOICE',exact:true}).click();await page.locator('.mat-mdc-tab-body-active .subsystem-grid').waitFor();checks++;
 // A genuinely incomplete profile opens resumable setup; simulated saves round-trip via the transport.
 await page.evaluate(()=>{window.testConfig={...window.testConfig,commander_name:'',api_key:'',tars_setup_step:0,tars_setup_complete:false};window.emit({type:'config',config:window.testConfig});});
 await page.getByRole('heading',{name:'Welcome to TARS'}).waitFor();checks++;
 await page.getByRole('button',{name:'Save & continue'}).click();
 await page.getByRole('heading',{name:'Commander',exact:true}).waitFor();checks++;
 await page.reload();await page.getByRole('button',{name:'Settings',exact:true}).click();
 assert.deepEqual(errors,[]);console.log(`${checks} browser click/render checks passed (online/offline/re-entry/reload/cards).`);
} finally {await browser.close();await new Promise(r=>server.close(r));}
