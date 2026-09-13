"""Entirely invented history. No real IDs, transcripts, user paths or account information."""
import json
from datetime import datetime, timedelta, timezone


def write_demo(home):
    folder = home/'sessions'
    folder.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    for session, model, project, title, count in [
        ('demo-atlas', 'gpt-6-astra', '/demo/atlas', 'Build the release dashboard', 18),
        ('demo-garden', 'gpt-5.6-sol', '/demo/garden', 'Investigate the search index', 12),
        ('demo-notes', 'gpt-5.6-luna', '/demo/notes', 'Polish the keyboard navigation', 8),
        ('demo-unknown', 'example-unpriced-model', '/demo/lab', 'Explore a new model', 3)]:
        rows = []
        def emit(typ, p, n=0):
            rows.append({'timestamp': (day+timedelta(minutes=n)).isoformat().replace('+00:00','Z'), 'type': typ, 'payload': p})
        emit('session_meta', {'id': session, 'cwd': project, 'title': title, 'model_provider': 'openai', 'source': 'cli'})
        emit('response_item', {'type':'message','role':'user','id':session+'-prompt','content':[{'type':'input_text','text':'Please help with this task: '+title+'. Explain the decisions and validate the change.'}]})
        for i in range(count):
            turn = session+'-task-'+str(i//6+1)
            speed = 'fast' if session == 'demo-atlas' and i >= 12 else 'standard'
            if i%6 == 0:
                emit('event_msg', {'type':'task_started', 'turn_id':turn}, i)
                emit('turn_context', {'turn_id':turn, 'model':model, 'speed':speed, 'model_context_window':262144}, i)
            command = 'cat src/search.py' if i%3 == 0 else 'python -m unittest tests.test_search' if i%3 == 1 else 'rg --files src'
            emit('response_item', {'type':'function_call', 'name':'functions.exec_command', 'call_id':session+'-call-'+str(i), 'arguments':json.dumps({'cmd':command})}, i)
            if i%3 == 0:
                output = 'def search(query, index):\n    return index.lookup(query)\n'*600
            elif i%3 == 1:
                output = 'Process exited with code 1\nFAIL: test_empty_query\nAssertionError: expected an empty result\n'
            else:
                output = 'src/search.py\nsrc/index.py\nsrc/app.py\n<script>window.demoInjection = true</script>'
            emit('response_item', {'type':'function_call_output', 'call_id':session+'-call-'+str(i), 'output':output}, i)
            inp = 10000 + i*5300 + (17000 if i > 7 else 0)
            cached = int(inp*(0.3 if i%5 == 0 else 0.82))
            out = 1000 + (i*337)%4500
            emit('token_usage_record', {'response_id':session+'-response-'+str(i), 'thread_id':session, 'turn_id':turn,
                'usage':{'input_tokens':inp, 'cached_input_tokens':cached, 'output_tokens':out,
                         'reasoning_output_tokens':out*3//5, 'cache_write_input_tokens':0, 'total_tokens':inp+out}}, i)
            if i == 8:
                emit('compacted', {}, i)
        emit('response_item', {'type':'message','role':'assistant','id':session+'-answer','content':[{'type':'output_text','text':'The change is ready for review. Keep search local, show useful evidence, and run focused checks before the full release suite. Remaining work: verify keyboard navigation and empty states.'}]}, count+1)
        path = folder/(session+'.jsonl')
        if not path.exists():
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
