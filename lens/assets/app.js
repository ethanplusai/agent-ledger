'use strict';
// Log strings enter textContent only. No HTML interpolation, eval, or remote resources.
const $ = id => document.getElementById(id);
let token = location.hash.slice(1) || sessionStorage.getItem('lens-token') || '';
if (token) sessionStorage.setItem('lens-token', token);
history.replaceState(null, '', location.pathname);
const state = {session: '', selected: null, responses: [], boundaries: [], sessionOffset: 0, responseOffset: 0, evidenceOffset: 0, diagnosticOffset: 0, activityOffset: 0, legacyOffset: 0, conversationOffset: 0, revision: 0};
const number = v => v == null ? 'Unavailable' : Number(v).toLocaleString(undefined, {maximumFractionDigits: 0});
const compact = v => v == null ? '—' : Number(v).toLocaleString(undefined, {notation: 'compact', maximumFractionDigits: 1});
const credits = (v,precision=4) => v == null ? 'Unavailable' : Number(v).toLocaleString(undefined, {maximumFractionDigits: precision});
const el = (tag, text, cls) => {const node = document.createElement(tag); if (text != null) node.textContent = text; if (cls) node.className = cls; return node;};
const clear = id => $(id).replaceChildren();
function status(message, error=false) {$('status').textContent = message; $('status').className = error ? 'error' : '';}
const modelName = model => ({'gpt-6-astra':'Astra','gpt-5.6-sol':'Sol','gpt-5.6-terra':'Terra','gpt-5.6-luna':'Luna'}[model] || model || 'Unknown model');
const timeLabel = timestamp => timestamp ? timestamp.slice(11,19)+' UTC' : 'Time unavailable';
function guarded(fn) {return (...args) => {try{return Promise.resolve(fn(...args)).catch(e=>status(e.message,true));}catch(e){status(e.message,true);}};}
async function api(route, args={}, method='GET') {
  const query = new URLSearchParams(Object.entries(args).filter(([,v]) => v !== '' && v != null));
  const response = await fetch('/api/'+route+(query.size?'?'+query:''), {method, headers: {'X-Lens-Token': token}, cache: 'no-store'});
  const data = await response.json();
  if (!response.ok || data.error) throw new Error(data.error || 'Local report request failed');
  return data;
}
function filters() {return {from:$('from').value,to:$('to').value,project:$('project').value,model:$('model').value,agent:$('agent').value,sort:$('sort').value};}
const agentName = provider => provider === 'anthropic' ? 'Claude Code' : 'Codex';
// Distinct recorded tools must keep distinct labels; two agents both run a terminal.
const toolName = tool => tool === 'functions.exec_command' ? 'Terminal' : tool === 'shell' ? 'Shell'
  : tool === 'read' ? 'Read file' : tool || 'Unknown tool';
