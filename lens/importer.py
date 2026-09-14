"""Bounded JSONL ingestion. Never evaluate log text or read credentials/configuration."""
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from .accounting import FIELDS, normalize
from .privacy import scrub


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def short(value, limit=1024):
    return value[:limit] if isinstance(value, str) else ''


def observed(output, limit):
    """Hash text in chunks; non-text metadata gets a preview marker but contributes no text bytes."""
    blocks = output if isinstance(output, list) else [output]
    h = hashlib.sha256()
    size = chars = 0
    preview = []
    kept = 0
    omitted = False
    for block in blocks:
        if isinstance(block, str):
            text = block
        elif isinstance(block, dict):
            text = block.get('text')
            if not isinstance(text, str):
                marker = '[non-text block: ' + short(block.get('type'), 80) + '; content omitted]'
                preview.append(marker[:max(0, limit-kept)])
                kept += min(len(marker), max(0, limit-kept))
                omitted = True
                continue
        else:
            marker = '[unrecognized output; content omitted]'
            preview.append(marker[:max(0, limit-kept)])
            kept += min(len(marker), max(0, limit-kept))
            omitted = True
            continue
        if chars:
            h.update(b'\n'); size += 1; chars += 1
            if kept < limit:
                preview.append('\n'); kept += 1
        for n in range(0, len(text), 4096):
            chunk = text[n:n+4096]
            encoded = chunk.encode('utf-8', 'replace')
            h.update(encoded); size += len(encoded); chars += len(chunk)
            if kept < limit:
                preview.append(chunk[:limit-kept]); kept += len(chunk[:limit-kept])
    return size, chars, h.hexdigest(), ''.join(preview), chars > limit or omitted


CHUNK_STATUS_WINDOW = 1024


def chunk_exit_codes(blocks):
    """Exit statuses recorded inside result chunks, newest Codex exec format.

    One exec call runs a script, and the result carries one complete JSON object per command in it,
    each with its own recorded exit_code. Only a block that parses whole as such an object counts.
    No number is scraped out of surrounding prose, so an unrecognized result reports nothing.
    """
    codes = []
    for block in blocks:
        text = block if isinstance(block, str) else block.get('text') if isinstance(block, dict) else None
        # The status precedes the captured output, so a chunk that lacks it early is not one.
        # The window keeps a large unrelated result from being parsed just to be rejected.
        if not isinstance(text, str) or not text.startswith('{') or '"exit_code"' not in text[:CHUNK_STATUS_WINDOW]:
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            continue
        if isinstance(parsed, dict) and type(parsed.get('exit_code')) is int:
            codes.append(parsed['exit_code'])
    return codes


def action_info(item):
    name = short(item.get('name'), 200) or 'Unknown tool'
    args = item.get('arguments', item.get('input', ''))
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except (ValueError, RecursionError):
            parsed = None
    else:
        parsed = args
    command = parsed.get('cmd', parsed.get('command')) if isinstance(parsed, dict) else None
    operations = []
    if name in ('functions.exec', 'exec') and isinstance(args, str):
        operations = sorted(set(re.findall(r'\btools\.([A-Za-z_][A-Za-z_0-9]*)\s*\(', args)))[:30]
    # Only exact recognized commands are grouped; whitespace/argument differences survive.
    if isinstance(command, str) and name.split('.')[-1] in ('exec_command', 'shell_command', 'shell'):
        cwd = parsed.get('workdir', '')
        key = digest(dump([name, parsed]))
        return name, short(command, 2048), key, operations
    if isinstance(parsed, dict) and name.split('.')[-1] in ('read_file', 'read') and isinstance(parsed.get('path'), str):
        return name, short(parsed['path'], 2048), digest(dump([name, parsed])), operations
    return name, short(args if isinstance(args, str) else dump(args), 2048), None, operations


