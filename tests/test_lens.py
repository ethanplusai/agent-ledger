"""Synthetic regression tests for money-adjacent accounting and private local data."""
import json
import tempfile
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path
from lens.accounting import normalize, estimate
from lens.demo import write_demo
from lens.importer import Importer, observed
from lens.query import Report
from lens.server import LocalServer
from lens.storage import connect

U = dict(input_tokens=10000,cached_input_tokens=8000,output_tokens=1000,
         reasoning_output_tokens=600,cache_write_input_tokens=0,total_tokens=11000)


def record(typ, payload, timestamp='2026-09-12T12:00:00Z'):
    return dict(type=typ,payload=payload,timestamp=timestamp)


def meta(sid='test-session', **kw):
    return record('session_meta',dict(id=sid,cwd='/demo/project',model_provider='openai',**kw))


def context(turn='task-1',model='gpt-6-astra',**kw):
    return record('turn_context',dict(turn_id=turn,model=model,**kw))


def native(rid='r1',usage=None,**kw):
    timestamp=kw.pop('timestamp','2026-09-12T12:00:00Z')
    return record('token_usage_record',dict(response_id=rid,turn_id='task-1',usage=U if usage is None else usage,**kw),timestamp)


def legacy(usage=None,timestamp='2026-09-12T12:00:01Z'):
    return record('event_msg',dict(type='token_count',info={'total_token_usage':U if usage is None else usage,'last_token_usage':U}),timestamp)


def call(cid='c1',command='cat src/example.py'):
    return record('response_item',dict(type='function_call',name='functions.exec_command',call_id=cid,arguments=json.dumps({'cmd':command})))


def output(cid='c1',text='hello',**kw):
    return record('response_item',dict(type='function_call_output',call_id=cid,output=text,**kw))


class Accounting(unittest.TestCase):
    def test_expected_arithmetic(self):
        u=normalize(U)
        self.assertEqual((u['uncached_input'],u['other_output'],u['displayed_total']),(2000,400,11000))
        self.assertEqual(u['cached_input_tokens']/u['input_tokens'],.8)
        for model,speed,expected in [('gpt-5.6-sol','standard','0.78'),('gpt-6-astra','standard','1.95'),('gpt-6-astra','fast','4.875')]:
            e=estimate(u,model,speed,'2026-09-12','openai')
            self.assertEqual(Decimal(e['total']),Decimal(expected))
            self.assertEqual(sum(map(Decimal,e['parts'])),Decimal(expected))

    def test_synthetic_aggregate_decimal(self):
        u=normalize(dict(input_tokens=1924969,cached_input_tokens=1758208,output_tokens=15437,reasoning_output_tokens=9772,cache_write_input_tokens=0,total_tokens=1940406))
        self.assertEqual(Decimal(estimate(u,'gpt-5.6-sol')['total']),Decimal('41.97668'))

    def test_missing_is_not_zero(self):
        u=normalize({'input_tokens':0,'output_tokens':0})
        self.assertEqual(u['displayed_total'],0)
        self.assertIsNone(u['uncached_input'])
        self.assertIsNone(estimate(u,'gpt-6-astra')['total'])

    def test_invalid_arithmetic(self):
        for bad in [{'cached_input_tokens':10001},{'reasoning_output_tokens':1001},{'total_tokens':12000},{'input_tokens':-1},{'output_tokens':True},{'input_tokens':2**64}]:
            u=normalize(dict(U,**bad))
            self.assertTrue(u['errors']);self.assertIsNone(u['displayed_total']);self.assertIsNone(estimate(u,'gpt-6-astra')['total'])

    def test_unknown_rate_and_speed(self):
        for model,speed,provider in [('new-model',None,'openai'),('gpt-6-astra','unrecognized','openai'),('gpt-6-astra',None,'other')]:
            self.assertIsNone(estimate(normalize(U),model,speed,provider=provider)['total'])
        e=estimate(normalize(U),'gpt-6-astra',timestamp='2025-01-01')
        self.assertFalse(e['historical']);self.assertIn('speed unavailable',e['assumption']);self.assertIn('older',e['assumption'])

    def test_cache_write_not_priced(self):
        self.assertIsNone(estimate(normalize(dict(U,cache_write_input_tokens=1)),'gpt-6-astra')['total'])

    def test_missing_reasoning_retains_total_not_parts(self):
        u=normalize(dict(U,reasoning_output_tokens=None))
        e=estimate(u,'gpt-6-astra');self.assertEqual(Decimal(e['total']),Decimal('1.95'));self.assertIsNone(e['parts'])

    def test_non_text_and_multibyte(self):
        size,chars,h,preview,truncated=observed([{'type':'text','text':'é'}, {'type':'image','data':'secretblob'}],4096)
        self.assertEqual(size,chars+1);self.assertNotIn('secretblob',preview);self.assertIn('image',preview)


