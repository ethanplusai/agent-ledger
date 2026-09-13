#!/usr/bin/env python3
"""Generate a large synthetic rollout in temporary storage; never commit its data."""
import argparse
import json
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lens.importer import Importer
from lens.storage import connect
from lens.query import Report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mib', type=int, default=256)
    args=parser.parse_args()
    if not 16 <= args.mib <= 8192:
        parser.error('--mib must be between 16 and 8192')
    with tempfile.TemporaryDirectory(prefix='lens-large-smoke-') as temp:
        root=Path(temp);folder=root/'history'/'sessions';folder.mkdir(parents=True)
        path=folder/'generated.jsonl'
        def row(typ,payload):return (json.dumps({'timestamp':'2026-09-12T12:00:00Z','type':typ,'payload':payload})+'\n').encode()
        with path.open('wb') as h:
            h.write(row('session_meta',{'id':'synthetic-large','model_provider':'openai','cwd':'/demo/large'}))
            h.write(row('turn_context',{'turn_id':'large-turn','model':'gpt-6-astra'}))
            index=0
            while h.tell()<args.mib*1024*1024:
                h.write(row('response_item',{'type':'function_call_output','call_id':'call-'+str(index),'output':'synthetic output\n'*4096}))
                h.write(row('token_usage_record',{'response_id':'response-'+str(index),'turn_id':'large-turn','usage':{'input_tokens':10000,'cached_input_tokens':8000,'output_tokens':1000,'reasoning_output_tokens':600,'cache_write_input_tokens':0,'total_tokens':11000}}))
                index+=1
            # A single 32 MiB complete line must be drained, not accumulated or parsed.
            for _ in range(512):h.write(b'x'*65536)
            h.write(b'\n')
        db=connect(root/'cache.sqlite3');start=time.monotonic();tracemalloc.start()
        result=Importer(db,root/'history').run();_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        totals=Report(db).totals({})
        assert totals['responses']==index and totals['total']==index*11000
        assert db.execute("SELECT COUNT(*) FROM diagnostics WHERE code='oversize'").fetchone()[0]==1
        assert peak<64*1024*1024, f'Unexpected Python allocation peak: {peak}'
        again=Importer(db,root/'history').run();assert again['records']==0 and again['changed']==0
        print(json.dumps({'generated_mib':round(path.stat().st_size/1024/1024,1),'unique_responses':index,'python_peak_mib':round(peak/1024/1024,2),'seconds':round(time.monotonic()-start,2),'unchanged_records_read':again['records'],'oversize_line_skipped':True},indent=2))
        db.close()


if __name__=='__main__':main()
