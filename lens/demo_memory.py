"""Synthetic conversations only. Never read a user's history for demo content."""
import json
from datetime import datetime, timedelta, timezone

# Invented Claude Code sessions. Each one carries tool activity and more than one recorded response so
# the tool breakdown, the agent comparison and the conversation replay all have something to show.
SESSIONS = [
    ('/demo/atlas', 'Why did we choose SQLite for local search?', [
        ('read', 'src/search/index.py', 'class Index:\n    def lookup(self, query):\n        return self.db.execute(...)\n', False),
        ('shell', 'python -m pytest tests/test_index.py -q', '4 passed in 0.31s\n', False),
    ], 'Decision: use SQLite FTS5 for local conversation search. It works offline and keeps setup to one command. '
       'Keep imported history separate from user-authored notes.'),
    ('/demo/atlas', 'Prepare the handoff for the search release.', [
        ('Grep', 'rg "def search" --type py', 'src/search/api.py:12:def search(query, index):\n', False),
        ('shell', 'python -m pytest tests/ -q', 'Process exited with code 1\nFAILED tests/test_api.py::test_malformed\n', True),
        ('shell', 'python -m pytest tests/test_api.py -q', '9 passed in 1.02s\n', False),
    ], 'Search and project filters are implemented. Tests cover empty results and malformed inputs. '
       'Remaining work: keyboard testing and clear error recovery. Avoid storing credentials.'),
    ('/demo/studio', 'What did we change in the build pipeline?', [
        ('read', 'ci/pipeline.yml', 'steps:\n  - run: make build\n  - run: make test\n', False),
        ('shell', 'make test', 'ok\n', False),
    ], 'We reduced repeated full builds by running the targeted check first. A full suite still runs before release. '
       'This is a workflow decision, not a measured savings claim.'),
]


def write_memory_demo(root):
    folder = root/'projects'/'demo'
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    for day, (project, title, calls, answer) in enumerate(SESSIONS):
        rows = []
        clock = now-timedelta(days=day)

        def emit(row, minutes):
            shared = {'sessionId': 'demo-claude-'+str(day), 'cwd': project,
                      'timestamp': (clock+timedelta(minutes=minutes)).isoformat()}
            rows.append(dict(shared, **row))

        def usage(step):
            # Recorded context grows as the conversation carries earlier turns forward.
            return {'input_tokens': 1800+step*400, 'output_tokens': 620+step*180,
                    'cache_read_input_tokens': 9000+step*7400, 'cache_creation_input_tokens': 1000}

        emit({'type': 'user', 'uuid': 'u-'+str(day)+'-0',
              'message': {'role': 'user', 'content': title}}, 0)
        for step, (tool, action, output, failed) in enumerate(calls):
            call = 'tool-'+str(day)+'-'+str(step)
            arguments = {'file_path': action} if tool == 'read' else {'command': action}
            name = {'read': 'Read', 'shell': 'Bash'}.get(tool, tool)
            emit({'type': 'assistant', 'uuid': 'a-'+str(day)+'-'+str(step), 'requestId': 'req-'+str(day)+'-'+str(step),
                  'message': {'id': 'message-'+str(day)+'-'+str(step), 'model': 'claude-sonnet-demo', 'role': 'assistant',
                              'content': [{'type': 'text', 'text': 'Checking '+action+' before answering.'},
                                          {'type': 'tool_use', 'id': call, 'name': name, 'input': arguments}],
                              'usage': usage(step)}}, step*2+1)
            emit({'type': 'user', 'uuid': 'r-'+str(day)+'-'+str(step),
                  'message': {'role': 'user', 'content': [dict({'type': 'tool_result', 'tool_use_id': call,
                                                                'content': output}, **({'is_error': True} if failed else {}))]}}, step*2+2)
        if day == 1:
            emit({'type': 'system', 'subtype': 'compact_boundary', 'uuid': 'c-'+str(day)}, len(calls)*2+1)
        emit({'type': 'assistant', 'uuid': 'a-'+str(day)+'-final', 'requestId': 'req-'+str(day)+'-final',
              'message': {'id': 'message-'+str(day)+'-final', 'model': 'claude-sonnet-demo', 'role': 'assistant',
                          'content': [{'type': 'text', 'text': answer}], 'usage': usage(len(calls))}}, len(calls)*2+2)
        (folder/('demo-'+str(day)+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
