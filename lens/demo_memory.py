"""Synthetic conversations only. Never read a user's history for demo content."""
import json
from datetime import datetime, timedelta, timezone


def write_memory_demo(root):
    folder=root/'projects'/'demo';folder.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc)
    for day,(project,title,answer) in enumerate([
        ('/demo/atlas','Why did we choose SQLite for local search?','Decision: use SQLite FTS5 for local conversation search. It works offline and keeps setup to one command. Keep imported history separate from user-authored notes.'),
        ('/demo/atlas','Prepare the handoff for the search release.','Search and project filters are implemented. Tests cover empty results and malformed inputs. Remaining work: keyboard testing and clear error recovery. Avoid storing credentials.'),
        ('/demo/studio','What did we change in the build pipeline?','We reduced repeated full builds by running the targeted check first. A full suite still runs before release. This is a workflow decision, not a measured savings claim.'),
    ]):
        timestamp=(now-timedelta(days=day)).isoformat()
        shared={'sessionId':'demo-claude-'+str(day),'cwd':project,'timestamp':timestamp}
        rows=[dict(shared,type='user',uuid='user-'+str(day),message={'role':'user','content':title}),
              dict(shared,type='assistant',uuid='answer-'+str(day),requestId='request-'+str(day),message={'id':'message-'+str(day),'model':'claude-sonnet-demo','role':'assistant','content':[{'type':'text','text':answer}], 'usage':{'input_tokens':2000,'output_tokens':700,'cache_read_input_tokens':12000,'cache_creation_input_tokens':1000}})]
        (folder/('demo-'+str(day)+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
