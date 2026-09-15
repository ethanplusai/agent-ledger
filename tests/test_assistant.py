"""No real model or private history is used by this suite."""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from lens.assistant import Questions, evidence_packet, run_claude, claude_command
from lens.claude import ClaudeImporter
from lens.memory import Memory
from lens.storage import connect


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.db=connect(root/'cache.sqlite3');self.home=root/'claude'
        folder=self.home/'projects'/'synthetic';folder.mkdir(parents=True)
        for project,text in [('atlas','We chose SQLite because offline operation was required. Hosted search failed the offline constraint.'),('other','Unrelated private project text')]:
            row=dict(type='user',sessionId=project,uuid=project,cwd='/demo/'+project,timestamp='2026-09-12T10:00:00Z',message={'role':'user','content':text})
            (folder/(project+'.jsonl')).write_text(json.dumps(row)+'\n')
        ClaudeImporter(self.db,self.home).run()
    def tearDown(self):self.db.close();self.temp.cleanup()
    def test_question_retrieves_decision_without_matching_every_word(self):
        packet=evidence_packet(self.db,{'project':'/demo/atlas','question':'Why did we choose SQLite rather than a hosted service?'})
        self.assertTrue(packet['matched']);self.assertIn('offline',packet['sources'][0]['text'])
        self.assertNotIn('Unrelated',json.dumps(packet))
    def test_cleanup_is_project_scoped_and_does_not_write(self):
        memory=Memory(self.db)
        for project in ['/demo/atlas','/demo/other','']:
            memory.save_note({'project':project,'title':'Decision','text':'Notes for '+project})
        before=self.db.total_changes
        packet=evidence_packet(self.db,{'project':'/demo/atlas','question':'Review outdated saved notes'})
        notes=[s for s in packet['sources'] if s['role']=='saved context']
        self.assertEqual(len(notes),1);self.assertEqual(notes[0]['text'],'Notes for /demo/atlas')
        self.assertEqual(self.db.total_changes,before)
    def test_bounds_and_recent_fallback(self):
        packet=evidence_packet(self.db,{'project':'/demo/atlas','question':'zzzznonexistent'})
        self.assertFalse(packet['matched']);self.assertTrue(packet['sources'])
        for args in [{'project':'','question':'why'},{'project':'/demo/atlas','question':'x'*2001},{'project':'/demo/atlas','question':'why','history':[{}]}]:
            with self.assertRaises(ValueError):evidence_packet(self.db,args)
    def test_followup_uses_prior_topic_without_other_project_evidence(self):
        packet=evidence_packet(self.db,{'project':'/demo/atlas','question':'What constraint mattered?', 'history':[{'question':'Why SQLite?','answer':'An earlier answer'}]})
        self.assertTrue(packet['matched']);self.assertEqual(len(packet['history']),1)


class ProcessTests(unittest.TestCase):
    def run_fake(self,script,**kw):
        with patch('lens.assistant.claude_command',return_value=[sys.executable,'-c',script]):
            return run_claude({'question':'synthetic','sources':[]},kw.pop('cancel',threading.Event()),binary=sys.executable,**kw)
    def test_stdin_answer_and_no_shell_tools_or_persisted_session(self):
        result=self.run_fake('import sys,json; p=json.load(sys.stdin); print(json.dumps({"result":p["question"]}))')
        self.assertEqual(result,'synthetic')
        argv=claude_command('claude');self.assertEqual(argv[argv.index('--tools')+1],'')
        self.assertIn('--strict-mcp-config',argv);self.assertIn('--no-session-persistence',argv)
        self.assertNotIn('--dangerously-skip-permissions',argv);self.assertNotIn('--model',argv)
    def test_output_bound(self):
        with self.assertRaisesRegex(ValueError,'too much output'):
            self.run_fake('import sys; sys.stdin.read(); sys.stdout.write("x"*1100000)')
    def test_timeout_and_cancel(self):
        script='import sys,time; sys.stdin.read(); time.sleep(5)'
        with self.assertRaisesRegex(ValueError,'longer'):self.run_fake(script,timeout=.1)
        cancel=threading.Event();cancel.set()
        with self.assertRaisesRegex(ValueError,'cancelled'):self.run_fake(script,cancel=cancel)
    def test_nonzero_and_invalid_format_hide_stderr(self):
        with self.assertRaisesRegex(ValueError,'could not answer'):
            self.run_fake('import sys; sys.stdin.read(); print("private debug",file=sys.stderr); sys.exit(1)')
        with self.assertRaisesRegex(ValueError,'unsupported'):self.run_fake('import sys; sys.stdin.read(); print("not json")')


class JobTests(unittest.TestCase):
    def packet(self):return {'project':'/demo/atlas','question':'Why SQLite?','history':[],'sources':[{'citation':'message:1','text':'Offline constraint'}]}
    def wait(self,questions,key):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            result=questions.get(key)
            if result['state']!='running':return result
            time.sleep(.01)
        self.fail('Job did not finish')
    def test_prepare_never_runs_model_and_packet_cannot_be_reused(self):
        calls=[];q=Questions(runner=lambda packet,cancel:calls.append(packet) or 'Answer [message:1]')
        q.capability={'available':True};p=q.prepare(self.packet());self.assertFalse(calls)
        q.start(p['id']);self.assertEqual(self.wait(q,p['id'])['state'],'complete');self.assertEqual(len(calls),1)
        with self.assertRaises(ValueError):q.start(p['id'])
    def test_one_run_at_a_time_and_cancel(self):
        def runner(packet,cancel):cancel.wait(2);return 'Cancelled answer'
        q=Questions(runner=runner);q.capability={'available':True}
        a=q.prepare(self.packet());b=q.prepare(self.packet());q.start(a['id'])
        with self.assertRaisesRegex(ValueError,'Another'):q.start(b['id'])
        q.cancel(a['id']);self.assertEqual(self.wait(q,a['id'])['state'],'cancelled')
    def test_shutdown_cancels_worker_and_refuses_late_starts(self):
        def runner(packet,cancel):cancel.wait(2);return 'Answer'
        q=Questions(runner=runner);q.capability={'available':True}
        a=q.prepare(self.packet());b=q.prepare(self.packet());q.start(a['id']);q.close()
        self.assertEqual(q.get(a['id'])['state'],'cancelled')
        with self.assertRaisesRegex(ValueError,'stopping'):q.start(b['id'])
        with self.assertRaisesRegex(ValueError,'stopping'):q.prepare(self.packet())

    def test_unknown_citations_are_flagged(self):
        q=Questions(runner=lambda p,c:'Unsupported claim [message:999]');q.capability={'available':True}
        p=q.prepare(self.packet());q.start(p['id']);self.assertIn('outside',self.wait(q,p['id'])['notice'])
    def test_packet_retention_is_bounded_and_demo_does_not_run_provider(self):
        q=Questions(demo=True,runner=lambda *_:self.fail('Real runner invoked'))
        old=q.prepare(self.packet())
        for _ in range(10):p=q.prepare(self.packet())
        self.assertLessEqual(len(q.items),8)
        with self.assertRaises(ValueError):q.get(old['id'])
        q.start(p['id']);self.assertIn('no AI was called',self.wait(q,p['id'])['answer'])


if __name__=='__main__':unittest.main()