class StoreFixture:

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.home=self.root/'history';self.folder=self.home/'sessions';self.folder.mkdir(parents=True)
        self.db_path=self.root/'cache.sqlite3';self.db=connect(self.db_path)

    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def write(self,rows,name='a.jsonl',append=False):
        p=self.folder/name
        with p.open('a' if append else 'w',encoding='utf-8') as h:
            for row in rows:h.write(json.dumps(row)+'\n')
        return p

    def ingest(self,**kw):
        return Importer(self.db,self.home,**kw).run()

    def total(self,**args):return Report(self.db).totals(args)
    def rows(self):return list(self.db.execute('SELECT * FROM appearances'))
    def codes(self):return [r[0] for r in self.db.execute('SELECT code FROM diagnostics')]


class StoreCase(StoreFixture, unittest.TestCase):
    def test_native_and_mirror(self):
        self.write([meta(),context(),native(),legacy(),native()]);self.ingest()
        self.assertEqual(self.total()['total'],11000);self.assertEqual(self.total()['responses'],1)

    def test_legacy_before_native_mirror(self):
        self.write([meta(),context(),legacy(timestamp='2026-09-12T12:00:00Z'),native()]);self.ingest()
        self.assertEqual(self.total()['total'],11000)

    def test_fork_union_and_provenance(self):
        self.write([meta('parent'),context(),native(thread_id='parent')])
        self.write([meta('child',parent_thread_id='parent'),context(),native(thread_id='parent'),native('new',thread_id='child')],name='b.jsonl')
        self.ingest();self.assertEqual(self.total()['total'],22000)
        self.assertEqual(self.total(session='parent',descendants='1')['responses'],2)
        self.assertEqual(self.total(session='parent')['responses'],1)
        child=Report(self.db).session({'session':'child'})['responses'][0]
        detail=Report(self.db).detail({'id':child['id']})
        self.assertTrue(any(p['inherited'] for p in detail['provenance']))

    def test_conflicting_duplicate_not_counted(self):
        self.write([meta(),context(),native()]);self.write([meta('other'),context(),native(usage=dict(U,output_tokens=1001,total_tokens=11001))],name='b.jsonl');self.ingest()
        self.assertEqual(self.total()['invalid'],1);self.assertEqual(self.total()['total'],0)
        self.assertTrue(Report(self.db).session({})['responses'][0]['conflict'])

    def test_missing_response_id_excluded(self):
        r=native();r['payload'].pop('response_id');self.write([meta(),r]);self.ingest()
        self.assertEqual(self.total()['total'],0);self.assertIn('missing_identity',self.codes())

    def test_late_context_backfill(self):
        self.write([meta(),native(),context(speed='fast')]);self.ingest()
        self.assertEqual(Decimal(self.total()['credits']),Decimal('4.875'))

    def test_per_response_model_and_speed(self):
        self.write([meta(),context(speed='standard'),native(),context(model='gpt-5.6-sol',speed='fast'),native('r2')]);self.ingest()
        rs=Report(self.db).session({})['responses']
        self.assertEqual([r['model'] for r in rs],['gpt-6-astra','gpt-5.6-sol'])
        self.assertEqual([Decimal(r['estimate']['total']) for r in rs],[Decimal('1.95'),Decimal('1.95')])

    def test_later_fast_context_does_not_reprice_unknown_speed(self):
        self.write([meta(),context(),native(),context(speed='fast'),native('r2')]);self.ingest()
        rs=Report(self.db).session({})['responses']
        self.assertIsNone(rs[0]['speed']);self.assertEqual(rs[1]['speed'],'fast')
        self.assertEqual(Decimal(rs[0]['estimate']['total']),Decimal('1.95'))

    def test_same_timestamp_is_not_sufficient_mirror_evidence(self):
        self.write([meta(),context(),legacy({k:v*2 for k,v in U.items()},timestamp='2026-09-12T12:00:00Z'),native()]);self.ingest()
        self.assertEqual(self.total()['total'],33000)

    def test_native_thread_snapshot_suppresses_prior_mirror(self):
        self.write([meta(),context(),legacy(),native(thread_token_usage=U,timestamp='2026-09-12T12:00:02Z')]);self.ingest()
        self.assertEqual(self.total()['total'],11000);self.assertEqual(self.total()['legacy'],0)

    def test_mixed_ambiguous_range_is_diagnosed(self):
        self.write([meta(),context(),native(),legacy({k:v*4 for k,v in U.items()})]);self.ingest()
        self.assertEqual(self.total()['total'],11000);self.assertIn('mixed_range',self.codes())

    def test_explicit_result_after_response_links_to_recorded_id(self):
        self.write([meta(),context(),native(),call(),output(response_id='r1')]);self.ingest()
        activity=self.db.execute("SELECT * FROM activities WHERE kind='output'").fetchone()
        self.assertEqual(activity['following'],self.rows()[0]['key'])
        self.assertEqual(activity['association'],'Recorded response identifier')

    def test_timezone_normalizes_for_filtering(self):
        self.write([meta(),context(),native(timestamp='2026-09-12T23:30:00-04:00')]);self.ingest()
        self.assertEqual(self.total(**{'to':'2026-09-12'})['responses'],0)
        self.assertEqual(self.total(**{'from':'2026-09-13'})['responses'],1)

    def test_different_working_directory_not_a_repeat(self):
        self.write([meta(),context(cwd='/demo/one'),call(),output(),native(),context(cwd='/demo/two'),call('c2'),output('c2'),native('r2')]);self.ingest()
        self.assertEqual(Report(self.db).findings({})['repeated'],[])

    def test_legacy_first_and_delta_no_response_points(self):
        self.write([meta(),context(),legacy(),legacy({k:v*2 for k,v in U.items()},'2026-09-12T12:01:00Z')]);self.ingest()
        self.assertEqual(self.total()['total'],22000);self.assertEqual(self.total()['responses'],0);self.assertEqual(self.total()['legacy'],2)
        self.assertEqual(Report(self.db).session({})['responses'],[])
        self.assertIsNone(self.total()['credits'])
        self.assertIsNone(Report(self.db).legacy({})['items'][0]['model'])

    def test_legacy_counter_reset_and_inconsistent_delta(self):
        self.write([meta(),context(),legacy(),legacy({k:0 for k in U},'2026-09-12T12:01:00Z'),legacy(dict(U,input_tokens=8000,total_tokens=9000),'2026-09-12T12:02:00Z')]);self.ingest()
        self.assertIn('legacy_reset',self.codes());self.assertEqual(self.total()['total'],20000)
        self.write([legacy(dict(U,input_tokens=8100,cached_input_tokens=8200,total_tokens=9100))],append=True);self.ingest();self.assertIn('legacy_invalid',self.codes())

    def test_legacy_delta_subset_validation(self):
        self.write([meta(),context(),legacy(),legacy(dict(U,input_tokens=10100,cached_input_tokens=8200,total_tokens=11100))]);self.ingest()
        self.assertIn('legacy_delta',self.codes());self.assertEqual(self.total()['total'],11000)

    def test_legacy_gap_excluded(self):
        p=self.write([meta(),context(),legacy()])
        with p.open('ab') as h:h.write(b'not JSON\n')
        self.write([legacy({k:v*2 for k,v in U.items()})],append=True);self.ingest()
        self.assertIn('legacy_gap',self.codes());self.assertEqual(self.total()['total'],11000)

    def test_legacy_native_transition(self):
        self.write([meta(),context(),legacy(),native(thread_token_usage={k:v*2 for k,v in U.items()}),legacy({k:v*2 for k,v in U.items()}),legacy({k:v*3 for k,v in U.items()},'2026-09-12T12:02:00Z')]);self.ingest()
        self.assertEqual(self.total()['total'],33000);self.assertEqual(self.total()['responses'],1)

    def test_invalid_legacy_baseline_cannot_double_count_recovery(self):
        self.write([meta(),context(),legacy(),legacy(dict(U,cached_input_tokens=99999)),legacy({k:v*2 for k,v in U.items()})]);self.ingest()
        self.assertEqual(self.total()['total'],11000);self.assertIn('legacy_gap',self.codes())

    def test_ambiguous_equal_legacy_native_excluded(self):
        self.write([meta(),context(),legacy(),native(timestamp='2026-09-12T12:00:02Z')]);self.ingest()
        self.assertEqual(self.total()['total'],11000);self.assertIn('mixed_overlap',self.codes())

    def test_call_identity_retains_turn_after_task_complete(self):
        self.write([meta(),context(),call(),record('event_msg',{'type':'task_complete'}),output()]);self.ingest()
        row=self.db.execute("SELECT turn FROM activities WHERE kind='output'").fetchone()
        self.assertEqual(row['turn'],'task-1')

    def test_crash_resumes_committed_batch_only(self):
        rows=[meta(),context()]+[native('r'+str(i)) for i in range(505)]
        self.write(rows)
        class Interrupted(Importer):
            calls=0
            def record(inner,*args):
                inner.calls+=1
                if inner.calls==503:raise RuntimeError('Synthetic crash')
                return super().record(*args)
        with self.assertRaises(RuntimeError):Interrupted(self.db,self.home).run()
        self.db.close();self.db=connect(self.db_path)
        before=len(self.rows());self.assertEqual(before,498)
        self.ingest();self.assertEqual(self.total()['responses'],505)

    def test_legacy_child_is_excluded(self):
        self.write([meta('child',parent_thread_id='parent'),legacy()]);self.ingest()
        self.assertEqual(self.total()['total'],0);self.assertIn('legacy_fork',self.codes())

    def test_idempotent_no_read_unchanged(self):
        self.write([meta(),context(),native()]);self.ingest();r=self.ingest()
        self.assertEqual(r['records'],0);self.assertEqual(r['changed'],0);self.assertEqual(len(self.rows()),1)

    def test_partial_tail_resume(self):
        p=self.write([meta(),context()]);line=json.dumps(native()).encode()+b'\n'
        with p.open('ab') as h:h.write(line[:50])
        self.ingest();self.assertEqual(len(self.rows()),0)
        with p.open('ab') as h:h.write(line[50:])
        r=self.ingest();self.assertEqual(len(self.rows()),1);self.assertEqual(r['records'],1)

    def test_restart_retains_legacy_baseline_and_calls(self):
        self.write([meta(),context(),legacy(),call()]);self.ingest();self.db.close();self.db=connect(self.db_path)
        self.write([output(),legacy({k:v*2 for k,v in U.items()}),native(thread_token_usage={k:v*3 for k,v in U.items()})],append=True);self.ingest()
        self.assertEqual(self.total()['total'],33000)
        activity=self.db.execute("SELECT * FROM activities WHERE kind='output'").fetchone()
        self.assertEqual(activity['action'],'cat src/example.py');self.assertTrue(activity['following'])

    def test_truncation_retains_duplicate_other_source(self):
        self.write([meta(),context(),native(),native('r2')]);self.write([meta('b'),context(),native()],name='b.jsonl');self.ingest()
        self.write([meta(),context()]);self.ingest()
        self.assertEqual(self.total()['responses'],1);self.assertEqual(self.total()['total'],11000)

    def test_replacement_and_in_place_edit(self):
        p=self.write([meta(),context(),native()]);self.ingest()
        self.write([meta(),context(),native('r2')],name='new.jsonl').replace(p);self.ingest()
        self.assertEqual(self.rows()[0]['rid'],'r2')
        self.write([meta(),context(),native('r3')]);self.ingest();self.assertEqual(self.rows()[0]['rid'],'r3')

    def test_oversize_complete_and_partial_line(self):
        p=self.write([meta(),context()]);self.ingest()
        with p.open('ab') as h:h.write(b'x'*4000)
        self.ingest(line_limit=1024);self.assertNotIn('oversize',self.codes())
        with p.open('ab') as h:h.write(b'\n'+json.dumps(native()).encode()+b'\n')
        self.ingest(line_limit=1024);self.assertIn('oversize',self.codes());self.assertEqual(self.total()['total'],11000)

    def test_archives_and_missing_history(self):
        archive=self.home/'archived_sessions';archive.mkdir();self.write([meta(),context(),native()]).rename(archive/'archived.jsonl');self.ingest()
        self.assertEqual(self.total()['responses'],1)
        (archive/'archived.jsonl').unlink();result=self.ingest();self.assertTrue(result['issues']);self.assertEqual(self.total()['responses'],1)

    def test_tool_mirror_dedup_and_inert_preview(self):
        out=output(text='<script>alert(1)</script>');self.write([meta(),context(),call(),out,record('event_msg',{'type':'item_completed','item':out['payload']}),native()]);self.ingest()
        data=Report(self.db).detail({'id':self.rows()[0]['id']});self.assertEqual(len(data['activities']),1);self.assertIn('<script>',data['activities'][0]['preview'])

    def test_findings_exact_arguments_and_compaction(self):
        self.write([meta(),context(),call(),output(text='same'),native(),record('compacted',{}),call('c2'),output('c2','same'),native('r2'),call('c3','cat other.py'),output('c3','same'),native('r3')]);self.ingest()
        findings=Report(self.db).findings({});self.assertEqual(len(findings['repeated']),1)
        group=findings['repeated'][0];self.assertEqual(group['occurrences'],2);self.assertNotEqual(group['first_boundary'],group['last_boundary'])

    def test_non_text_is_metadata_not_counted_or_matched(self):
        image=[{'type':'image','data':'synthetic-one'}]
        self.write([meta(),context(),call(),output(text=image),native(),call('c2'),output('c2',[{'type':'image','data':'synthetic-two'}]),native('r2')]);self.ingest()
        row=self.db.execute("SELECT * FROM activities WHERE kind='output' LIMIT 1").fetchone()
        self.assertEqual(row['bytes'],0);self.assertEqual(row['chars'],0)
        self.assertIn('non-text block',row['preview'])
        self.assertEqual(Report(self.db).findings({})['repeated'],[])

    def test_failure_requires_recorded_exit(self):
        fail='Process exited with code 1\nAssertionError: failed'
        self.write([meta(),context(),call(),output(text=fail),native(),call('c2'),output('c2',fail),native('r2'),call('c3','cat different.py'),output('c3',fail),native('r3')]);self.ingest()
        categories=[x['category'] for x in Report(self.db).findings({})['repeated']]
        self.assertIn('Repeated command failures',categories)

    def test_filters_totals_and_paging(self):
        self.write([meta(),context(),native(),context(model='gpt-5.6-sol'),native('r2')]);self.ingest()
        self.assertEqual(self.total(model='gpt-5.6-sol')['responses'],1)
        self.assertEqual(self.total(project='/wrong')['responses'],0)
        self.assertEqual(self.total(**{'from':'2027-01-01'})['responses'],0)
        self.assertEqual(len(Report(self.db).session({'offset':'1'})['responses']),1)

    def test_finding_navigation_across_response_pages(self):
        self.write([meta(),context()]+[native('r'+str(i)) for i in range(105)]);self.ingest()
        report=Report(self.db);last=self.rows()[-1]
        located=report.locate({'id':last['id']})
        self.assertEqual(located['offset'],100)
        self.assertEqual(located['id'],last['id'])
        self.assertEqual(len(report.session({'offset':'100'})['responses']),5)

    def test_demo_endpoints(self):
        write_demo(self.home);self.ingest();report=Report(self.db)
        overview=report.overview({});self.assertEqual(overview['count'],4)
        self.assertEqual(overview['totals']['responses'],41)
        self.assertTrue(report.findings({})['largest']);self.assertEqual(report.options()['empty_sources'],0)