class Importer:
    folders = ('sessions', 'archived_sessions')
    agent_label = 'Codex'

    def accepts(self, record):
        return isinstance(record, dict) and isinstance(record.get('payload'), dict)

    def __init__(self, db, home, line_limit=8*1024*1024, preview_limit=4096, progress=None):
        self.db, self.home = db, Path(home).expanduser().resolve()
        self.line_limit, self.preview_limit = line_limit, preview_limit
        self.progress = progress or (lambda message: None)
        self.report = {'discovered': 0, 'changed': 0, 'records': 0, 'issues': []}
        self.started = self.last_progress = time.monotonic()

    def progress_tick(self, detail='', force=False):
        now = time.monotonic()
        if force or now-self.last_progress >= 2:
            elapsed = int(now-self.started)
            self.progress(f"{self.agent_label}: {self.report['discovered']:,} files checked; "
                          f"{self.report['changed']:,} changed; {elapsed//60}m {elapsed%60:02d}s"
                          + (f" · {detail}" if detail else ''))
            self.last_progress = now

    def diag(self, source, offset, code, message):
        self.db.execute('INSERT INTO diagnostics(source,offset,code,message) VALUES(?,?,?,?)',
                        (source, offset, code, message))

    def run(self):
        self.progress(f'Scanning {self.agent_label} history. Unchanged files will be skipped.')
        seen = set()
        for folder in self.folders:
            base = self.home / folder
            if not base.exists():
                continue
            def walk_error(_error):
                self.report['issues'].append('A history directory could not be read; prior cache retained.')
            for directory, dirs, files in os.walk(base, followlinks=False, onerror=walk_error):
                dirs[:] = [d for d in dirs if not (Path(directory)/d).is_symlink()]
                for name in files:
                    if not name.endswith('.jsonl'):
                        continue
                    path = Path(directory)/name
                    if path.is_symlink():
                        self.report['issues'].append('A symbolic-link rollout was skipped.')
                        continue
                    seen.add(str(path)); self.report['discovered'] += 1
                    try:
                        self.import_file(path)
                        self.progress_tick()
                    except OSError:
                        self.db.rollback()
                        self.report['issues'].append('A rollout could not be read; prior cache retained.')
        if not self.report['discovered']:
            self.report['issues'].append('No readable rollout files found in sessions/ or archived_sessions/. Check Codex home and permissions, or try --demo.')
        # Do not delete cache on discovery failure; mark absent contributions as uncertain.
        missing = self.db.execute('SELECT path FROM sources').fetchall()
        missing = [r for r in missing if str(self.home) + os.sep in r['path']]
        if any(r['path'] not in seen for r in missing):
            self.report['issues'].append('Some cached source files were not discovered. Their last imported data is retained; rebuild in a new cache to exclude it.')
        self.progress_tick('agent scan complete', force=True)
        return self.report

    def anchor(self, handle, offset):
        handle.seek(0)
        first = handle.read(min(4096, offset))
        handle.seek(max(0, offset-4096))
        return hashlib.sha256(first + handle.read(min(4096, offset))).hexdigest()

    def checkpoint(self, sid, handle, offset, state, stat):
        anchor = self.anchor(handle, offset)
        self.db.execute('UPDATE sources SET offset=?,state=?,anchor=?,size=?,mtime=? WHERE id=?',
                        (offset, dump(state), anchor, stat.st_size, stat.st_mtime_ns, sid))
        self.db.commit()
        handle.seek(offset)

    def import_file(self, path):
        stat = path.stat()
        identity = f'{stat.st_dev}:{stat.st_ino}'
        row = self.db.execute('SELECT * FROM sources WHERE path=?', (str(path),)).fetchone()
        if row and row['identity'] == identity and row['size'] == stat.st_size and row['mtime'] == stat.st_mtime_ns and json.loads(row['state']).get('settled'):
            return
        self.report['changed'] += 1
        self.progress_tick(f"reading a {stat.st_size/(1024*1024):,.1f} MiB file")
        with path.open('rb') as handle:
            changed = row and (row['identity'] != identity or stat.st_size < row['offset'] or
                               self.anchor(handle, row['offset']) != row['anchor'] or
                               (stat.st_size == row['size'] and stat.st_mtime_ns != row['mtime']))
            if changed:
                self.db.execute('DELETE FROM sources WHERE id=?', (row['id'],))
                row = None
            if not row:
                sid = self.db.execute('INSERT INTO sources(path,identity) VALUES(?,?)', (str(path), identity)).lastrowid
                state = {'session': 'source-'+str(sid), 'provider': 'unknown', 'turn': 'unassigned',
                         'boundary': 0, 'baseline': None, 'native_since': False, 'gap': False}
                self.db.execute('INSERT INTO sessions(source,sid,project,title,provider) VALUES(?,?,?,?,?)',
                                (sid, state['session'], '(working directory unavailable)', '', 'unknown'))
                offset = 0
            else:
                sid, state, offset = row['id'], json.loads(row['state']), row['offset']
            state['settled'] = False
            handle.seek(offset)
            count = 0
            while True:
                start = handle.tell()
                line = handle.readline(self.line_limit+1)
                if not line:
                    break
                if len(line) > self.line_limit:
                    # Drain without accumulating. An incomplete enormous tail is retried next refresh.
                    while line and not line.endswith(b'\n'):
                        line = handle.readline(65536)
                    if not line.endswith(b'\n'):
                        break
                    self.diag(sid, start, 'oversize', 'Record exceeds configured line limit; content skipped. Usage coverage may be incomplete.')
                    state['gap'] = True
                elif not line.endswith(b'\n'):
                    break
                else:
                    try:
                        record = json.loads(line)
                        if not self.accepts(record):
                            raise ValueError('Unknown envelope')
                    except (ValueError, UnicodeError, RecursionError):
                        self.diag(sid, start, 'malformed', 'Malformed complete JSON record skipped; possible coverage gap.')
                        state['gap'] = True
                    else:
                        self.record(sid, start, state, record)
                        self.report['records'] += 1
                offset = handle.tell(); count += 1
                if count % 500 == 0:
                    self.checkpoint(sid, handle, offset, state, stat)
                    self.progress_tick(f"current file {offset/(1024*1024):,.1f} / "
                                       f"{stat.st_size/(1024*1024):,.1f} MiB "
                                       f"({min(100, offset*100//max(1,stat.st_size))}%) · checkpoint saved")
            state['settled'] = True
            self.checkpoint(sid, handle, offset, state, stat)

    def context(self, sid, turn, offset):
        return self.db.execute('''SELECT * FROM contexts WHERE source=? AND turn=?
          ORDER BY CASE WHEN offset<=? THEN 0 ELSE 1 END,
          CASE WHEN offset<=? THEN -offset ELSE offset END LIMIT 1''', (sid, turn, offset, offset)).fetchone()

    def record(self, sid, offset, state, record):
        p, typ = record['payload'], record.get('type')
        from .memory import capture_codex
        capture_codex(self.db, sid, offset, record)
        timestamp = short(record.get('timestamp'), 64)
        try:
            parsed_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if parsed_time.tzinfo is None:
                raise ValueError('Timestamp has no timezone')
            timestamp = parsed_time.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
        except (ValueError, OverflowError):
            timestamp = ''
            self.diag(sid, offset, 'timestamp', 'Timestamp missing or invalid; activity excluded from date-limited scopes.')
        if typ == 'session_meta':
            state['session'] = short(p.get('id') or p.get('session_id')) or state['session']
            state['provider'] = short(p.get('model_provider')) or 'unknown'
            parent = short(p.get('parent_thread_id') or p.get('parent_id'))
            state['parent'] = parent
            state['cwd'] = short(p.get('cwd'), 4096)
            self.db.execute('UPDATE sessions SET sid=?,project=?,title=?,parent=?,relationship=?,provider=? WHERE source=?',
                (state['session'], short(p.get('cwd'), 4096) or '(working directory unavailable)',
                 scrub(short(p.get('title'))), parent, short(p.get('source') if isinstance(p.get('source'), str) else dump(p.get('source'))), state['provider'], sid))
        elif typ == 'turn_context':
            turn = short(p.get('turn_id')) or state['turn']
            state['turn'] = turn
            if p.get('cwd'):
                state['cwd'] = short(p.get('cwd'), 4096)
            model = short(p.get('model')) or None
            speed = short(p.get('speed') or p.get('service_tier')) or None
            limit = p.get('model_context_window', p.get('context_window'))
            limit = limit if type(limit) is int and 0 < limit <= 2**53-1 else None
            self.db.execute('INSERT OR REPLACE INTO contexts VALUES(?,?,?,?,?,?,?)',
                            (sid, turn, offset, timestamp, model, speed, limit))
            # Backfill only records with no preceding context, never apply a later speed change retroactively.
            self.db.execute('''UPDATE appearances SET model=COALESCE(model,?),speed=COALESCE(speed,?),
                               context_limit=COALESCE(context_limit,?) WHERE source=? AND turn=? AND offset<?
                               AND NOT EXISTS(SELECT 1 FROM contexts c WHERE c.source=appearances.source
                                              AND c.turn=appearances.turn AND c.offset<=appearances.offset)''',
                            (model, speed, limit, sid, turn, offset))
        elif typ == 'token_usage_record':
            turn = short(p.get('turn_id')) or state['turn']
            rid = short(p.get('response_id'))
            if not rid:
                self.diag(sid, offset, 'missing_identity', 'Native usage has no response ID; excluded to avoid unsafe deduplication.')
                state['gap'] = True
                return
            usage = normalize(p.get('usage'))
            # Suppress proven mirrors. Timestamp alone is not a response identity.
            last = state.get('last_legacy')
            snapshot = p.get('thread_token_usage')
            if last and ((last['timestamp'] == timestamp and last['usage'] == usage) or
                         (isinstance(snapshot, dict) and normalize(snapshot) == last['cumulative'])):
                self.db.execute('DELETE FROM appearances WHERE source=? AND offset=?', (sid, last['offset']))
                self.db.execute("DELETE FROM diagnostics WHERE source=? AND offset=? AND code LIKE 'legacy%'", (sid, last['offset']))
                state.pop('last_legacy', None)
                if last['usage'] != usage:
                    self.diag(sid, offset, 'mixed_overlap', 'Native snapshot overlaps a legacy interval of different size; uncertain legacy interval excluded.')
            elif last and not isinstance(snapshot, dict) and last['usage'] == usage and last.get('turn') == turn:
                self.db.execute('DELETE FROM appearances WHERE source=? AND offset=?', (sid, last['offset']))
                self.diag(sid, offset, 'mixed_overlap', 'Equal legacy/native usage without an identity-bearing snapshot may be mirrored; lower-confidence legacy amount excluded.')
                state.pop('last_legacy', None)
            key = dump([state['provider'], rid])
            self.add_usage(sid, offset, state, timestamp, turn, rid, key, usage, 'native', p)
            # Keep a bounded native sum to check that the next legacy interval is a mirror.
            if not self.db.execute('SELECT 1 FROM appearances WHERE source=? AND key=? AND offset<?', (sid, key, offset)).fetchone():
                sums = state.setdefault('native_sum', {'input_tokens': 0, 'output_tokens': 0})
                for field in sums:
                    value = usage[field]
                    sums[field] = sums[field] + value if sums[field] is not None and value is not None else None
            state['native_since'] = True
            self.db.execute('''UPDATE activities SET following=?,association='Chronological correlation'
              WHERE source=? AND turn=? AND following IS NULL AND offset<? AND kind='output' ''',
                            (key, sid, turn, offset))
            self.db.execute('''UPDATE activities SET following=? WHERE source=? AND following=?''',
                            (key, sid, 'explicit:'+rid))
        elif typ == 'compacted' or (typ in ('event_msg', 'response_item') and p.get('type') in ('compaction', 'context_compacted')):
            state['boundary'] += 1
            self.activity(sid, offset, state, timestamp, {'type': 'boundary', 'call_id': 'boundary-'+str(offset)})
        elif typ == 'event_msg':
            event = p.get('type')
            if event == 'task_started':
                state['turn'] = short(p.get('turn_id')) or 'task-'+str(offset)
            elif event == 'user_message' and state['turn'] == 'unassigned':
                state['turn'] = 'task-'+str(offset)
            elif event == 'task_complete':
                state['turn'] = 'unassigned'
            elif event == 'token_count':
                self.legacy(sid, offset, state, timestamp, p)
            elif event == 'item_completed' and isinstance(p.get('item'), dict):
                self.activity(sid, offset, state, timestamp, p['item'])
        elif typ == 'response_item':
            self.activity(sid, offset, state, timestamp, p)

    def add_usage(self, sid, offset, state, timestamp, turn, rid, key, usage, kind, p):
        ctx = self.context(sid, turn, offset)
        model = short(p.get('model')) or (ctx['model'] if ctx else None)
        speed = short(p.get('speed') or p.get('service_tier')) or (ctx['speed'] if ctx else None)
        if kind != 'native':
            # A cumulative observation does not establish one model/speed for all included work.
            model = speed = None
        for error in usage['errors']:
            self.diag(sid, offset, 'invalid_usage', error)
        self.db.execute('''INSERT INTO appearances(source,offset,key,rid,turn,timestamp,model,speed,provider,
            context_limit,usage,signature,kind,owner) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (sid, offset, key, rid, turn, timestamp, model, speed, state['provider'], ctx['context_limit'] if ctx else None,
             dump(usage), digest(dump({k: usage[k] for k in FIELDS})), kind, short(p.get('thread_id')) or state['session']))

    def legacy(self, sid, offset, state, timestamp, payload):
        info = payload.get('info')
        if not isinstance(info, dict) or not isinstance(info.get('total_token_usage'), dict):
            return
        current = normalize(info['total_token_usage'])
        previous = state.get('baseline')
        state['baseline'] = {k: current[k] for k in FIELDS}
        native = state.pop('native_since', False)
        state['native_since'] = False
        if native:
            sums = state.pop('native_sum', {})
            mismatch = current['errors'] or any(current[k] is None or
                current[k] - ((previous or {}).get(k) or 0) != sums.get(k) for k in ('input_tokens', 'output_tokens'))
            if mismatch:
                self.diag(sid, offset, 'mixed_range', 'Legacy interval overlaps native usage but is not a matching mirror; uncertain remainder excluded.')
            state['gap'] = False
            return
        if current['errors']:
            self.diag(sid, offset, 'legacy_invalid', 'Inconsistent cumulative snapshot; establishes no usage interval.')
            state['baseline'] = None
            state['gap'] = True
            return
        if state.get('parent'):
            self.diag(sid, offset, 'legacy_fork', 'Legacy counters in a child may include copied history; excluded because response identity is unavailable.')
            return
        if state.pop('gap', False):
            self.diag(sid, offset, 'legacy_gap', 'Counter after a skipped record establishes a new baseline; gap excluded.')
            return
        if previous:
            delta = {k: current[k]-previous[k] if current[k] is not None and previous.get(k) is not None else None for k in FIELDS}
            if any(v is not None and v < 0 for v in delta.values()):
                self.diag(sid, offset, 'legacy_reset', 'Cumulative counter reset; new baseline only.')
                return
            usage = normalize(delta)
            if usage['errors']:
                self.diag(sid, offset, 'legacy_delta', 'Inconsistent cumulative delta excluded; new baseline established.')
                return
            if usage['displayed_total'] == 0:
                return
            kind = 'legacy_interval'
        else:
            usage, kind = current, 'legacy_baseline'
        self.diag(sid, offset, kind, 'Session-level cumulative amount; no individual response attribution. May overlap history in other files.')
        # Equal session counters copied into another source share a key, but unidentified intervals remain partial.
        key = 'legacy:'+digest(dump([state['session'], previous, state['baseline']]))
        self.add_usage(sid, offset, state, timestamp, state['turn'], '', key, usage, kind, {})
        state['last_legacy'] = {'offset': offset, 'timestamp': timestamp, 'usage': usage, 'cumulative': current, 'turn': state['turn']}

    def activity(self, sid, offset, state, timestamp, p):
        typ = p.get('type')
        if typ not in ('function_call', 'custom_tool_call', 'function_call_output', 'custom_tool_call_output', 'boundary'):
            return
        kind = 'output' if typ.endswith('_output') else ('boundary' if typ == 'boundary' else 'call')
        turn = short(p.get('turn_id')) or state['turn']
        call = short(p.get('call_id') or p.get('id')) or 'unidentified-'+str(offset)
        tool, action, action_key, operations = action_info(p)
        if action_key:
            action_key = digest(dump([action_key, state.get('cwd', '')]))
        if kind == 'call':
            data = (0, 0, '', '', False)
        else:
            data = observed(p.get('output', ''), self.preview_limit)
            matched = self.db.execute("SELECT * FROM activities WHERE source=? AND call_id=? AND kind='call'", (sid, call)).fetchone()
            if matched:
                turn = short(p.get('turn_id')) or matched['turn']
                tool, action, action_key = matched['tool'], matched['action'], matched['action_key']
                operations = json.loads(matched['operations'])
        size, chars, hash_value, preview, truncated = data
        # Exit code is established by an explicit field or the recognized exec wrapper.
        out = p.get('output')
        code = out.get('exit_code') if isinstance(out, dict) else None
        if isinstance(out, dict) and 'output' in out:
            size, chars, hash_value, preview, truncated = observed(out['output'], self.preview_limit)
        content = out.get('output') if isinstance(out, dict) and 'output' in out else out
        blocks = content if isinstance(content, list) else [content]
        if kind == 'output' and any(not isinstance(b, str) and
                not (isinstance(b, dict) and isinstance(b.get('text'), str)) for b in blocks):
            action_key = None  # Omitted non-text payloads cannot establish repeated unchanged content.
        failure = bool(type(code) is int and code != 0)
        match = re.search(r'(?m)^Process exited with code ([0-9]+)\s*$', preview)
        if match:
            failure = int(match.group(1)) != 0
        elif code is None and kind == 'output':
            # A non-zero status recorded for any command in the script is an explicit failure signal.
            # A recorded zero is equally explicit, so it settles the result rather than leaving it unknown.
            chunk_codes = chunk_exit_codes(blocks)
            if chunk_codes:
                failure = any(value != 0 for value in chunk_codes)
        old = self.db.execute('SELECT hash FROM activities WHERE source=? AND call_id=? AND kind=?', (sid, call, kind)).fetchone()
        if old:
            if kind == 'output' and old['hash'] != hash_value:
                self.diag(sid, offset, 'activity_conflict', 'Mirrored tool result differs; first observed result retained.')
            return
        explicit = short(p.get('response_id'))
        following = None
        if explicit:
            known = self.db.execute('SELECT key FROM appearances WHERE source=? AND rid=? LIMIT 1', (sid, explicit)).fetchone()
            following = known['key'] if known else 'explicit:'+explicit
        self.db.execute('''INSERT INTO activities(source,offset,turn,timestamp,call_id,kind,tool,action,action_key,
            preview,bytes,chars,hash,truncated,failed,boundary,following,association,operations)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (sid, offset, turn, timestamp, call, kind, tool, scrub(action), action_key, scrub(preview), size, chars,
             hash_value, int(truncated or 'truncated' in preview.lower()), int(failure), state['boundary'],
             following, 'Recorded response identifier' if explicit else 'Unassociated', dump(operations)))
        if kind == 'call':
            self.db.execute("UPDATE activities SET tool=?,action=?,action_key=CASE WHEN truncated=0 THEN ? ELSE NULL END,operations=? WHERE source=? AND call_id=? AND kind='output'",
                            (tool, action, action_key, dump(operations), sid, call))