function scope() {return {...filters(),session:state.session,turn:$('turn').value,descendants:$('descendants').checked?'1':''};}
function option(select, label, value) {const o = el('option', label); o.value=value; select.append(o);}
function metrics(t) {
  clear('metrics');clear('usage-explanation');
  $('usage-explanation').append(el('h2','What used your tokens?'));
  $('usage-explanation').append(el('p',t.total ? `${Math.round(t.input/t.total*100)}% was input sent to the model (${compact(t.input)} tokens); ${compact(t.output)} was generated output. Every response can send earlier conversation and tool results again.` : 'No recorded usage matches these filters.'));
  $('usage-explanation').append(el('p',t.cached==null ? 'The cache breakdown is incomplete. Token volume does not establish your account usage or charges.' : `${compact(t.cached)} input tokens were read from cache. Cached tokens still appear in token totals; their credit rate can be lower. These totals do not show your subscription allowance.`, 'small muted'));

  if(t.credit_components&&Number(t.credits)>0){
    const [kind,value]=Object.entries(t.credit_components).sort((a,b)=>Number(b[1])-Number(a[1]))[0];
    const names={uncached_input:'Uncached input',cached_input:'Cached input',output:'Generated output'};
    $('usage-explanation').append(el('p',`${names[kind]} accounts for ${Math.round(Number(value)/Number(t.credits)*100)}% of ${t.unpriced?'the available':'the'} estimated credits (${credits(value,2)} of ${credits(t.credits,2)}).${t.unpriced?' Unpriced records are excluded from this comparison.':''}`));
  }
  const values = [
    ['Recorded tokens', compact(t.total), compact(t.input)+' input · '+compact(t.output)+' output'],
    ['Estimated credits', credits(t.credits,2), t.credit_status === 'partial' ? 'Partial · '+t.unpriced+' unpriced records' : 'Published-rate reference'],
    ['Cached input', t.cache_share == null ? '—' : (t.cache_share*100).toFixed(1)+'%', 'Share of recorded input'],
    ['Responses', number(t.responses), t.legacy ? t.legacy+' additional legacy amounts' : 'Unique recorded responses']
  ];
  for (const [label,value,note] of values) {
    const metric = el('div',null,'metric');
    metric.append(el('div',label,'metric-label'),el('div',value,'metric-value'),el('div',note,'metric-note'));
    $('metrics').append(metric);
  }
  $('scope-note').textContent = ($('from').value || 'Earliest')+' to '+($('to').value || 'latest')+' UTC. Totals count each native response once across sessions. Copied session history can overlap. '+(t.invalid?t.invalid+' invalid or conflicting records excluded. ':'')+'Credits are rate references, not account charges. Unknown speed uses a Standard-rate assumption. Legacy amounts have no reliable model attribution.';
  $('astra').setAttribute('aria-pressed',String($('model').value==='gpt-6-astra'));
}
function renderProviders(data) {
  clear('providers');
  const rows=data.providers.filter(p=>p.totals.records);
  // One agent alone is not a comparison; the totals above already describe it.
  if(rows.length<2){$('agent-compare').hidden=true;return;}
  $('agent-compare').hidden=false;
  const peak=Math.max(1,...rows.map(p=>p.totals.total));
  for(const p of rows){
    const card=el('div',null,'provider');
    card.append(el('div',p.label,'provider-label'),el('div',compact(p.totals.total)+' tokens','provider-value'));
    const bar=el('div',null,'provider-bar'),fill=el('div',null,'fill');
    fill.style.width=Math.round(p.totals.total/peak*100)+'%';bar.append(fill);card.append(bar);
    const share=data.totals.total?Math.round(p.totals.total/data.totals.total*100):0;
    card.append(el('div',share+'% of recorded tokens · '+number(p.sessions)+' sessions · '+number(p.totals.responses)+' responses','provider-note'));
    card.append(el('div',p.totals.credits==null?'No verified credit rate for this agent':credits(p.totals.credits,2)+' estimated credits','provider-note'));
    card.append(el('div',p.results?number(p.failures)+' of '+number(p.results)+' observed tool results failed':'No linked tool results','provider-note'));
    $('providers').append(card);
  }
  $('provider-note').textContent=data.notice;
}
async function overview(focus='') {
  const revision=++state.revision;
  status('Reading filtered history…');
  const [data,providers]=await Promise.all([api('overview',{...filters(),offset:state.sessionOffset,focus}),api('providers',filters())]);
  if (revision!==state.revision)return;
  renderProviders(providers);
  state.sessionOffset=data.offset;metrics(data.totals); clear('sessions'); $('session-count').textContent=data.count;
  for (const s of data.sessions) {
    const b=el('button',null,'session'); b.dataset.session=s.sid; b.setAttribute('aria-pressed',String(s.sid===state.session));
    b.append(el('div',s.title || s.project.split(/[\\/]/).pop()+' · '+s.first.slice(0,10),'session-title'));
    b.title=s.project;
    b.append(el('div',s.models.map(modelName).join(', ')+' · '+s.last.slice(0,10),'session-meta'));
    const n=el('div',null,'session-numbers');n.append(el('strong',s.totals.credits==null?'Unpriced':credits(s.totals.credits,2)+' cr'),el('span',compact(s.totals.total)+' tokens'));b.append(n);
    if(s.parent)b.append(el('div','Child session','session-meta'));
    if(s.diagnostics||s.totals.unpriced||s.totals.legacy)b.append(el('div',s.diagnostics?s.diagnostics+' coverage notes':'Partial estimate','session-status'));
    b.addEventListener('click',guarded(async()=>{state.session=s.sid;state.responseOffset=0;$('turn').value='';await openSession(s);document.querySelectorAll('.session').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));}));
    $('sessions').append(b);
  }
  $('sessions-prev').disabled=state.sessionOffset===0; $('sessions-next').disabled=state.sessionOffset+50>=data.count;
  if(!data.sessions.length){$('sessions').append(el('p','No usage in this range. Try All dates, change a filter, or run report.py --demo.','empty'));resetSession();}
  else {const selected=data.sessions.find(s=>s.sid===state.session) || data.sessions[0];if(state.session!==selected.sid){state.responseOffset=0;$('turn').value='';}state.session=selected.sid;document.querySelectorAll('.session').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.session===state.session)));await openSession(selected);}
  status('Local history ready');
}
function resetSession(){state.session='';state.responses=[];state.boundaries=[];state.selected=null;state.conversationSession=null;$('session-title').textContent='No session selected';$('session-project').textContent='';for(const id of ['chart','context-summary','context-readout','context-rows','detail','evidence','findings','session-totals','all-activity','legacy-amounts','diagnostics','finding-count','diagnostic-count','session-coverage','response-page','conversation','conversation-summary','conversation-page','tool-rows','tool-metrics','tool-count','tools-note','conversation-note'])clear(id);clear('turn');option($('turn'),'Whole session','');clear('response');option($('response'),'No responses','');for(const id of ['evidence-more','activity-more','legacy-more','diagnostics-more'])$(id).hidden=true;}
async function openSession(session) {
  if(session){$('session-title').textContent=session.title||'Session · '+session.first.slice(0,10);$('session-project').textContent=session.project+(session.parent?' · Parent: '+session.parent+' · '+(session.relationship||'relationship unspecified'):'');}
  const selectedScope=JSON.stringify(scope());
  const [data, findings, diagnostics]=await Promise.all([api('session',{...scope(),offset:state.responseOffset}),api('findings',scope()),api('diagnostics',{session:state.session})]);
  if(selectedScope!==JSON.stringify(scope()))return;
  state.responses=data.responses;
  state.boundaries=data.boundaries||[];
  renderContext(data);
  const turn=$('turn').value; clear('turn'); option($('turn'),'Whole session',''); data.turns.forEach((t,i)=>{option($('turn'),'Task '+(i+1)+' · '+t.records+' records',t.turn);$('turn').lastElementChild.title=t.turn;});$('turn').value=turn;
  $('session-coverage').textContent=data.totals.legacy||data.totals.invalid?'Partial coverage':'';
  $('session-totals').textContent=compact(data.totals.total)+' tokens · '+credits(data.totals.credits,2)+' estimated credits'+(data.totals.unpriced?' (partial)':'')+' · '+data.totals.responses+' responses'+(data.totals.legacy?' · '+data.totals.legacy+' legacy amounts excluded from response chart':'');
  clear('response'); for(let i=0;i<data.responses.length;i++){const r=data.responses[i];option($('response'),'#'+(data.offset+i+1)+' · '+modelName(r.model)+' · '+compact(r.usage.displayed_total)+' tokens',r.id);}
  $('responses-prev').disabled=data.offset===0;$('responses-next').disabled=data.offset+100>=data.count;$('response-page').textContent=data.count?(data.offset+1)+'–'+Math.min(data.offset+100,data.count)+' / '+data.count:'0 responses';
  drawChart();renderFindings(findings);renderDiagnostics(diagnostics,false);
  state.activityOffset=state.legacyOffset=0;clear('all-activity');clear('legacy-amounts');if(!$('view-activity').hidden)await loadActivity(false);
  if(!$('view-tools').hidden)await loadTools();
  if(!$('view-conversation').hidden)await loadConversation();
  if(data.responses.length)await selectResponse(data.responses.some(r=>r.id===state.selected)?state.selected:data.responses[0].id);
  else {clear('detail');clear('evidence');$('detail').append(el('p','This scope has no attributable native responses. Legacy amounts remain in the session totals.','notice'));}
}
const svgNS='http://www.w3.org/2000/svg';
function svgEl(tag,attrs,text){const n=document.createElementNS(svgNS,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!=null)n.textContent=text;return n;}
function drawChart(){
  clear('chart');const rs=state.responses;if(!rs.length)return;
  const credit=$('measure').value==='credits',context=$('measure').value==='context';
  document.querySelectorAll('.legend span').forEach((n,i)=>n.hidden=context&&i>1);
  const parts=rs.map(r=>credit?r.estimate.parts?.map(Number):r.usage.errors.length?null:[r.usage.uncached_input,r.usage.cached_input_tokens,context?0:r.usage.reasoning_output_tokens??0,context?0:r.usage.other_output??r.usage.output_tokens]);
  if(context)rs.forEach((r,i)=>{if(!r.usage.errors.length&&r.usage.cached_input_tokens==null)parts[i]=[r.usage.input_tokens,0,0,0];});
  const sums=parts.map(p=>p&&p.every(x=>x!=null)?p.reduce((a,b)=>a+b,0):null);const max=Math.max(1,...sums.filter(x=>x!=null));
  const width=Math.max(270,Math.round($('chart').clientWidth)), height=Math.round($('chart').clientHeight), top=14, bottom=height-26, left=40, plot=width-left-8;
  const svg=svgEl('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':credit?'Estimated credits by response':context?'Context sent per response':'Recorded tokens by response'});
  const step=plot/rs.length;
  for(let i=0;i<=2;i++){const y=bottom-(bottom-top)*i/2;svg.append(svgEl('line',{x1:left,x2:width-8,y1:y,y2:y,class:'gridline'}),svgEl('text',{x:left-7,y:y+3,'text-anchor':'end',class:'axis-text'},compact(max*i/2)));}
  rs.forEach((r,i)=>{const x=left+i*step+step*.17;let y=bottom;const g=svgEl('g',{class:'bar'+(r.id===state.selected?' selected':''),'data-id':r.id,tabindex:0,role:'button','aria-label':`Response ${state.responseOffset+i+1}, ${sums[i]==null?'breakdown unavailable':credit?credits(sums[i])+' credits':number(sums[i])+(context?' context tokens; '+number(r.usage.cached_input_tokens)+' cached; change '+contextChange(r.context.change):' tokens')}`});
    if(sums[i]==null){g.append(svgEl('rect',{x,y:bottom-8,width:step*.66,height:8,class:'unavailable'}));}
    else parts[i].forEach((v,j)=>{const h=v/max*(bottom-top);y-=h;g.append(svgEl('rect',{x,y,width:step*.66,height:h,class:context&&r.usage.cached_input_tokens==null?'unavailable':['uncached','cached','reasoning','other'][j]}));});
    // A transparent hit target makes very small/zero responses selectable.
    g.append(svgEl('rect',{x,y:top,width:step*.66,height:bottom-top,fill:'transparent',stroke:'none'}));
    g.append(svgEl('line',{x1:x,x2:x+step*.66,y1:bottom+4,y2:bottom+4,class:'selection-line'}));
    g.append(svgEl('title',{},`Response ${state.responseOffset+i+1}: ${r.model||'unknown'} · ${number(r.usage.input_tokens)} context tokens · ${number(r.usage.cached_input_tokens)} cached · ${number(r.usage.output_tokens)} output tokens`));
    g.addEventListener('click',guarded(async()=>{await setTab('response');await selectResponse(r.id);}));g.addEventListener('keydown',guarded(e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();return setTab('response').then(()=>selectResponse(r.id));}}));svg.append(g);
    const stride=Math.max(1,Math.ceil(rs.length/(width/35)));
    if(i===0||i===rs.length-1||(i%stride===0&&i<rs.length-stride))svg.append(svgEl('text',{x:x+step*.33,y:height-7,'text-anchor':'middle',class:'axis-text'},state.responseOffset+i+1));
  });
  // A recorded compaction marks where the agent's context was reset, which is what a drop in the next bar follows.
  const resets=new Set();
  for(const b of state.boundaries){const i=rs.findIndex(r=>r.source===b.source&&r.offset>=b.offset);if(i>0)resets.add(i);}
  for(const i of resets){const x=left+i*step;
    svg.append(svgEl('line',{x1:x,x2:x,y1:top,y2:bottom,class:'compaction'}));
    svg.append(svgEl('text',{x:x+4,y:top+8,class:'compaction-text'},'context reset'));
  }
  $('chart').append(svg);$('chart-note').textContent=(sums.some(x=>x==null)?'Gray marks: unavailable breakdown. ':'')+(context&&rs.some(r=>!r.usage.errors.length&&r.usage.cached_input_tokens==null)?'Gray bars: input known, cache split unavailable. ':'')+(resets.size?'Dashed line: a recorded compaction reset the context here. ':'')+(credit?'Per-response rate estimates; not account charges.':context?'Height = input sent with this response, including cached context. This is not cumulative usage. Select a bar to see the change.':'Input includes reprocessed context. Unsplit output uses Other output.');
}
function contextChange(v){return v==null?'No baseline':(v>0?'+':'')+number(v);}
function renderContextReadout(r){
  clear('context-readout');if(!r)return;
  const c=r.context;
  $('context-readout').append(el('strong',`Context sent: ${number(c.input)} tokens`),el('span',`Change: ${contextChange(c.change)} · Cached: ${number(r.usage.cached_input_tokens)} · Output: ${number(r.usage.output_tokens)}`));
  $('context-readout').append(el('span',c.limit_share==null?'Context limit not recorded':`${(c.limit_share*100).toFixed(1)}% of the recorded ${number(r.context_limit)} token limit`,'small muted'));
}
function renderContext(data){
  clear('context-summary');clear('context-rows');clear('context-readout');
  const c=data.context_summary;
  $('context-summary').append(el('h3','Context adds up with every response'));
  $('context-summary').append(el('p',c.count?`${compact(c.average)} average input tokens × ${number(c.count)} valid responses in this selection. Peak context sent: ${compact(c.peak)} tokens.`:'No valid per-response context counts in this selection.'));
  const links=el('div',null,'largest-responses');links.append(el('span','Largest responses by total tokens: '));
  for(const r of data.largest){const b=el('button',`${compact(r.usage.displayed_total)} · ${modelName(r.model)}`);b.addEventListener('click',guarded(async()=>{const found=await api('locate',{...scope(),id:r.id});state.responseOffset=found.offset;state.selected=found.id;await openSession();await setTab('response');}));links.append(b);}
  if(data.largest.length)$('context-summary').append(links);
  for(const [i,r] of data.responses.entries()){
    const tr=el('tr');tr.dataset.id=r.id;const td=el('td');const b=el('button','#'+(data.offset+i+1));b.addEventListener('click',guarded(async()=>{await setTab('response');await selectResponse(r.id);}));td.append(b);tr.append(td);
    for(const text of [number(r.context.input),contextChange(r.context.change),number(r.usage.cached_input_tokens),number(r.usage.output_tokens),r.context.limit_share==null?'Unavailable':(r.context.limit_share*100).toFixed(1)+'%'])tr.append(el('td',text));
    $('context-rows').append(tr);
  }
}
function addCount(dl,label,value,total=false){dl.append(el('dt',label,total?'total-label':''),el('dd',number(value),total?'total-value':''));}
async function selectResponse(id) {
  state.selected=Number(id);
  state.evidenceOffset=0;
  $('response').value=id;
  renderContextReadout(state.responses.find(r=>r.id===Number(id)));
  document.querySelectorAll('#context-rows tr').forEach(n=>n.classList.toggle('selected-row',n.dataset.id===String(id)));
  document.querySelectorAll('.bar').forEach(n=>n.classList.toggle('selected',n.dataset.id===String(id)));
  const data=await api('detail',{id});
  if(state.selected!==Number(id))return;
  const r=data.response,u=r.usage;
  clear('detail');
  $('detail').append(el('h3',modelName(r.model),'response-name'),el('p',timeLabel(r.timestamp)+' · '+r.kind+' usage','response-meta'));
  if(u.errors.length)$('detail').append(el('p',u.errors.join('; '),'notice'));
  const dl=el('dl',null,'counts');
  for(const[label,key]of [['Input','input_tokens'],['Uncached input','uncached_input'],['Cached input','cached_input_tokens'],['Output','output_tokens'],['Reasoning output','reasoning_output_tokens'],['Other output','other_output']])addCount(dl,label,u[key]);
  addCount(dl,'Total tokens',u.displayed_total,true);
  $('detail').append(dl);

  const estimate=el('div',null,'estimate');
  estimate.append(el('strong',r.estimate.total==null?'Credit estimate unavailable':credits(r.estimate.total)+' estimated credits'));
  estimate.append(el('p',r.estimate.reason||r.estimate.assumption));
  const assumptions=el('details');
  assumptions.append(el('summary','Rates & assumptions'));
  if(r.estimate.parts)assumptions.append(el('p',r.estimate.parts.map((v,i)=>['Uncached','Cached','Reasoning','Other'][i]+' '+credits(v)).join(' · ')));
  assumptions.append(el('p','Snapshot '+r.estimate.date+'. '+r.estimate.basis+'. API-authenticated work has separate billing.'));
  const link=el('a','Published rates');
  link.href=r.estimate.source;link.target='_blank';link.rel='noreferrer noopener';
  assumptions.append(link);estimate.append(assumptions);$('detail').append(estimate);

  $('detail').append(el('p','Input cache split · '+number(u.input_tokens)+' input tokens','context-label'));
  const meter=el('div',null,'context-meter');
  if(u.uncached_input!=null&&u.cached_input_tokens!=null){
    const uncached=el('div',null,'uncached'),cached=el('div',null,'cached');
    uncached.style.flex=String(u.uncached_input);cached.style.flex=String(u.cached_input_tokens);
    meter.append(uncached,cached);
  }
  $('detail').append(meter);
  const provenance=el('details',null,'activity provenance');
  provenance.append(el('summary','Source details · '+data.provenance.length+' appearances'));
  provenance.append(el('p','Model: '+(r.model||'unavailable')+' · '+r.timestamp,'small muted'));
  provenance.append(el('p','Turn: '+r.turn+' · cache writes: '+number(u.cache_write_input_tokens)+' (input metadata)','small muted'));
  provenance.append(el('p',r.context_limit?'Context limit is recorded; the meter shows the cached and uncached share of input.':'Context limit unavailable; the meter shows the cached and uncached share of input.','small muted'));
  for(const p of data.provenance)provenance.append(el('p','Source '+p.source+' · byte '+p.offset+' · '+p.sid+(p.inherited?' · inherited / owner '+p.owner:''),'small muted'));
  $('detail').append(provenance);
  if(data.message){const b=el('button','Read conversation near this response');b.addEventListener('click',guarded(()=>readCitation(data.message)));$('detail').append(b);}
  renderEvidence(data,false);
}
function activityNode(a) {
  const details=el('details',null,'activity'),summary=el('summary');
  const tool=a.kind==='boundary'?'Compaction':a.tool?.endsWith('exec_command')?'Terminal':a.tool||'Unknown tool';
  summary.append(el('strong',tool),el('span',compact(a.bytes)+' B','activity-size'));
  if(a.failed)summary.append(el('span','failed','activity-failed'));
  summary.append(el('span',a.action?.slice(0,180)||'Generic activity','activity-action'));
  details.append(summary);
  details.append(el('p',number(a.bytes)+' bytes · '+number(a.chars)+' characters'+(a.truncated?' · bounded or truncated preview':'')+' · '+a.association,'activity-meta'));
  if(a.operations&&a.operations!=='[]'){
    let operations=[];try{operations=JSON.parse(a.operations);}catch{}
    details.append(el('p','Operations: '+operations.join(', ')+'. Credits are not allocated to individual operations.','small muted'));
  }
  details.append(el('pre',a.preview||'(No observed text preview)'));
  details.append(el('p',a.tool+' · '+a.timestamp+' · source '+a.source+' · byte '+a.offset+' · compaction segment '+a.boundary,'small muted'));
  return details;
}
function renderEvidence(data,append){if(!append)clear('evidence');for(const a of data.activities)$('evidence').append(activityNode(a));if(!data.activities.length&&!append)$('evidence').append(el('p','No preceding tool results linked to this response. Unassociated results are in Activity.','small muted'));$('evidence-more').hidden=data.offset+50>=data.count;}
function findingButton(label,fn){const b=el('button',label);b.addEventListener('click',guarded(fn));return b;}
async function showActivity(id){await setTab('response');const data=await api('activity',{activity:id});for(const a of data.activities){if(a.following_id)await showFindingResponse(a.following_id,false);const n=activityNode(a);n.open=true;$('evidence').replaceChildren(n);}$('evidence').scrollIntoView({behavior:'smooth',block:'nearest'});}
async function showFindingResponse(id,scroll=true){await setTab('response');const target=await api('locate',{...scope(),id});if(state.responseOffset!==target.offset){state.responseOffset=target.offset;await openSession();}await selectResponse(target.id);if(scroll)$('detail').scrollIntoView({behavior:'smooth',block:'nearest'});}
function renderFindings(data){clear('findings');$('finding-count').textContent=data.largest.length+data.repeated.length+data.jumps.length+data.reasoning.length;
  const large=el('div',null,'finding-group');large.append(el('h3','Large tool results'));for(const a of data.largest.slice(0,5)){const row=el('div',null,'finding');row.append(el('strong',compact(a.bytes)+' observed bytes'),el('p',a.action||a.tool),findingButton('Inspect result',()=>showActivity(a.id)));if(a.following_id)row.append(findingButton('Following response',()=>showFindingResponse(a.following_id)));large.append(row);}$('findings').append(large);
  const repeats=el('div',null,'finding-group');repeats.append(el('h3','Repeated observed content & failures'));if(!data.repeated.length)repeats.append(el('p','No safely recognized exact repeats in this scope.','small muted'));for(const r of data.repeated.slice(0,6)){const row=el('div',null,'finding');row.append(el('strong',r.category+' · '+r.occurrences+' occurrences'),el('p',r.action),el('p','Exact recognized action + observed output hash. '+r.first+' → '+r.last+(r.first_boundary!==r.last_boundary?' · crosses compaction':'')+(r.truncated?' · truncated output does not establish unchanged full content.':'')));for(const a of r.evidence.slice(0,5))row.append(findingButton('Evidence '+a.timestamp.slice(11,19),()=>showActivity(a.id)));repeats.append(row);}$('findings').append(repeats);
  for(const [title,rows,field,prefix]of[['Largest recorded context jumps',data.jumps,'jump','+'],['Most recorded reasoning output',data.reasoning,'reasoning','']]){const group=el('div',null,'finding-group');group.append(el('h3',title));for(const r of rows.slice(0,4)){const row=el('div',null,'finding');row.append(el('strong',prefix+number(r[field])+' tokens'),el('p',r.timestamp),findingButton('Inspect response',()=>showFindingResponse(r.id)));group.append(row);}$('findings').append(group);}
}
function renderDiagnostics(data,append){if(!append){clear('diagnostics');state.diagnosticOffset=0;}$('diagnostic-count').textContent=data.count||'';for(const d of data.items)$('diagnostics').append(el('p',d.code+' · source '+d.source+' · byte '+d.offset+' — '+d.message,'diagnostic'));$('diagnostics-more').hidden=state.diagnosticOffset+50>=data.count;}
async function loadActivity(append){
  if(!state.session)return;
  const [activity,legacy]=await Promise.all([api('activity',{session:state.session,turn:$('turn').value,offset:state.activityOffset}),api('legacy',{...scope(),offset:state.legacyOffset})]);
  if(!append){clear('all-activity');clear('legacy-amounts');}
  for(const a of activity.activities)$('all-activity').append(activityNode(a));
  for(const r of legacy.items){const d=el('details',null,'activity');d.append(el('summary',r.kind+' · '+number(r.usage.displayed_total)+' tokens'),el('p',r.timestamp+' · source '+r.source+' · byte '+r.offset+' · '+(r.model||'Model unavailable'),'small muted'),el('p','Observed cumulative amount; timing and response attribution are unavailable. '+credits(r.estimate.total)+' reference credits.','notice'));const dl=el('dl',null,'counts');for(const [label,key]of[['Input','input_tokens'],['Cached input','cached_input_tokens'],['Output','output_tokens'],['Reasoning','reasoning_output_tokens']])addCount(dl,label,r.usage[key]);d.append(dl);$('legacy-amounts').append(d);}
  if(!legacy.count)$('legacy-amounts').append(el('p','No legacy amounts in this filtered scope.','small muted'));
  $('activity-more').hidden=state.activityOffset+50>=activity.count;$('legacy-more').hidden=state.legacyOffset+50>=legacy.count;
}
function renderTools(data) {
  clear('tool-metrics');clear('tool-rows');
  const t=data.totals;
  $('tool-count').textContent=t.results||'';
  const values=[
    ['Tool results',number(t.results),t.tools+(t.tools===1?' distinct tool':' distinct tools')],
    ['Failed results',number(t.failures),t.failure_rate==null?'No observed results':(t.failure_rate*100).toFixed(1)+'% of observed results'],
    ['Text returned',compact(t.bytes)+' B','Observed bytes, not billed tokens'],
    ['Largest result',compact(t.largest)+' B','Single observed result']
  ];
  for(const [label,value,note] of values){
    const metric=el('div',null,'metric');
    metric.append(el('div',label,'metric-label'),el('div',value,'metric-value'),el('div',note,'metric-note'));
    $('tool-metrics').append(metric);
  }
  const peak=Math.max(1,...data.items.map(r=>r.results));
  for(const r of data.items){
    const tr=el('tr'),first=el('td');
    const bar=el('div',null,'tool-bar'),fill=el('div',null,'fill');
    fill.style.width=Math.round(r.results/peak*100)+'%';bar.append(fill);
    first.append(el('div',toolName(r.tool),'tool-name'),bar);
    const failed=el('td',number(r.failures));
    if(r.failures)failed.className='tool-failed';
    tr.append(first,el('td',number(r.results)),failed,
              el('td',r.failure_rate==null?'—':(r.failure_rate*100).toFixed(1)+'%'),
              el('td',compact(r.bytes)),el('td',compact(r.largest)));
    $('tool-rows').append(tr);
  }
  if(!data.items.length){const tr=el('tr'),td=el('td','No tool results linked to a response in this scope.');td.colSpan=6;tr.append(td);$('tool-rows').append(tr);}
  $('tools-note').textContent=data.notice;
}
async function loadTools(){renderTools(await api('tools',$('tools-all').checked?filters():scope()));}
function renderTranscript(data) {
  clear('conversation');
  $('conversation-summary').textContent=data.count
    ? `${number(data.count)} recorded messages · ${compact(data.recorded)} tokens across this session. The running total follows the conversation.`
    : 'No recorded conversation text for this session. Tool-only sources have no message excerpts.';
  const peak=Math.max(1,data.peak);
  for(const m of data.items){
    const row=el('article',null,'turn turn-'+m.role);
    const head=el('div',null,'turn-head');
    head.append(el('h4',m.role==='user'?'You':'Assistant'),el('span',m.timestamp?m.timestamp.slice(0,10)+' '+m.timestamp.slice(11,19)+' UTC':'Time unavailable','turn-time'));
    if(m.models.length)head.append(el('span',m.models.map(modelName).join(', '),'turn-time'));
    row.append(head,el('pre',m.text||'(No recorded text)'));
    if(m.clipped)row.append(el('p','Excerpt clipped; open the source to read the rest.','section-note'));
    const cost=el('div',null,'turn-cost'),bar=el('div',null,'turn-bar'),fill=el('div',null,'fill');
    // Linear against the session peak, so one dominant turn still reads as dominant. A recorded but
    // tiny turn keeps a sliver of width so it stays visible; the exact count is printed beside it.
    fill.style.width=(m.total?Math.max(.7,m.total/peak*100):0).toFixed(2)+'%';bar.append(fill);
    const facts=el('div',null,'turn-facts');
    facts.append(el('span',m.total?number(m.total)+' tokens here':'No usage recorded here','turn-here'));
    facts.append(el('span','Running total '+compact(m.cumulative),'turn-running'));
    if(m.calls)facts.append(el('span',m.calls+(m.calls===1?' tool call':' tool calls'),'turn-tools'));
    if(m.failures)facts.append(el('span',m.failures+' failed','turn-failed'));
    if(m.compactions)facts.append(el('span','context reset','turn-compact'));
    if(m.credits)facts.append(el('span',credits(m.credits,3)+' cr','turn-running'));
    cost.append(bar,facts);
    row.append(cost);
    const open=el('button','Read in context');
    open.addEventListener('click',guarded(()=>readCitation(m.citation)));
    row.append(open);
    $('conversation').append(row);
  }
  $('conversation-page').textContent=data.count?(data.offset+1)+'–'+Math.min(data.offset+data.items.length,data.count)+' / '+data.count:'0 messages';
  $('conversation-prev').disabled=data.offset===0;
  $('conversation-next').disabled=data.offset+data.items.length>=data.count;
  $('conversation-note').textContent=data.notice;
}
async function loadConversation() {
  if(!state.session){clear('conversation');$('conversation-summary').textContent='Select a session to replay its recorded conversation.';return;}
  if(state.conversationSession!==state.session){state.conversationSession=state.session;state.conversationOffset=0;}
  renderTranscript(await api('transcript',{session:state.session,offset:state.conversationOffset}));
}
async function setTab(name) {
  for(const button of document.querySelectorAll('[role="tab"]')) {
    const selected=button.id==='tab-'+name;
    button.setAttribute('aria-selected',String(selected));
    button.tabIndex=selected?0:-1;
    $(button.getAttribute('aria-controls')).hidden=!selected;
  }
  if(name==='activity') {
    state.activityOffset=state.legacyOffset=0;
    await loadActivity(false);
  }
  if(name==='tools')await loadTools();
  if(name==='conversation')await loadConversation();
}
const tabs=[...document.querySelectorAll('[role="tab"]')];
for(const tab of tabs) {
  tab.addEventListener('click',guarded(()=>setTab(tab.id.replace('tab-',''))));
  tab.addEventListener('keydown',guarded(async event=>{
    const index=tabs.indexOf(tab);
    let next;
    if(event.key==='ArrowRight')next=(index+1)%tabs.length;
    if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;
    if(event.key==='Home')next=0;
    if(event.key==='End')next=tabs.length-1;
    if(next==null)return;
    event.preventDefault();tabs[next].focus();
    await setTab(tabs[next].id.replace('tab-',''));
  }));
}
$('session-toggle').addEventListener('click',()=>{
  const expanded=document.querySelector('.sessions-panel').classList.toggle('expanded');
  $('session-toggle').setAttribute('aria-expanded',String(expanded));
  $('session-toggle').textContent=expanded?'Close':'Browse';
});
let chartWidth=0;
new ResizeObserver(entries=>{
  const width=Math.round(entries[0].contentRect.width);
  if(width!==chartWidth){chartWidth=width;drawChart();}
}).observe($('chart'));
$('activity-more').addEventListener('click',guarded(async()=>{state.activityOffset+=50;const data=await api('activity',{session:state.session,turn:$('turn').value,offset:state.activityOffset});for(const a of data.activities)$('all-activity').append(activityNode(a));$('activity-more').hidden=state.activityOffset+50>=data.count;}));
$('legacy-more').addEventListener('click',guarded(async()=>{state.legacyOffset+=50;const data=await api('legacy',{...scope(),offset:state.legacyOffset});for(const r of data.items)$('legacy-amounts').append(el('p',r.kind+' · '+r.timestamp+' · '+number(r.usage.displayed_total)+' tokens · source '+r.source+' · byte '+r.offset,'diagnostic'));$('legacy-more').hidden=state.legacyOffset+50>=data.count;}));
async function init(){const data=await api('options');for(const p of data.projects)option($('project'),p,p);for(const m of data.models)option($('model'),modelName(m),m);$('from').value=data.from;$('to').value=data.to;$('mode').textContent=data.demo?'Demo data':'Local history';$('coverage').textContent=data.sources+' discovered cached sources · '+data.empty_sources+' without usable usage. '+(data.import.issues||[]).join(' ');}
for(const id of ['from','to','model','agent','sort'])$(id).addEventListener('change',guarded(()=>{state.sessionOffset=state.responseOffset=0;return overview();}));
$('tools-all').addEventListener('change',guarded(loadTools));
for(const [id,delta] of [['conversation-prev',-40],['conversation-next',40]])$(id).addEventListener('click',guarded(()=>{state.conversationOffset=Math.max(0,state.conversationOffset+delta);return loadConversation();}));
$('astra').addEventListener('click',guarded(()=>{if(![...$('model').options].some(o=>o.value==='gpt-6-astra'))option($('model'),'gpt-6-astra','gpt-6-astra');$('model').value='gpt-6-astra';state.sessionOffset=0;return overview();}));
$('all-dates').addEventListener('click',guarded(()=>{$('from').value=$('to').value='';state.sessionOffset=0;return overview();}));
for(const id of ['turn','descendants'])$(id).addEventListener('change',guarded(()=>{state.responseOffset=0;return openSession();}));
$('measure').addEventListener('change',drawChart);$('response').addEventListener('change',guarded(async()=>{await setTab('response');await selectResponse($('response').value);}));
for(const [id,delta]of[['sessions-prev',-50],['sessions-next',50]])$(id).addEventListener('click',guarded(()=>{state.sessionOffset=Math.max(0,state.sessionOffset+delta);return overview();}));
for(const[id,delta]of[['responses-prev',-100],['responses-next',100]])$(id).addEventListener('click',guarded(()=>{state.responseOffset=Math.max(0,state.responseOffset+delta);return openSession();}));
$('evidence-more').addEventListener('click',guarded(async()=>{state.evidenceOffset+=50;renderEvidence(await api('detail',{id:state.selected,offset:state.evidenceOffset}),true);}));
$('diagnostics-more').addEventListener('click',guarded(async()=>{state.diagnosticOffset+=50;renderDiagnostics(await api('diagnostics',{session:state.session,offset:state.diagnosticOffset}),true);}));
$('refresh').addEventListener('click',guarded(async()=>{$('refresh').disabled=true;status('Importing new complete records…');try{await api('refresh',{},'POST');const savedProject=$('project').value,savedModel=$('model').value;const data=await api('options');clear('project');clear('model');option($('project'),'All projects','');option($('model'),'All models','');data.projects.forEach(p=>option($('project'),p,p));data.models.forEach(m=>option($('model'),modelName(m),m));$('project').value=savedProject;$('model').value=savedModel;$('coverage').textContent=data.sources+' cached sources. '+(data.import.issues||[]).join(' ');if(window.refreshWorkspace)await window.refreshWorkspace();else await overview();}finally{$('refresh').disabled=false;}}));
const savedTheme=localStorage.getItem('lens-theme');document.documentElement.dataset.theme=savedTheme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
function themeLabel(){const dark=document.documentElement.dataset.theme==='dark';$('theme').textContent=dark?'Light mode':'Dark mode';$('theme').setAttribute('aria-label',dark?'Switch to light appearance':'Switch to dark appearance');}
themeLabel();
$('theme').addEventListener('click',()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=theme;localStorage.setItem('lens-theme',theme);themeLabel();});
guarded(async()=>{await init();window.dispatchEvent(new Event('ledger-ready'));})();
