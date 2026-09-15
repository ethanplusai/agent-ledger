import io
import json
import tempfile
import unittest
from pathlib import Path
from lens.storage import connect
from lens.claude import ClaudeImporter
from lens.memory import Memory
from lens.mcp import serve, call
from lens.query import Report
from lens.demo import write_demo
from lens.importer import Importer


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.home=self.root/'claude';self.folder=self.home/'projects'/'test';self.folder.mkdir(parents=True)
        self.path=self.folder/'s.jsonl';self.dbpath=self.root/'cache.sqlite3';self.db=connect(self.dbpath)
    def tearDown(self):self.db.close();self.temp.cleanup()
    def row(self, typ='assistant', text='We chose SQLite for offline search.', ident='a', output=10, message='m'):
        return dict(type=typ,sessionId='s',uuid=ident,cwd='/demo/project',timestamp='2026-09-12T10:00:00Z',requestId='req',message=dict(id=message,role=typ,model='claude-demo',content=[dict(type='text',text=text)],usage=dict(input_tokens=10,cache_read_input_tokens=20,cache_creation_input_tokens=30,output_tokens=output)))
    def load(self, rows):
        self.path.write_text(''.join(json.dumps(r)+'\n' for r in rows));return ClaudeImporter(self.db,self.home).run()
    def test_cache_counts_inclusive_and_no_codex_credit_guess(self):
        self.load([self.row()]);t=Report(self.db).totals({});self.assertEqual(t['total'],70);self.assertEqual(t['input'],60);self.assertIsNone(t['credits']);self.assertIsNone(t['reasoning'])
    def test_stream_snapshots_merge_and_copied_source_deduplicates(self):
        self.load([self.row(output=3),self.row(ident='b',output=10)])
        self.assertEqual(Report(self.db).totals({})['total'],70)
        (self.folder/'copy.jsonl').write_bytes(self.path.read_bytes());ClaudeImporter(self.db,self.home).run()
        self.assertEqual(Report(self.db).totals({})['responses'],1);self.assertEqual(Report(self.db).totals({})['total'],70)
    def test_conflicting_copy_excluded(self):
        self.load([self.row()]);(self.folder/'copy.jsonl').write_text(json.dumps(self.row(output=30))+'\n');ClaudeImporter(self.db,self.home).run();self.assertEqual(Report(self.db).totals({})['invalid'],1)
    def test_append_resume_and_replacement_remove_fts_rows(self):
        self.load([self.row()]);self.assertEqual(ClaudeImporter(self.db,self.home).run()['changed'],0)
        with self.path.open('a') as f:f.write(json.dumps(self.row(text='New release decision',ident='new',message='new'))+'\n')
        ClaudeImporter(self.db,self.home).run();self.assertEqual(len(Memory(self.db).search({'q':'decision'})['items']),1)
        self.load([self.row(text='Replacement content')]);self.assertEqual(Memory(self.db).search({'q':'decision'})['items'],[])
    def test_incomplete_tail_waits_for_newline(self):
        self.path.write_text(json.dumps(self.row()));ClaudeImporter(self.db,self.home).run();self.assertEqual(Report(self.db).totals({})['records'],0)
        with self.path.open('a') as f:f.write('\n')
        ClaudeImporter(self.db,self.home).run();self.assertEqual(Report(self.db).totals({})['records'],1)
    def test_search_literals_scope_and_citation(self):
        self.load([self.row()]);memory=Memory(self.db)
        self.assertEqual(memory.search({'q':'SQLite','project':'/other'})['items'],[])
        hits=memory.search({'q':'"SQLite" * (offline)'})['items'];self.assertEqual(len(hits),1)
        r=memory.read({'citation':hits[0]['citation']});self.assertTrue(r['untrusted']);self.assertIn('SQLite',r['selected']['text'])
    def test_redaction_before_persistence(self):
        secret='sk-'+('a'*32);self.load([self.row(text='Value '+secret)])
        self.assertNotIn(secret,self.db.execute('SELECT text FROM messages').fetchone()[0]);self.assertIn('[redacted]',self.db.execute('SELECT text FROM messages').fetchone()[0])
    def test_user_only_session_discoverable(self):
        self.load([self.row(typ='user',text='Why use SQLite?')]);memory=Memory(self.db)
        self.assertEqual(len(memory.sessions({})['items']),1);self.assertEqual(Report(self.db).totals({})['records'],0)
    def test_notes_global_project_edit_and_delete(self):
        m=Memory(self.db);a=m.save_note({'title':'Global','text':'Use tests'});b=m.save_note({'title':'Decision','text':'SQLite offline','project':'/demo/project'})
        self.assertEqual(len(m.notes({'project':'/demo/project'})['items']),2);self.assertEqual(len(m.notes({'project':'/other'})['items']),1)
        m.save_note(dict(id=b['id'],title='Changed',text='Decision revised',project='/demo/project'))
        self.assertEqual(m.read({'citation':b['reference']})['note']['title'],'Changed')
        m.delete_note({'id':b['id']});self.assertEqual(len(m.notes({})['items']),1)
    def test_note_validation(self):
        for args in ({'title':'','text':'a'},{'title':'a','text':'x'*32001},{'title':{},'text':'x'}):
            with self.assertRaises(ValueError):Memory(self.db).save_note(args)
    def test_mcp_lifecycle_tools_errors_and_no_writes(self):
        self.load([self.row()]);self.db.commit()
        requests=[dict(jsonrpc='2.0',id=0,method='tools/list'),dict(jsonrpc='2.0',id=1,method='initialize',params={'protocolVersion':'2025-11-25'}),dict(jsonrpc='2.0',method='notifications/initialized'),dict(jsonrpc='2.0',id=2,method='tools/list'),dict(jsonrpc='2.0',id=3,method='tools/call',params={'name':'search_history','arguments':{'q':'SQLite'}}),dict(jsonrpc='2.0',id=4,method='tools/call',params={'name':'write_file','arguments':{}})]
        out=io.StringIO();serve(self.dbpath,io.BytesIO(('\n'.join(json.dumps(x) for x in requests)+'\n').encode()),out)
        replies=[json.loads(l) for l in out.getvalue().splitlines()];self.assertEqual(len(replies),5);self.assertIn('error',replies[0]);self.assertEqual(len(replies[2]['result']['tools']),6);self.assertIn('SQLite',replies[3]['result']['content'][0]['text']);self.assertTrue(replies[4]['result']['isError'])
        call(self.db,'recent_sessions',{})
        import sqlite3
        with self.assertRaises(sqlite3.OperationalError):self.db.execute("INSERT INTO notes(title,text,created,updated) VALUES('a','b','x','x')")
    def test_mcp_malformed_and_oversize_recovery(self):
        out=io.StringIO();serve(self.dbpath,io.BytesIO(b'no json\n'+b'x'*70000+b'\n'+b'{"jsonrpc":"2.0","id":8,"method":"ping"}\n'),out)
        responses=[json.loads(x) for x in out.getvalue().splitlines()];self.assertEqual(len(responses),3);self.assertEqual(responses[-1]['result'],{})
    def test_findings_have_explanation_action_and_provenance(self):
        home=self.root/'codex';write_demo(home);Importer(self.db,home).run();items=Memory(self.db).insights({})['items'];self.assertTrue(items)
        for item in items:
            for field in ('observed','meaning','next','prompt','evidence'):self.assertTrue(item[field])
            self.assertIn('sid',item['evidence'])
    def test_replaced_source_cannot_reuse_an_old_citation(self):
        self.load([self.row()]);m=Memory(self.db);citation=m.search({'q':'SQLite'})['items'][0]['citation']
        self.load([self.row(text='A different conversation with unrelated content')])
        with self.assertRaises(ValueError):m.read({'citation':citation})
    def test_reader_can_page_beyond_initial_context(self):
        self.load([self.row(text='Message '+str(i),ident=str(i),message=str(i)) for i in range(12)])
        m=Memory(self.db);first=m.sessions({})['items'][0]['message'];r=m.read({'citation':'message:'+str(first)})
        self.assertIsNotNone(r['later']);later=m.read({'citation':r['later']});self.assertIsNotNone(later['earlier'])
    def test_saved_note_search_is_not_limited_to_first_page(self):
        m=Memory(self.db);m.save_note({'title':'Old decision','text':'Rare migration choice'})
        for i in range(101):m.save_note({'title':'Recent '+str(i),'text':'Other context'})
        self.assertEqual(len(m.search({'q':'Rare migration'})['notes']),1)

    def test_linking_only_visits_pending_results(self):
        self.load([self.row()])
        source=self.db.execute('SELECT id FROM sources').fetchone()[0]
        self.db.executemany("INSERT INTO activities(source,offset,call_id,kind,following) VALUES(?,?,?,'output','linked')",((source,i,'old-'+str(i)) for i in range(20000)))
        self.db.execute("INSERT INTO activities(source,offset,call_id,kind) VALUES(?,20001,'pending','output')",(source,))
        callbacks=[]
        self.db.set_progress_handler(lambda: callbacks.append(1) or 0,100)
        try:
            self.db.execute("UPDATE activities SET following='next' WHERE source=? AND following IS NULL AND kind='output' AND offset<30000",(source,))
        finally:self.db.set_progress_handler(None,0)
        self.assertLess(len(callbacks),50,'Linking must not scan thousands of already-linked results')
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM activities WHERE following='next'").fetchone()[0],1)
    def test_progress_names_agent_and_current_file_percentage(self):
        from unittest.mock import patch
        self.path.write_text(''.join(json.dumps(self.row(ident=str(i),message=str(i)))+'\n' for i in range(501)))
        messages=[]
        with patch('lens.importer.time.monotonic',side_effect=iter(range(0,10000,3))):
            ClaudeImporter(self.db,self.home,progress=messages.append).run()
        self.assertTrue(any('Scanning Claude Code' in m for m in messages))
        self.assertTrue(any('%' in m and 'checkpoint saved' in m for m in messages))
        self.assertTrue(any('agent scan complete' in m for m in messages))

    def test_oversize_and_malformed_lines_record_coverage(self):
        self.path.write_text('broken\n'+json.dumps(self.row(text='x'*2000))+'\n'+json.dumps(self.row())+'\n');ClaudeImporter(self.db,self.home,line_limit=1000).run()
        codes={r[0] for r in self.db.execute('SELECT code FROM diagnostics')};self.assertIn('oversize',codes);self.assertIn('malformed',codes)