class Cli(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'report.py'),*args],capture_output=True,text=True,timeout=30)

    def test_demo_without_install_or_real_history(self):
        r=self.invoke('--demo','--import-only','--no-open')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('7 sources',r.stdout)

    def test_custom_empty_home_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            r=self.invoke('--codex-home',str(root/'missing'),'--cache-dir',str(root/'cache'),'--no-claude','--import-only')
            self.assertEqual(r.returncode,0);self.assertIn('No readable rollout',r.stdout)
            self.assertFalse((root/'missing').exists())
            self.assertEqual(len(list((root/'cache').glob('*.sqlite3'))),1)

    def test_cannot_write_cache_inside_history(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.invoke('--codex-home',temp,'--cache-dir',str(Path(temp)/'cache'),'--import-only')
            self.assertEqual(r.returncode,1);self.assertIn('outside agent history roots',r.stderr)

    def test_help_and_invalid_limit(self):
        self.assertEqual(self.invoke('--help').returncode,0)
        self.assertEqual(self.invoke('--preview-chars','0').returncode,2)


class ServerSecurity(StoreFixture, unittest.TestCase):
    def setUp(self):
        super().setUp();self.write([meta(),context(),call(),output(text='<script>window.injected=true</script>'),native()]);self.ingest()
        self.server=LocalServer(self.db_path,lambda:{'records':0})
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()

    def request(self,path,headers=None,method='GET'):
        req=urllib.request.Request(self.server.origin+path,headers=headers or {},method=method)
        try:response=urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:response=e
        self.addCleanup(response.close)
        return response

    def test_non_ascii_token_is_rejected_without_exception(self):
        self.assertEqual(self.request('/api/overview',{'X-Lens-Token':'é'}).status,403)

    def test_requires_token(self):
        self.assertEqual(self.request('/api/overview').status,403)
        self.assertEqual(self.request('/api/overview',{'X-Lens-Token':self.server.token}).status,200)

    def test_rejects_origin_host_and_fetch_site(self):
        for headers in [{'Origin':'https://evil.example'},{'Host':'evil.example'},{'Sec-Fetch-Site':'cross-site'}]:
            headers['X-Lens-Token']=self.server.token
            self.assertEqual(self.request('/api/overview',headers).status,403)
            self.assertEqual(self.request('/api/refresh',headers,'POST').status,403)

    def test_no_arbitrary_files_or_cors(self):
        for path in ['/../../report.py','/report.py','/api/file?path=/etc/passwd']:
            self.assertEqual(self.request(path,{'X-Lens-Token':self.server.token}).status,404)
        self.assertEqual(self.request('/api/overview',method='OPTIONS').status,403)

    def test_security_headers_and_local_assets(self):
        response=self.request('/')
        self.assertEqual(response.status,200);self.assertIn("default-src 'none'",response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['Cache-Control'],'no-store');self.assertEqual(response.headers['X-Frame-Options'],'DENY')
        text=response.read().decode();self.assertNotIn('https://',text)
        js=self.request('/app.js').read().decode();self.assertNotIn('innerHTML',js);self.assertNotIn('eval(',js)

    def test_excessive_query_is_friendly_error(self):
        self.assertEqual(self.request('/api/overview?'+'&'.join('p'+str(i)+'=x' for i in range(40)),{'X-Lens-Token':self.server.token}).status,400)

    def test_refresh_authorized(self):
        self.assertEqual(self.request('/api/refresh',{'X-Lens-Token':self.server.token},'POST').status,200)


if __name__=='__main__':unittest.main()
