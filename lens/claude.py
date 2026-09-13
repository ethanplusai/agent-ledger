"""Claude Code adapter. Reuses bounded, restartable source checkpoints."""
from datetime import datetime, timezone
from .importer import Importer, dump, digest, short
from .accounting import normalize, FIELDS
from .memory import content_text, save_message
from .privacy import scrub
import json


class ClaudeImporter(Importer):
    folders = ('projects',)
    agent_label = 'Claude Code'

    def accepts(self, record):
        return isinstance(record, dict) and isinstance(record.get('type'), str)

    def record(self, sid, offset, state, record):
        typ = record['type']
        timestamp = short(record.get('timestamp'),64)
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z','+00:00'))
            if dt.tzinfo is None: raise ValueError()
            timestamp=dt.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
        except (ValueError,OverflowError):
            timestamp=''
        if not state.get('claude'):
            source = self.db.execute('SELECT path FROM sources WHERE id=?',(sid,)).fetchone()[0]
            from pathlib import Path
            state.update(claude=True, provider='anthropic', session='claude:'+Path(source).stem)
            self.db.execute('UPDATE sessions SET sid=?,provider=? WHERE source=?',(state['session'],'anthropic',sid))
        # Subagent files have their own identity even when sessionId points at the parent's conversation.
        source = self.db.execute('SELECT path FROM sources WHERE id=?',(sid,)).fetchone()[0]
        is_child = '/subagents/' in source.replace('\\','/')
        session = short(record.get('sessionId'))
        if session and not is_child:
            state['session']='claude:'+session
            self.db.execute('UPDATE sessions SET sid=? WHERE source=?',(state['session'],sid))
        elif session and is_child:
            self.db.execute('UPDATE sessions SET parent=?,relationship=? WHERE source=?',('claude:'+session,'subagent',sid))
        if isinstance(record.get('cwd'),str):
            state['cwd']=short(record['cwd'],4096)
            self.db.execute('UPDATE sessions SET project=? WHERE source=?',(scrub(state['cwd']),sid))
        if typ in ('custom-title','ai-title'):
            title=short(record.get('customTitle') or record.get('aiTitle'),140)
            if title:self.db.execute('UPDATE sessions SET title=? WHERE source=?',(scrub(title),sid))
        if typ=='system' and record.get('subtype')=='compact_boundary':
            state['boundary']+=1
        message=record.get('message')
        if typ not in ('user','assistant') or not isinstance(message,dict):return
        identity=short(record.get('uuid')) or str(offset)
        content=message.get('content')
        if typ=='user' and not record.get('isMeta'):
            text=content_text(content)
            if text and not text.lstrip().startswith(('<local-command-', '<command-name>', '<command-message>', 'Base directory for this skill:')):
                state['turn']=identity
                save_message(self.db,sid,offset,identity,'user',timestamp,text)
        if typ=='assistant' and not record.get('isApiErrorMessage'):
            save_message(self.db,sid,offset,identity,'assistant',timestamp,content_text(content))
            rid=short(message.get('id'))
            raw=message.get('usage')
            if rid and isinstance(raw,dict):
                # Claude's ordinary input excludes cache reads/writes. Convert once to Lens's inclusive input.
                numbers=[raw.get(k,0) for k in ('input_tokens','cache_read_input_tokens','cache_creation_input_tokens','output_tokens')]
                valid=all(type(v) is int and 0<=v<=2**53-1 for v in numbers) and 'input_tokens' in raw and 'output_tokens' in raw
                if not valid:
                    self.diag(sid,offset,'claude_usage','Invalid or incomplete Claude usage snapshot excluded.')
                else:
                    i,c,w,o=numbers
                    usage=normalize(dict(input_tokens=i+c+w,cached_input_tokens=c,cache_write_input_tokens=w,output_tokens=o,total_tokens=i+c+w+o))
                    key=dump(['anthropic',rid])
                    prior=self.db.execute('SELECT * FROM appearances WHERE source=? AND key=?',(sid,key)).fetchone()
                    if prior:
                        old=json.loads(prior['usage'])
                        # Streaming snapshots within one source may grow. Never sum repeated fragments.
                        if all(usage[k]>=old[k] for k in ('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens')):
                            self.db.execute('UPDATE appearances SET usage=?,signature=? WHERE id=?',(dump(usage),digest(dump({k:usage[k] for k in FIELDS})),prior['id']))
                        elif any(usage[k]!=old[k] for k in ('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens')):
                            old['errors'].append('Non-monotonic stream snapshots; response excluded')
                            old['displayed_total']=None
                            self.db.execute('UPDATE appearances SET usage=? WHERE id=?',(dump(old),prior['id']))
                            self.diag(sid,offset,'claude_stream_conflict','Non-monotonic Claude stream usage; retained prior snapshot. Coverage may be incomplete.')
                    else:
                        self.add_usage(sid,offset,state,timestamp,state['turn'],rid,key,usage,'native',{'model':message.get('model')})
                    self.db.execute("UPDATE activities SET following=?,association='Chronological correlation' WHERE source=? AND following IS NULL AND kind='output' AND offset<?",(key,sid,offset))
            elif raw:
                self.diag(sid,offset,'claude_identity','Claude usage lacks a message identity; excluded.')
        if not isinstance(content,list):return
        for index,b in enumerate(content):
            if not isinstance(b,dict):continue
            if b.get('type')=='tool_use':
                names={'Bash':'shell','Read':'read'}
                args=b.get('input',{})
                if isinstance(args,dict) and 'file_path' in args:args=dict(args,path=args['file_path'])
                self.activity(sid,offset,state,timestamp,{'type':'function_call','call_id':b.get('id'),'name':names.get(b.get('name'),b.get('name')),'arguments':args})
            elif b.get('type')=='tool_result':
                out=b.get('content','')
                self.activity(sid,offset,state,timestamp,{'type':'function_call_output','call_id':b.get('tool_use_id'),'output':out})
                if b.get('is_error'):
                    self.db.execute("UPDATE activities SET failed=1 WHERE source=? AND call_id=? AND kind='output'",(sid,b.get('tool_use_id')))
