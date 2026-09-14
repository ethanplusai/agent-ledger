"""Entirely invented history. No real IDs, transcripts, user paths or account information."""
import json
from datetime import datetime, timedelta, timezone

# Invented dialogue. Each entry covers three recorded responses so the conversation interleaves with
# tool activity the way a real transcript does.
CONVERSATIONS = {
    'demo-atlas': [
        ('Build the release dashboard so the team can see the last ten builds at a glance. Keep it local.',
         'I read the build records. Status is stored as free text, so the same outcome appears as ok, OK and passed. '
         'I will normalize it in the loader and keep the raw value for debugging.'),
        ('Normalize it, but keep the raw value so we can trace odd rows.',
         'The loader now writes both status and raw_status. One test fails: test_empty_query expects an empty result '
         'for a blank search and currently raises instead.'),
        ('Fix the blank search case and run only that test.',
         'Blank search returns an empty list now. The focused test still fails, this time on the assertion message '
         'rather than the exception.'),
        ('Read the assertion carefully before changing anything else.',
         'The test asserts the result is an empty list, but the function returns an empty generator. '
         'I will materialize the result before returning it.'),
        ('Good catch. Make that change and check the dashboard renders with no builds.',
         'The empty state renders a short explanation instead of a blank panel. The full suite has not been run yet, '
         'only the focused test.'),
        ('Run the focused test once more, then summarize what is left.',
         'The focused test passes. Remaining work: keyboard navigation across the build rows, and an empty-state '
         'check at narrow widths.'),
    ],
    'demo-garden': [
        ('Search results feel stale after a rebuild. Investigate the index.',
         'The index writes a temp file and renames it. The reader caches the file handle at import time, so it keeps '
         'reading the old inode after the rename.'),
        ('That would explain it. Can we open the index lazily instead?',
         'Yes. Opening on first query costs one stat per call and removes the stale handle. I measured no noticeable '
         'difference on the sample corpus.'),
        ('Do it, and add a test that rebuilds and then queries.',
         'Added a test that writes, rebuilds, and queries in one process. It fails before the fix and passes after it.'),
        ('Anything else stale in that path?',
         'The term cache keyed by query string is never invalidated. It is bounded so it self-evicts, but a rebuild '
         'should clear it explicitly.'),
    ],
    'demo-notes': [
        ('Keyboard navigation in the notes list skips the delete control. Take a look.',
         'Delete sits inside a closed details element, so it is not in the tab order until the summary is opened. '
         'That is the expected pattern, but the summary has no visible focus ring.'),
        ('Add the focus ring and make sure arrow keys move between notes.',
         'Focus ring added. Arrow keys move between note rows with a roving tabindex, and Home and End jump to the ends.'),
        ('Check it at a narrow width too.',
         'At 360 pixels the rows stack and focus order follows the visual order. No horizontal scrolling.'),
    ],
    'demo-unknown': [
        ('Try the new model on a small task and tell me whether the output differs.',
         'The model is not in the bundled rate reference, so its credits are unavailable. Token counts are recorded '
         'normally. Output was similar on this task.'),
    ],
}


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
        script = CONVERSATIONS[session]
        for i in range(count):
            turn = session+'-task-'+str(i//6+1)
            step = i//3
            speed = 'fast' if session == 'demo-atlas' and i >= 12 else 'standard'
            if i%6 == 0:
                emit('event_msg', {'type':'task_started', 'turn_id':turn}, i)
                emit('turn_context', {'turn_id':turn, 'model':model, 'speed':speed, 'model_context_window':262144}, i)
            # The instruction opens a step; the report closes it just before that step's usage record,
            # which is the order a recorded transcript uses.
            if i%3 == 0 and step < len(script):
                emit('response_item', {'type':'message','role':'user','id':session+'-ask-'+str(step),
                                       'content':[{'type':'input_text','text':script[step][0]}]}, i)
            command = 'cat src/search.py' if i%3 == 0 else 'python -m unittest tests.test_search' if i%3 == 1 else 'rg --files src'
            emit('response_item', {'type':'function_call', 'name':'functions.exec_command', 'call_id':session+'-call-'+str(i), 'arguments':json.dumps({'cmd':command})}, i)
            if i%3 == 0:
                output = 'def search(query, index):\n    return index.lookup(query)\n'*600
            elif i%3 == 1:
                output = 'Process exited with code 1\nFAIL: test_empty_query\nAssertionError: expected an empty result\n'
            else:
                output = 'src/search.py\nsrc/index.py\nsrc/app.py\n<script>window.demoInjection = true</script>'
            emit('response_item', {'type':'function_call_output', 'call_id':session+'-call-'+str(i), 'output':output}, i)
            if i%3 == 2 and step < len(script):
                emit('response_item', {'type':'message','role':'assistant','id':session+'-said-'+str(step),
                                       'content':[{'type':'output_text','text':script[step][1]}]}, i)
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
