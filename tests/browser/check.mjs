import WebSocket from 'ws';
import fs from 'node:fs';
import {spawn,execFileSync} from 'node:child_process';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const profile=fs.mkdtempSync('/tmp/status-tracker-firefox-');
const container=process.env.TEST_CONTAINER;
if(!container?.startsWith('status-tracker-browser-'))throw Error('Use run_browser_tests.sh');
const origin=process.env.TEST_ORIGIN;
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin))throw Error('Local test origin required');
const firefox=spawn('firefox',['--headless','--no-remote','--profile',profile,'--remote-debugging-port',process.env.TEST_DEBUG_PORT || '19229','about:blank']);
let ws,id=0,context;const pending=new Map();let log='';
firefox.stderr.on('data',b=>log+=b);
const call=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;const timer=setTimeout(()=>reject(Error('Timeout '+method)),20000);pending.set(n,{resolve,reject,timer});ws.send(JSON.stringify({id:n,method,params}));});
const decode=v=>v?.type==='array'?v.value.map(decode):v?.type==='object'?Object.fromEntries(v.value.map(([k,x])=>[k,decode(x)])):v?.value;
const evaluate=async expression=>{const r=await call('script.evaluate',{expression,target:{context},awaitPromise:true});if(r.type==='exception')throw Error(r.exceptionDetails.text);return decode(r.result);};
async function until(fn,label){for(let i=0;i<100;i++){if(await fn())return;await pause(200);}throw Error(label);}
try{
 await until(()=>log.includes('WebDriver BiDi'),'Firefox startup');
 ws=new WebSocket(`ws://127.0.0.1:${process.env.TEST_DEBUG_PORT || '19229'}/session`);await new Promise((r,j)=>{ws.once('open',r);ws.once('error',j);});
 ws.on('message',raw=>{const m=JSON.parse(raw);if(m.id){const p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);m.type==='error'?p.reject(Error(m.message)):p.resolve(m.result);}}});
 await call('session.new',{capabilities:{}});context=(await call('browsingContext.getTree')).contexts[0].context;
 await call('browsingContext.navigate',{context,url:origin+'/request/1',wait:'complete'});
 await until(()=>evaluate(`document.querySelector('#update-status')?.textContent==='Live updates active'`),'SSE did not connect');
 console.log('PASS initial SSE connected');
 console.log('HTMX loaded:',await evaluate(`typeof htmx!=='undefined'`));
 await evaluate(`window.testDocumentMarker='unchanged'; window.testSwaps=0; document.body.addEventListener('htmx:afterSwap',()=>window.testSwaps++);`);
 await fetch(origin+'/test/update/55',{method:'POST'});
 await until(()=>evaluate(`document.querySelector('#detail-main').innerText.includes('55.0%')`),'progress did not update');
 if(!await evaluate(`document.querySelector('#detail-main').innerText.includes('5 MB/s') && document.querySelector('#detail-main').innerText.includes('ETA: 2m')`))throw Error('Speed/ETA stale'); console.log('PASS speed and ETA updated');
 console.log('PASS progress changed without reload; swaps:',await evaluate('window.testSwaps'));
 if(await evaluate('window.testDocumentMarker')!=='unchanged')throw Error('Page reloaded');
 await until(()=>evaluate(`document.querySelector('#detail-main').innerText.includes('Synthetic progress 55')`),'timeline did not update');
 console.log('PASS timeline updated');
 execFileSync('docker',['restart','-t','1',container]);
 await until(()=>evaluate(`document.querySelector('#update-status')?.textContent==='Live updates active'`),'did not reconnect');
 await pause(1500);
 await fetch(origin+'/test/update/85',{method:'POST'});
 await until(()=>evaluate(`document.querySelector('#detail-main').innerText.includes('85.0%')`),'update after restart failed');
 console.log('PASS reconnect and fresh update after server restart');
 console.log('document retained:',await evaluate(`window.testDocumentMarker==='unchanged'`));
 await fetch(origin+'/test/update/100',{method:'POST'});
 await until(()=>evaluate(`document.querySelector('#detail-main').innerText.toLowerCase().includes('ready to watch')`),'status did not update');
 console.log('PASS status changed to Ready to Watch without reload');
 await call('browsingContext.navigate',{context,url:origin+'/request/2',wait:'complete'});
 await until(()=>evaluate(`document.querySelector('#update-status')?.textContent==='Live updates active'`),'TV SSE connect');
 await until(()=>evaluate(`document.querySelector('[data-episode-summary]').textContent.includes('2/5 downloaded · 1/5 ready')`),'initial TV counts');
 if(!await evaluate(`document.querySelector('[data-episode="2-3"]').innerText.includes('37%') && document.querySelector('[data-episode="2-4"]').innerText.toLowerCase().includes('progress unknown') && !document.querySelector('[data-episode="1-1"]')`))throw Error('Episode percentages/scoping');
 await fetch(origin+'/test/episode-update',{method:'POST'});
 await until(()=>evaluate(`document.querySelector('[data-episode-summary]').textContent.includes('3/5 downloaded · 1/5 ready')`),'TV counts after SSE');
 console.log('PASS season counts, known/unknown per-file progress and episode SSE');
 for (const width of [320,390,768,1440,2048]) {
  await call('browsingContext.setViewport',{context,viewport:{width,height:900}});
  if(await evaluate(`document.documentElement.scrollWidth>innerWidth`))throw Error(`Horizontal overflow at ${width}px`);
  if(!await evaluate(`(()=>{const el=document.querySelector('.postercard');const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})()`))throw Error(`Poster overflow at ${width}px`);
  console.log(`PASS realistic detail layout at ${width}px`);
 }
 await call('browsingContext.setViewport',{context,viewport:{width:390,height:844}});
 await call('browsingContext.reload',{context,wait:'complete'});
 await until(()=>evaluate(`document.querySelector('[data-episode-summary]').textContent.includes('3/5 downloaded · 1/5 ready')`),'saved TV progress after reload');
 console.log('PASS saved episode progress after reload');
 await call('browsingContext.navigate',{context,url:origin+'/',wait:'complete'});
 await until(()=>evaluate(`document.body.innerText.includes('3/5 downloaded · 1/5 ready')`),'card counters');
 console.log('PASS card counters match detail');
 await call('browsingContext.navigate',{context,url:origin+'/history',wait:'complete'});
 if(await evaluate(`document.querySelector('#user-filter').innerText.includes('Library Sync')`))throw Error('System source listed as person');
 await evaluate(`document.querySelector('#source-filter').value='library'; document.querySelector('#source-filter').dispatchEvent(new Event('change'));`);
 await until(()=>evaluate(`location.search.includes('source=library') && document.querySelector('#user-filter').disabled`),'library source filter');
 if(!await evaluate(`document.body.innerText.includes('1 history item') && document.querySelector('.tabs').innerText.includes('READY (1)')`))throw Error('Filtered counts');
 await evaluate(`document.querySelector('.tabs a.st-failed').click()`);
 await until(()=>evaluate(`document.body.innerText.includes('No matching history')`),'empty filtered history');
 if(!await evaluate(`location.search.includes('source=library')`))throw Error('Tab lost source');
 await evaluate(`document.querySelector('.tabs a').click()`);
 await until(()=>evaluate(`document.body.innerText.includes('1 history item')`),'all state tab');
 for(const expected of ['1','0']) {
  await evaluate(`document.querySelector('#sync-library-btn').click(); document.querySelector('[onclick="startSync()"]').click();`);
  await until(()=>evaluate(`!document.querySelector('#sync-results').classList.contains('hidden')`),'sync results');
  if(await evaluate(`document.querySelector('#sync-updated').textContent`)!==expected)throw Error('Incorrect repaired count');
  if(await evaluate(`document.querySelector('#sync-added').textContent`)!=='0')throw Error('Duplicate import');
  await evaluate(`window.syncRefreshMarker=true; document.querySelector('[onclick="closeSyncAndRefresh()"]').click()`);
  await until(()=>evaluate(`!window.syncRefreshMarker && !!document.querySelector('#sync-library-btn')`),'sync refresh');
 }
 for(const width of [320,390,768,1440]) {
  await call('browsingContext.setViewport',{context,viewport:{width,height:900}});
  if(await evaluate(`document.documentElement.scrollWidth>innerWidth`))throw Error(`History overflow at ${width}`);
 }
 console.log('PASS History filters/counts/tab retention/empty state, admin sync repair and repeat sync, mobile layout');
 const shot=await call('browsingContext.captureScreenshot',{context});fs.writeFileSync(new URL('./result.png',import.meta.url),Buffer.from(shot.data,'base64'));
}catch(e){console.error('FAIL',e.message); if(ws&&context)console.log('Overflow',await evaluate(`JSON.stringify([...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,right:Math.round(e.getBoundingClientRect().right),width:Math.round(e.getBoundingClientRect().width)})).slice(0,15))`).catch(()=>''));if(ws&&context)console.log('PAGE',await evaluate('document.body.innerText').catch(()=>''));process.exitCode=1;}
finally{ws?.close();firefox.kill(); await new Promise(r=>firefox.once('exit',r)); fs.rmSync(profile,{recursive:true,force:true});}