if __name__=='__main__':unittest.main()

class MemoryHTTPTests(unittest.TestCase):
    def setUp(self):
        import threading
        from lens.server import LocalServer
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'cache.sqlite3';db=connect(self.path);db.close()
        self.server=LocalServer(self.path,lambda:{'records':0});self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,route,payload=None,token=True,origin=None):
        import urllib.request,urllib.error
        headers={'Content-Type':'application/json'}
        if token:headers['X-Lens-Token']=self.server.token
        if origin:headers['Origin']=origin
        req=urllib.request.Request(self.server.origin+'/api/'+route,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            try:return error.code,json.load(error)
            finally:error.close()
    def test_question_routes_require_capability_and_cannot_start_unreviewed_text(self):
        self.assertEqual(self.request('ask/options',token=False)[0],403)
        self.assertEqual(self.request('ask/prepare',{'project':'/demo/project','question':'why'},token=False)[0],403)
        self.assertEqual(self.request('ask/start',{'id':'not-a-packet'},origin='https://example.invalid')[0],403)
        self.server.questions.demo=True
        self.assertEqual(self.request('ask/start',{'id':'not-a-packet'})[0],400)
        self.assertEqual(self.request('ask/start',{'id':[]})[0],400)
        self.assertEqual(self.request('ask/prepare',{'project':'','question':'why'})[0],400)
        self.assertEqual(self.request('ask/status?id=missing')[0],400)

    def test_notes_require_capability_and_same_origin(self):
        p={'title':'Decision','text':'Use a local index'}
        self.assertEqual(self.request('notes/save',p,token=False)[0],403)
        self.assertEqual(self.request('notes/save',p,origin='https://example.invalid')[0],403)
        self.assertEqual(self.request('notes')[1]['items'],[])
    def test_create_read_delete_and_inert_text(self):
        status,created=self.request('notes/save',{'title':'Test','text':'<script>not executable</script>'});self.assertEqual(status,200)
        self.assertIn('<script>',self.request('read?citation='+created['reference'])[1]['note']['text'])
        self.assertEqual(self.request('notes/delete',{'id':created['id']})[0],200);self.assertEqual(self.request('notes')[1]['items'],[])
    def test_note_limits_and_connection_is_private(self):
        self.assertEqual(self.request('notes/save',{'title':'Test','text':'a'*32001})[0],400)
        self.assertEqual(self.request('connection',token=False)[0],403)
        self.assertIn('--mcp',self.request('connection')[1]['mcpServers']['agent-ledger']['args'])

class BriefingTests(unittest.TestCase):
    setUp=MemoryTests.setUp
    tearDown=MemoryTests.tearDown
    row=MemoryTests.row
    load=MemoryTests.load
    def test_briefing_has_project_sources_and_no_cross_project_text(self):
        self.load([self.row(text='Latest Atlas decision')]);memory=Memory(self.db)
        memory.save_note({'title':'Keep','text':'Project convention','project':'/demo/project'})
        memory.save_note({'title':'Global','text':'Global convention'})
        memory.save_note({'title':'Other','text':'Unrelated private context','project':'/other'})
        brief=memory.briefing({'project':'/demo/project'})
        self.assertEqual(len(brief['updates']),1)
        self.assertIn('Latest Atlas decision',brief['draft']);self.assertIn('Project convention',brief['draft'])
        self.assertNotIn('Unrelated private context',brief['draft'])
        self.assertTrue(brief['updates'][0]['citation'].startswith('message:'))
        self.assertIn('historical',brief['draft'])
    def test_briefing_requires_project_and_bounds_context(self):
        self.load([self.row(text='x'*10000)])
        brief=Memory(self.db).briefing({'project':'/demo/project'})
        self.assertEqual(len(brief['updates'][0]['text']),2400);self.assertTrue(brief['updates'][0]['truncated'])
        with self.assertRaises(ValueError):Memory(self.db).briefing({})
    def test_home_defers_expensive_usage_queries(self):
        from unittest.mock import patch
        with patch.object(Memory,'insights',side_effect=AssertionError('Unexpected usage scan')):
            self.assertEqual(Memory(self.db).home({})['insights'],[])
    def test_transcript_pairs_conversation_with_recorded_usage(self):
        self.load([self.row(typ='user',text='Why did we choose SQLite?',ident='u',message='u'),self.row()])
        sid=self.db.execute('SELECT sid FROM sessions').fetchone()[0]
        data=Memory(self.db).transcript({'session':sid})
        self.assertEqual(data['count'],2)
        self.assertEqual([m['role'] for m in data['items']],['user','assistant'])
        # The response is recorded on the assistant record, so it attaches there rather than to the question.
        self.assertEqual(data['items'][0]['total'],0)
        self.assertEqual(data['items'][1]['total'],70)
        self.assertEqual(data['items'][1]['responses'],1)
        self.assertEqual(data['items'][-1]['cumulative'],70)
        self.assertEqual(data['recorded'],70)
        self.assertTrue(data['items'][0]['citation'].startswith('message:'))
        with self.assertRaises(ValueError):Memory(self.db).transcript({'session':'missing'})
        with self.assertRaises(ValueError):Memory(self.db).transcript({})
    def test_transcript_counts_tool_activity_against_its_message(self):
        from lens.demo_memory import write_memory_demo
        write_memory_demo(self.home);ClaudeImporter(self.db,self.home).run()
        sid=self.db.execute("SELECT sid FROM sessions WHERE title LIKE 'Prepare the handoff%'").fetchone()[0]
        data=Memory(self.db).transcript({'session':sid})
        self.assertTrue(sum(m['calls'] for m in data['items']))
        self.assertTrue(sum(m['failures'] for m in data['items']))
        self.assertTrue(sum(m['compactions'] for m in data['items']))
        self.assertEqual(data['items'][-1]['cumulative'],data['recorded'])
    def test_agent_comparison_and_tool_breakdown_separate_the_agents(self):
        from lens.demo_memory import write_memory_demo
        write_memory_demo(self.home);ClaudeImporter(self.db,self.home).run()
        codex=self.root/'codex';write_demo(codex);Importer(self.db,codex).run()
        report=Report(self.db)
        providers={p['agent']:p for p in report.providers({})['providers']}
        self.assertTrue(providers['claude']['totals']['records'] and providers['codex']['totals']['records'])
        self.assertIsNone(providers['claude']['totals']['credits'])
        self.assertIsNotNone(providers['codex']['totals']['credits'])
        self.assertEqual(providers['claude']['totals']['total']+providers['codex']['totals']['total'],
                         report.totals({})['total'])
        self.assertTrue(providers['claude']['failures'])
        tools=report.tools({})
        self.assertIn('shell',[r['tool'] for r in tools['items']])
        self.assertIn('functions.exec_command',[r['tool'] for r in tools['items']])
        self.assertEqual(tools['totals']['results'],sum(r['results'] for r in tools['items']))
        self.assertEqual(report.tools({'agent':'claude'})['totals']['results']
                         +report.tools({'agent':'codex'})['totals']['results'],tools['totals']['results'])
