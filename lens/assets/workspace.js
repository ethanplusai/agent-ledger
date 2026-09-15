'use strict';
const work={page:'home',searchOffset:0,recentOffset:0,noteOffset:0,revision:0,query:'',config:null};
const projectScope=()=>({project:$('project').value});
function taskButton(label,fn,cls='quiet-button'){const b=el('button',label,cls);b.type='button';b.addEventListener('click',guarded(fn));return b;}
async function copyText(text){try{await navigator.clipboard.writeText(text);status('Copied. Paste it into your agent when useful.');return true;}catch{status('Copy unavailable. Select and copy the displayed text.',true);return false;}}
function page(name){work.page=name;for(const p of ['home','ask','search','notes','usage','connect'])$('page-'+p).hidden=p!==name;for(const b of document.querySelectorAll('[data-page]')){if(b.dataset.page===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}const h=$('page-'+name).querySelector('h1');if(h){h.tabIndex=-1;h.focus({preventScroll:true});}}
async function navigate(name){page(name);if(name==='ask')await showAsk();if(name==='home')await home();if(name==='usage'){await overview();drawChart();}if(name==='notes')await loadNotes();if(name==='connect'){work.config=await api('connection');$('connection-config').textContent=JSON.stringify(work.config,null,2);}}
for(const b of document.querySelectorAll('[data-page]'))b.addEventListener('click',guarded(()=>navigate(b.dataset.page)));
async function inspect(e){page('usage');$('from').value=$('to').value=$('model').value=$('agent').value='';state.session=e.sid;state.responseOffset=0;$('turn').value='';$('descendants').checked=false;await overview(e.sid);state.session=e.sid;await openSession({sid:e.sid,title:e.title,project:e.project,first:''});if(e.response)await showFindingResponse(e.response);if(e.activity)await showActivity(e.activity);status('Showing evidence for the selected finding');}
function renderInsight(item){const n=el('article',null,'insight');n.append(el('h3',item.title),el('p',item.evidence.title||item.evidence.project,'section-note'),el('p',item.observed,'observed'));const d=el('details');d.append(el('summary','Understand this pattern'));d.append(el('p',item.meaning));d.append(el('h4','What to try'),el('p',item.next));const prompt=el('details',null,'prompt');prompt.append(el('summary','A prompt for your next session'),el('pre',item.prompt),taskButton('Copy prompt',()=>copyText(item.prompt)));d.append(prompt);n.append(d,taskButton('Inspect evidence',()=>inspect(item.evidence)));return n;}
function recentRow(s){const n=el('article',null,'recent-row');n.append(el('h3',s.title||'Untitled session'),el('p',(s.provider==='anthropic'?'Claude Code':'Codex')+' · '+(s.last?s.last.slice(0,10):'Date unavailable')+' · '+s.project.split(/[\\/]/).pop(),'muted'));if(s.message)n.append(taskButton('Read conversation',()=>readCitation('message:'+s.message)));n.append(taskButton('Inspect usage',()=>inspect(s)));return n;}
async function home(showReview=false){const revision=++work.revision;status('Reading local work…');const data=await api('home',{...projectScope(),review:showReview?'1':''});if(revision!==work.revision)return;clear('insights');clear('recent');clear('daily');$('usage-review').hidden=!showReview;$('daily-review').hidden=!showReview;document.querySelector('.home-grid').classList.toggle('recent-only',!showReview);await renderBriefing(data,revision);if(revision!==work.revision)return;$('home-summary').textContent=number(data.sessions)+' indexed sessions · '+number(data.messages)+' searchable excerpts across all projects'+(data.refreshed?' · refreshed '+new Date(data.refreshed).toLocaleString():'');for(const item of data.insights.slice(0,4))$('insights').append(renderInsight(item));if(data.insights.length>4){$('insights').append(taskButton('Show more patterns',()=>{const button=$('insights').lastElementChild;button.remove();for(const item of data.insights.slice(4))$('insights').append(renderInsight(item));}));}if(!data.insights.length)$('insights').append(el('p','No supported patterns found in this scope. That does not grade the work. Try recovering a prior decision or inspect a session to understand its recorded usage.','empty'));for(const s of data.recent.items.slice(0,8))$('recent').append(recentRow(s));$('recent-more').hidden=data.recent.items.length<=8&&!data.recent.more;work.recentOffset=0;$('recent-more').onclick=guarded(async()=>{page('search');$('search-query').value='';clear('search-results');$('search-status').textContent='Recent sessions in this project';$('search-more').hidden=true;await recentPage(false);});if(!data.sessions)$('recent').append(el('p','No history found yet. Run ledger.py --demo to explore synthetic examples, or check the configured history directories and click Refresh.','empty'));
const byDay=new Map(data.days.map(d=>[d.day,d]));const max=Math.max(1,...data.days.map(d=>d.tokens));for(let i=365;i>=0;i--){const date=new Date();date.setUTCDate(date.getUTCDate()-i);const key=date.toISOString().slice(0,10);const value=byDay.get(key)?.tokens||0;const b=taskButton('',async()=>{$('from').value=$('to').value=key;state.sessionOffset=0;await navigate('usage');},'day day-'+(value?Math.min(4,1+Math.floor(value/max*3)):0));b.title=key+' · '+number(value)+' recorded tokens';b.setAttribute('aria-label',b.title);$('daily').append(b);}status('Ready. History indexed locally.');}
async function recentPage(append){const data=await api('recent',{...projectScope(),offset:work.recentOffset});if(!append)clear('search-results');for(const s of data.items)$('search-results').append(recentRow(s));$('search-more').hidden=!data.more;$('search-more').onclick=guarded(async()=>{work.recentOffset+=30;await recentPage(true);});}
async function search(append=false){const query=$('search-query').value.trim();if(!query)return;work.query=query;const revision=++work.revision;if(!append){work.searchOffset=0;clear('search-results');$('reader').hidden=true;}$('search-status').textContent='Searching…';try{const data=await api('search',{...projectScope(),q:query,offset:work.searchOffset});if(revision!==work.revision)return;for(const n of data.notes){if(append)break;const row=el('article',null,'search-result');row.append(el('h2',n.title),el('p','Saved context','muted'),taskButton('Read context',()=>readCitation(n.reference)));$('search-results').append(row);}for(const hit of data.items){const row=el('article',null,'search-result');row.append(el('h2',hit.title||'Recorded conversation'),el('p',(hit.provider==='anthropic'?'Claude Code':'Codex')+' · '+hit.role+' · '+hit.timestamp.slice(0,10)+' · '+hit.project,'muted'),el('p',hit.snippet),taskButton('Read in context',()=>readCitation(hit.citation)));$('search-results').append(row);}$('search-status').textContent=data.items.length||data.notes.length?'Results match all entered words. Open a result to check the surrounding context.':'No matches. Try fewer words, another project, or Refresh after new work.';$('search-more').hidden=!data.more;$('search-more').onclick=guarded(async()=>{work.searchOffset+=20;await search(true);});}catch(e){$('search-status').textContent='Search failed. '+e.message+' Try again.';throw e;}}
async function readCitation(citation){page('search');$('reader').hidden=false;$('reader').replaceChildren(el('p','Reading…'));try{const data=await api('read',{citation});clear('reader');$('reader').append(taskButton('Close excerpt',()=>{$('reader').hidden=true;}));if(data.note){$('reader').append(el('h2',data.note.title),el('pre',data.note.text),taskButton('Edit saved context',()=>editNote(data.note)));}else{const s=data.selected;$('reader').append(el('h2',s.title||'Recorded conversation'),el('p',s.project,'muted'),el('p','Historical conversation · bounded excerpts · best-effort redaction','section-note'));for(const m of data.messages){const n=el('article',null,'message'+(m.id===s.id?' selected-message':''));n.append(el('h3',m.role==='user'?'You':'Assistant'),el('p',m.timestamp,'muted'),el('pre',m.text));if(m.truncated)n.append(el('p','Excerpt limit reached; the original transcript contains more text.','section-note'));$('reader').append(n);}const navigation=el('div',null,'pager');if(data.earlier)navigation.append(taskButton('Earlier messages',()=>readCitation(data.earlier)));if(data.later)navigation.append(taskButton('Later messages',()=>readCitation(data.later)));$('reader').append(navigation);$('reader').append(taskButton('Save a takeaway',async()=>{page('notes');resetNote();$('note-title').value=(s.title||'Session takeaway').slice(0,160);$('note-citation').value=citation;$('note-project').value=s.project;$('note-status').textContent='Write the decision or useful context in your own words. The source citation will be retained.';$('note-text').focus();await loadNotes();}),taskButton('Inspect session usage',()=>inspect(s)));}$('reader').focus();}catch(e){$('reader').replaceChildren(el('p',e.message,'error'),taskButton('Retry',()=>readCitation(citation)));throw e;}}
function resetNote(){$('note-form').reset();$('note-id').value=$('note-citation').value='';$('note-project').value=$('project').value;$('note-form-title').textContent='Save context';$('note-status').textContent='';}
async function editNote(n){page('notes');$('note-id').value=n.id;$('note-title').value=n.title;$('note-text').value=n.text;$('note-project').value=n.project;$('note-citation').value=n.citation;$('note-form-title').textContent='Edit context';$('note-text').focus();await loadNotes();}
async function mutate(route,data){const response=await fetch('/api/'+route,{method:'POST',headers:{'X-Lens-Token':token,'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw new Error(result.error);return result;}
async function loadNotes(append=false){if(!append)work.noteOffset=0;const data=await api('notes',{...projectScope(),offset:work.noteOffset});if(!append)clear('notes-list');for(const n of data.items){const row=el('article',null,'saved-note');row.append(el('h2',n.title),el('p',(n.project||'Every project')+' · '+new Date(n.updated).toLocaleDateString(),'muted'),el('p',n.text.slice(0,350)+(n.text.length>350?'…':'')),taskButton('Read / edit',()=>editNote(n)));if(n.citation)row.append(taskButton('Source',()=>readCitation(n.citation)));const deletion=el('details',null,'delete-note');deletion.append(el('summary','Delete'),el('p','Remove this saved note from the local index? Its original source is unchanged.'),taskButton('Delete this note',async()=>{await mutate('notes/delete',{id:n.id});await loadNotes();status('Saved note deleted');}));row.append(deletion);$('notes-list').append(row);}if(!data.items.length&&!append)$('notes-list').append(el('p','Nothing saved yet. Keep one useful decision or handoff, or find a conversation and save its takeaway.','empty'));$('notes-more').hidden=data.items.length<100;}
$('notes-more').addEventListener('click',guarded(async()=>{work.noteOffset+=100;await loadNotes(true);}));
$('home-search').addEventListener('submit',guarded(async e=>{e.preventDefault();page('search');$('search-query').value=$('home-query').value;await search();}));
$('search-form').addEventListener('submit',guarded(async e=>{e.preventDefault();await search();}));
$('note-reset').addEventListener('click',resetNote);
$('note-form').addEventListener('submit',guarded(async e=>{e.preventDefault();const button=$('note-form').querySelector('[type="submit"]');button.disabled=true;try{await mutate('notes/save',{id:$('note-id').value,title:$('note-title').value,text:$('note-text').value,project:$('note-project').value,citation:$('note-citation').value});resetNote();await loadNotes();$('note-status').textContent='Saved. Connected agents can retrieve this context.';}catch(error){$('note-status').textContent=error.message;throw error;}finally{button.disabled=false;}}));
$('note-file').addEventListener('change',guarded(async()=>{const f=$('note-file').files[0];if(!f)return;if(!/\.(md|txt)$/i.test(f.name)||f.size>128000)throw new Error('Choose a text or Markdown file up to 32,000 characters.');const bytes=await f.arrayBuffer();let text;try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{throw new Error('The file must be UTF-8 text.');}if(text.length>32000||text.includes('\0'))throw new Error('Choose a text file up to 32,000 characters.');$('note-title').value=f.name.replace(/\.(md|txt)$/i,'').slice(0,160);$('note-text').value=text;$('note-status').textContent='File loaded into the editor. Review, then save.';}));
$('copy-config').addEventListener('click',guarded(()=>copyText(JSON.stringify(work.config,null,2))));
$('project').addEventListener('change',guarded(async()=>{stashHandoff();state.sessionOffset=0;work.revision++;if(work.page==='search'){clear('search-results');$('reader').hidden=true;await search();}else await navigate(work.page);}));
window.refreshWorkspace=async()=>{work.revision++;await navigate(work.page);status('Local history ready · index refreshed');};
window.addEventListener('ledger-ready',guarded(async()=>{for(const o of $('project').options){if(o.value)option($('note-project'),o.textContent,o.value);}await home();}));

// Project recovery keeps editable drafts in memory only; saving is an explicit action.
const handoffs=new Map();
let currentBrief=null;
function stashHandoff(){if(currentBrief&&!$('handoff-editor').hidden)handoffs.set(currentBrief.project,{goal:$('handoff-goal').value,text:$('handoff-text').value,open:true,id:handoffs.get(currentBrief.project)?.id});}
async function chooseProject(project){stashHandoff();$('project').value=project;await navigate('home');}
async function renderBriefing(data,revision){
  stashHandoff();const project=$('project').value;
  $('project-start').hidden=!!project;$('project-briefing').hidden=!project;$('handoff-editor').hidden=true;
  $('review-history').disabled=!project;
  $('review-hint').textContent=project?'Look for one change to try next time. Findings link back to the recorded evidence.':'Choose a project to investigate repeated failures, large results, or growing context.';
  if(!project){currentBrief=null;clear('project-shortcuts');const seen=new Set();for(const s of data.recent.items){if(seen.has(s.project))continue;seen.add(s.project);const b=taskButton('Continue '+s.project.split(/[\\/]/).pop(),()=>chooseProject(s.project),'project-shortcut');b.title=s.project;$('project-shortcuts').append(b);if(seen.size===6)break;}if(!seen.size)$('project-shortcuts').append(el('p','Import your history or try the demo to see recent projects.','muted'));return;}
  $('briefing-title').textContent='Continue '+project.split(/[\\/]/).pop();$('briefing-status').textContent='Gathering recent context…';clear('briefing-sources');$('build-handoff').disabled=true;
  try{
    const brief=await api('briefing',{project});if(revision!==work.revision||project!==$('project').value)return;currentBrief=brief;
    $('briefing-status').textContent='Latest recorded updates and saved context. Check the sources before continuing; these are historical reports.';
    const updates=el('section');updates.append(el('h3','Where the last sessions ended'));
    for(const u of brief.updates){const row=el('article',null,'brief-source');row.append(el('h4',u.title),el('p',u.timestamp.slice(0,10)+' · reported by the agent','section-note'));const d=el('details');d.append(el('summary',u.text.slice(0,180)+(u.text.length>180?'…':'')),el('pre',u.text));if(u.truncated)d.append(el('p','Excerpt clipped; open the source to read more.','section-note'));row.append(d,taskButton('Read source',()=>readCitation(u.citation)));updates.append(row);}
    if(!brief.updates.length)updates.append(el('p','No recent assistant updates available. Search older work, or write the context you know in a handoff.','muted'));
    const notes=el('section');notes.append(el('h3','Decisions and context you kept'));
    for(const n of brief.notes){const row=el('article',null,'brief-source');row.append(el('h4',n.title),el('p',n.text.slice(0,220)+(n.text.length>220?'…':'')),taskButton('Read saved context',()=>readCitation(n.reference)));notes.append(row);}
    if(!brief.notes.length)notes.append(el('p','No saved decisions yet. Read a relevant update and save the takeaway, or prepare a handoff from these sources.','muted'));
    $('briefing-sources').append(updates,notes);$('build-handoff').disabled=false;
    if(handoffs.get(project)?.open)prepareHandoff(false);
  }catch(error){$('briefing-status').textContent='Could not load this briefing. '+error.message;currentBrief=null;throw error;}
}
function prepareHandoff(focus=true){if(!currentBrief)return;const saved=handoffs.get(currentBrief.project);$('handoff-editor').hidden=false;$('handoff-goal').value=saved?.goal||'';$('handoff-text').value=saved?.text??currentBrief.draft;$('handoff-status').textContent='Source excerpts are included so you can use this without configuring MCP.';if(focus){$('handoff-goal').focus();$('handoff-editor').scrollIntoView({block:'start',behavior:'smooth'});}}
function handoffText(){const goal=$('handoff-goal').value.trim();if(!goal){$('handoff-goal').focus();throw new Error('Add what you want to do next so the handoff has a clear objective.');}const text=$('handoff-text').value.trim();if(!text)throw new Error('Add the context you want to carry forward.');return '# Next task\n'+goal+'\n\n'+text;}
$('build-handoff').addEventListener('click',()=>prepareHandoff());
for(const id of ['handoff-goal','handoff-text'])$(id).addEventListener('input',stashHandoff);
$('copy-handoff').addEventListener('click',guarded(async()=>{try{const copied=await copyText(handoffText());$('handoff-status').textContent=copied?'Copied. Paste the handoff into your next agent session.':'Automatic copy is unavailable. Select and copy your goal and the context from the editor.';}catch(e){$('handoff-status').textContent=e.message;throw e;}}));
$('save-handoff').addEventListener('click',guarded(async()=>{
  if(!currentBrief)return;const button=$('save-handoff');button.disabled=true;
  try{
    const text=handoffText(),project=currentBrief.project;
    stashHandoff();const draft={...handoffs.get(project)};
    const saved=await mutate('notes/save',{id:draft.id,title:('Handoff · '+project.split(/[\\/]/).pop()).slice(0,160),text,project,citation:currentBrief.updates[0]?.citation||''});
    handoffs.set(project,{...draft,id:saved.id});
    if(currentBrief?.project===project&&$('project').value===project){
      await renderBriefing({recent:{items:[]}},work.revision);
      $('handoff-status').textContent='Saved to this project. You can find it in Saved context or retrieve it through MCP.';
    }
  }catch(e){$('handoff-status').textContent=e.message;throw e;}finally{button.disabled=false;}
}));
$('review-history').addEventListener('click',guarded(async()=>{if(!$('project').value)return;const b=$('review-history');b.disabled=true;try{await home(true);$('usage-review').scrollIntoView({block:'start',behavior:'smooth'});}finally{b.disabled=!$('project').value;}}));

// Project conversations are ephemeral. Only explicit note saves write to the index.
const conversations=new Map();let askCapability=null;
function conversation(){const project=$('project').value;if(!conversations.has(project))conversations.set(project,{project,question:'',history:[],packet:null,result:null,running:false,status:''});return conversations.get(project);}
async function showAsk(){renderAsk();if(!askCapability){askCapability=await api('ask/options');if(work.page==='ask')renderAsk();}}
function renderCited(text,sources,target){
  const valid=new Set(sources.map(s=>s.citation));
  for(const part of text.split(/(\[(?:message|note):\d+\])/g)){
    const ref=part.slice(1,-1);
    if(valid.has(ref))target.append(taskButton(part,()=>readCitation(ref),'citation-link'));
    else target.append(document.createTextNode(part));
  }
}
function renderAsk(){
  const c=conversation();$('ask-question').value=c.question;$('ask-question').disabled=c.running;
  $('ask-find').disabled=!c.project||c.running;$('ask-provider').textContent=askCapability?.label||'Checking the optional Claude connection…';
  $('ask-status').textContent=!c.project?'Choose a project above to investigate its history.':c.status;
  $('ask-evidence').hidden=!c.packet;$('ask-evidence').open=!c.result;$('ask-answer').hidden=!c.result;
  $('ask-run').disabled=c.running||!askCapability?.available||!c.packet?.sources.length||!!c.result;
  $('ask-run').textContent=askCapability?.demo?'Show synthetic answer':'Ask Claude';
  $('ask-cancel').hidden=!c.running;$('ask-new').disabled=c.running;
  const earlier=c.result?c.history.slice(0,-1):c.history;$('ask-history').hidden=!earlier.length;clear('ask-history-text');
  for(const turn of earlier){const row=el('div',null,'ask-source');row.append(el('h3',turn.question),el('pre',turn.answer));$('ask-history-text').append(row);}
  clear('ask-sources');clear('ask-answer-text');
  if(c.packet){
    $('ask-coverage').textContent=`${c.packet.sources.length} excerpts · ${number(c.packet.sources.reduce((sum,s)=>sum+s.text.length,0))} source characters · ${c.packet.history.length} prior exchanges. `+(c.packet.matched?'Matching excerpts and nearby context. ':'No keyword matches; showing recent excerpts. ')+c.packet.retrieval;
    for(const source of c.packet.sources){const d=el('details',null,'ask-source');d.append(el('summary',source.title+' · '+source.role+' · '+source.citation),el('pre',source.text));if(source.truncated)d.append(el('p','Excerpt clipped; open the source for more context.','section-note'));d.append(taskButton('Open source',()=>readCitation(source.citation)));$('ask-sources').append(d);}
    if(!c.packet.sources.length)$('ask-sources').append(el('p','No evidence to send. Try another topic or import more history.'));
  }
  if(c.result){$('ask-answer-notice').textContent=c.result.notice;renderCited(c.result.answer,c.packet.sources,$('ask-answer-text'));}
}
$('ask-question').addEventListener('input',()=>{const c=conversation();c.question=$('ask-question').value;c.packet=null;c.result=null;$('ask-evidence').hidden=$('ask-answer').hidden=true;});
for(const b of document.querySelectorAll('[data-question]'))b.addEventListener('click',()=>{const c=conversation();if(c.running)return;c.question=b.dataset.question;c.packet=null;c.result=null;renderAsk();$('ask-question').focus();});
$('home-ask').addEventListener('click',guarded(()=>navigate('ask')));
$('home-cleanup').addEventListener('click',guarded(async()=>{await navigate('ask');const c=conversation();if(!c.running){c.question='Which saved project notes conflict or appear outdated? Propose edits with sources; do not change anything.';c.packet=null;c.result=null;renderAsk();}}));
$('ask-form').addEventListener('submit',guarded(async e=>{
  e.preventDefault();const c=conversation();if(c.running)return;
  c.question=$('ask-question').value.trim();c.status='Finding local evidence…';c.packet=null;c.result=null;renderAsk();
  const requestedQuestion=c.question;
  try{const packet=await mutate('ask/prepare',{project:c.project,question:requestedQuestion,history:c.history.slice(-4)});if(c.question===requestedQuestion)c.packet=packet;c.status='Review the excerpts, then ask for an answer. Nothing has been sent to a model yet.';}
  catch(error){c.status=error.message;}if(work.page==='ask'&&$('project').value===c.project)renderAsk();
}));
$('ask-run').addEventListener('click',guarded(async()=>{
  const c=conversation();if(!c.packet||c.running)return;c.running=true;c.status='Claude is reading the supplied evidence… This may take up to two minutes.';renderAsk();
  try{
    const started=await mutate('ask/start',{id:c.packet.id});
    while(true){
      await new Promise(resolve=>setTimeout(resolve,750));
      const result=await api('ask/status',{id:started.id});
      if(result.state==='running')continue;
      if(result.state!=='complete')throw new Error(result.error||'Question cancelled. No memory was changed.');
      c.result=result;c.history.push({question:c.question.slice(0,6000),answer:result.answer.slice(0,6000)});c.history=c.history.slice(-4);
      c.status='Answer ready. Check the sources before keeping a decision.';break;
    }
  }catch(error){c.status=error.message;c.packet=null;}
  finally{c.running=false;if(work.page==='ask'&&$('project').value===c.project)renderAsk();}
}));
$('ask-cancel').addEventListener('click',guarded(async()=>{const c=conversation();if(c.packet){await mutate('ask/cancel',{id:c.packet.id});c.status='Cancelling…';renderAsk();}}));
$('ask-new').addEventListener('click',()=>{const c=conversation();if(!c.running){conversations.delete(c.project);renderAsk();$('ask-question').focus();}});
$('ask-copy').addEventListener('click',guarded(()=>copyText(conversation().result?.answer||'')));
$('ask-save').addEventListener('click',guarded(async()=>{
  const c=conversation();if(!c.result)return;page('notes');resetNote();$('note-title').value=c.question.slice(0,160);$('note-text').value=c.result.answer;$('note-project').value=c.project;
  const valid=new Set(c.packet.sources.map(s=>s.citation));const cited=[...c.result.answer.matchAll(/\[((?:message|note):\d+)\]/g)].map(m=>m[1]).find(ref=>valid.has(ref));$('note-citation').value=cited||'';
  $('note-status').textContent='AI draft — review the wording and sources, then Save context. Existing notes have not changed.';await loadNotes();$('note-text').focus();
}));
