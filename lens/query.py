"""Scope-aware queries; union appearances before totaling, page evidence separately."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from .accounting import estimate


class Report:
    def __init__(self, db):
        self.db = db

    def filters(self, args, alias='a'):
        where, values = [], []
        for key, column in [('from', 'timestamp'), ('to', 'timestamp'), ('model', 'model')]:
            value = args.get(key)
            if value:
                if key == 'from':
                    where.append(f'{alias}.{column}>=?'); values.append(value)
                elif key == 'to':
                    where.append(f'{alias}.{column}<=?'); values.append(value+'T23:59:59.999999Z')
                else:
                    where.append(f'{alias}.{column}=?'); values.append(value)
        if args.get('agent') in ('claude','codex'):
            where.append(f"{alias}.provider {'=' if args['agent']=='claude' else '!='} 'anthropic'")
        if args.get('project'):
            where.append(f'{alias}.source IN (SELECT source FROM sessions WHERE project=?)')
            values.append(args['project'])
        if args.get('session'):
            if args.get('descendants') == '1':
                where.append(f'''{alias}.source IN (WITH RECURSIVE family(sid) AS (
                  SELECT ? UNION SELECT s.sid FROM sessions s JOIN family f ON s.parent=f.sid)
                  SELECT source FROM sessions WHERE sid IN family)''')
            else:
                where.append(f'{alias}.source IN (SELECT source FROM sessions WHERE sid=?)')
            values.append(args['session'])
        if args.get('turn'):
            where.append(f'{alias}.turn=?'); values.append(args['turn'])
        return ' AND '.join(where) or '1', values

    def scoped(self, args):
        where, values = self.filters(args)
        # Pick the appearance in scope, while detecting conflicts across all appearances.
        return f'''SELECT a.*, (SELECT COUNT(DISTINCT signature)>1 FROM appearances b WHERE b.key=a.key) AS conflict
        FROM appearances a WHERE a.id IN (SELECT MIN(a.id) FROM appearances a WHERE {where} GROUP BY a.key)''', values

    def response(self, row):
        result = dict(row)
        result['usage'] = json.loads(result['usage'])
        if result['conflict']:
            result['usage']['errors'].append('Conflicting duplicate response ID; excluded from totals')
            result['usage']['displayed_total'] = None
        # A provider+ID match with inconsistent recorded context cannot establish a rate.
        variants = self.db.execute('''SELECT COUNT(DISTINCT model),COUNT(DISTINCT speed)
                                    FROM appearances WHERE key=?''', (result['key'],)).fetchone()
        if variants[0] > 1 or variants[1] > 1:
            result['context_conflict'] = True
        result['estimate'] = estimate(result['usage'], result['model'], result['speed'], result['timestamp'], result['provider'])
        if result.get('context_conflict'):
            result['estimate']['total'] = result['estimate']['parts'] = result['estimate']['components'] = None
            result['estimate']['reason'] = 'Conflicting model/speed appearances'
        result.pop('signature', None)
        return result

    def totals(self, args):
        sql, values = self.scoped(args)
        totals = dict(input=0, output=0, cached=0, reasoning=0, total=0, responses=0,
                      records=0, invalid=0, legacy=0, priced=0, unpriced=0, inherited=0)
        cache_known = reasoning_known = True
        credits = Decimal(0)
        components = {key: Decimal(0) for key in ('uncached_input', 'cached_input', 'output')}
        for row in self.db.execute(sql, values):
            r = self.response(row); u = r['usage']
            totals['records'] += 1
            totals['responses'] += r['kind'] == 'native'
            totals['legacy'] += r['kind'] != 'native'
            if u['errors']:
                totals['invalid'] += 1; totals['unpriced'] += 1
                continue
            totals['input'] += u['input_tokens']; totals['output'] += u['output_tokens']
            totals['total'] += u['displayed_total']
            if u['cached_input_tokens'] is None:
                cache_known = False
            else:
                totals['cached'] += u['cached_input_tokens']
            if u['reasoning_output_tokens'] is None:
                reasoning_known = False
            else:
                totals['reasoning'] += u['reasoning_output_tokens']
            if r['estimate']['total'] is None:
                totals['unpriced'] += 1
            else:
                totals['priced'] += 1; credits += Decimal(r['estimate']['total'])
                for key, value in r['estimate']['components'].items():
                    components[key] += Decimal(value)
        totals['credits'] = str(credits) if totals['priced'] else None
        totals['credit_components'] = {key: str(value) for key, value in components.items()} if totals['priced'] else None
        totals['cache_share'] = totals['cached']/totals['input'] if cache_known and totals['input'] else None
        if not cache_known:
            totals['cached'] = None
        if not reasoning_known:
            totals['reasoning'] = None
        totals['credit_status'] = 'partial' if totals['unpriced'] or totals['legacy'] else 'reference'
        return totals

    def overview(self, args):
        where, values = self.filters(args)
        # Session cards summarize the appearances in the active filter, including empty sources separately.
        sessions = []
        sql = f'''SELECT s.sid,MIN(s.project) project,MAX(s.title) title,MAX(s.parent) parent,
                 MAX(s.relationship) relationship,MIN(a.timestamp) first,MAX(a.timestamp) last
                 FROM sessions s JOIN appearances a ON a.source=s.source WHERE {where} GROUP BY s.sid'''
        for row in self.db.execute(sql, values):
            r = dict(row)
            scope = dict(args, session=r['sid'])
            r['totals'] = self.totals(scope)
            r['models'] = [x[0] or 'Unknown model' for x in self.db.execute(
                'SELECT DISTINCT a.model FROM appearances a WHERE '+self.filters(scope)[0], self.filters(scope)[1])]
            r['diagnostics'] = self.db.execute('SELECT COUNT(*) FROM diagnostics WHERE source IN (SELECT source FROM sessions WHERE sid=?)', (r['sid'],)).fetchone()[0]
            sessions.append(r)
        def rank(r):
            t = r['totals']
            if args.get('sort') == 'tokens':
                return (0, -t['total'])
            return (t['credit_status'] == 'partial' or t['credits'] is None, -Decimal(t['credits'] or '0'))
        sessions.sort(key=rank)
        offset = page_offset(args)
        if args.get('focus'):
            position=next((i for i,s in enumerate(sessions) if s['sid']==args['focus']),None)
            if position is not None:offset=position//50*50
        return {'sessions': sessions[offset:offset+50], 'count': len(sessions), 'offset': offset,
                'totals': self.totals(args), 'filters': args}

    def options(self):
        latest = self.db.execute('SELECT MAX(timestamp) FROM appearances').fetchone()[0]
        today = datetime.now(timezone.utc).date()
        return {'projects': [r[0] for r in self.db.execute('SELECT DISTINCT project FROM sessions ORDER BY project')],
                'models': [r[0] for r in self.db.execute('SELECT DISTINCT model FROM appearances WHERE model IS NOT NULL ORDER BY model')],
                'from': (today-timedelta(days=29)).isoformat(), 'to': today.isoformat(), 'latest': latest,
                'sources': self.db.execute('SELECT COUNT(*) FROM sources').fetchone()[0],
                'empty_sources': self.db.execute('SELECT COUNT(*) FROM sources s WHERE NOT EXISTS(SELECT 1 FROM appearances a WHERE a.source=s.id)').fetchone()[0]}

    def session(self, args):
        sql, values = self.scoped(args)
        offset = page_offset(args)
        # Window before pagination: the first row on page two still has a baseline.
        # Compare matching responses in the same source, never across descendants.
        ranked = """WITH native AS ("""+sql+""" AND a.kind='native'), ranked AS (
            SELECT *,LAG(usage) OVER w previous_usage,LAG(conflict) OVER w previous_conflict
            FROM native WINDOW w AS (PARTITION BY source ORDER BY timestamp,id))
            SELECT * FROM ranked ORDER BY timestamp,id LIMIT 100 OFFSET ?"""
        rows = []
        for row in self.db.execute(ranked, values+[offset]):
            r = self.response(row)
            previous = json.loads(r.pop('previous_usage') or 'null')
            previous_conflict = r.pop('previous_conflict')
            u = r['usage']
            valid = not u['errors']
            before = previous['input_tokens'] if previous and not previous['errors'] and not previous_conflict else None
            r['context'] = {'input': u['input_tokens'] if valid else None,
                            'previous_input': before,
                            'change': u['input_tokens']-before if valid and before is not None else None,
                            'limit_share': u['input_tokens']/r['context_limit'] if valid and r['context_limit'] else None}
            rows.append(r)
        valid_sql = "SELECT * FROM ("+sql+") WHERE kind='native' AND conflict=0 AND json_array_length(usage,'$.errors')=0"
        context_summary = dict(self.db.execute("SELECT COUNT(*) count,MAX(json_extract(usage,'$.input_tokens')) peak,AVG(json_extract(usage,'$.input_tokens')) average FROM ("+valid_sql+")", values).fetchone())
        largest = [self.response(r) for r in self.db.execute(valid_sql+" ORDER BY json_extract(usage,'$.displayed_total') DESC,id LIMIT 3", values)]
        scope = dict(args); scope.pop('turn', None)
        where, params = self.filters(scope)
        turns = [dict(r) for r in self.db.execute(f'''SELECT turn,MIN(timestamp) first,COUNT(DISTINCT key) records
            FROM appearances a WHERE {where} GROUP BY turn ORDER BY first''', params)]
        # Compaction markers come from the same sources as the paged responses, so the chart can
        # show where recorded context was reset. A boundary is an observed record, not an inference.
        sources = sorted({r['source'] for r in rows})
        boundaries = []
        if sources:
            marks = ','.join('?'*len(sources))
            boundaries = [dict(x) for x in self.db.execute(
                f"""SELECT source,offset,timestamp,boundary FROM activities
                    WHERE kind='boundary' AND source IN ({marks}) ORDER BY source,offset""", sources)]
        return {'responses': rows, 'context_summary': context_summary, 'largest': largest, 'totals': self.totals(args), 'turns': turns, 'offset': offset,
                'boundaries': boundaries,
                'count': self.db.execute('SELECT COUNT(*) FROM ('+sql+") WHERE kind='native'", values).fetchone()[0]}

    def providers(self, args):
        """Per-agent totals in the active filter. Claude usage has no Codex credit conversion."""
        rows = []
        # An active agent filter narrows the comparison to that agent; one side alone is not a comparison.
        requested = args.get('agent') if args.get('agent') in ('claude', 'codex') else None
        for agent, label in (('claude', 'Claude Code'), ('codex', 'Codex')):
            if requested and agent != requested:
                continue
            scope = dict(args, agent=agent)
            where, values = self.filters(scope)
            sessions = self.db.execute(f'''SELECT COUNT(DISTINCT s.sid) FROM sessions s
                JOIN appearances a ON a.source=s.source WHERE {where}''', values).fetchone()[0]
            activity = self.db.execute(f'''SELECT COUNT(*) calls, SUM(COALESCE(t.failed,0)) failures
                FROM activities t WHERE t.kind='output' AND EXISTS
                (SELECT 1 FROM appearances a WHERE a.source=t.source AND a.key=t.following AND {where})''', values).fetchone()
            rows.append({'agent': agent, 'label': label, 'sessions': sessions,
                         'results': activity['calls'], 'failures': activity['failures'] or 0,
                         'totals': self.totals(scope)})
        return {'providers': rows, 'totals': self.totals(args),
                'notice': 'Per-agent totals in the active filter. Token volume is comparable; credits are not, because '
                          'Claude usage has no verified credit rate. Failure counts only include results whose source '
                          'recorded an exit status or error flag, which differs between agents.'}

    def tools(self, args):
        """Observed tool results per tool, with failures and result sizes, for activity linked to a response in scope.

        Only result records carry an observed size and a failure flag, and only result records are associated
        with a response, so the count is observed results rather than every attempted call.
        """
        where, values = self.filters(args)
        base = f'''FROM activities t WHERE t.kind='output' AND EXISTS
            (SELECT 1 FROM appearances a WHERE a.source=t.source AND a.key=t.following AND {where})'''
        items = [dict(r) for r in self.db.execute(f'''SELECT COALESCE(t.tool,'Unknown tool') tool,
            COUNT(*) results, SUM(COALESCE(t.failed,0)) failures,
            SUM(COALESCE(t.bytes,0)) bytes, MAX(COALESCE(t.bytes,0)) largest,
            SUM(COALESCE(t.truncated,0)) truncated
            {base} GROUP BY t.tool ORDER BY results DESC, bytes DESC LIMIT 50''', values)]
        for row in items:
            row['failure_rate'] = row['failures']/row['results'] if row['results'] else None
        totals = {key: sum(row[key] for row in items) for key in ('results', 'failures', 'bytes', 'truncated')}
        totals['failure_rate'] = totals['failures']/totals['results'] if totals['results'] else None
        totals['tools'] = len(items)
        totals['largest'] = max((row['largest'] for row in items), default=0)
        return {'items': items, 'totals': totals,
                'notice': 'Observed tool results linked to a response in the active filter. A result counts as failed '
                          'only where an exit status or error flag was recorded; tools that report neither show no '
                          'failures rather than none having occurred. Result bytes are not billed tokens, and a failed '
                          'result can be a deliberate check.'}

    def locate(self, args):
        sql, values = self.scoped(args)
        row = self.db.execute("""WITH ranked AS (
            SELECT id,key,ROW_NUMBER() OVER(ORDER BY timestamp,id)-1 position
            FROM ("""+sql+""") WHERE kind='native')
            SELECT id,position FROM ranked WHERE key=(SELECT key FROM appearances WHERE id=?)""",
            values+[args.get('id')]).fetchone()
        return {'id': row['id'], 'offset': row['position']//100*100} if row else {'error': 'Response is outside the selected scope'}

    def detail(self, args):
        row = self.db.execute('SELECT a.*, (SELECT COUNT(DISTINCT signature)>1 FROM appearances b WHERE b.key=a.key) conflict FROM appearances a WHERE id=?', (args.get('id'),)).fetchone()
        if not row:
            return {'error': 'Response not found'}
        r = self.response(row)
        offset = page_offset(args)
        activities = [dict(x) for x in self.db.execute('''SELECT * FROM activities WHERE source=? AND following=?
                                                        ORDER BY offset LIMIT 50 OFFSET ?''', (r['source'], r['key'], offset))]
        provenance = [dict(x) for x in self.db.execute('''SELECT a.source,a.offset,a.turn,a.owner,s.sid,
            a.owner!=s.sid AS inherited,a.kind FROM appearances a JOIN sessions s ON s.source=a.source
            WHERE a.key=? LIMIT 100''', (r['key'],))]
        message = self.db.execute('SELECT id FROM messages WHERE source=? AND offset<=? ORDER BY offset DESC LIMIT 1', (r['source'], r['offset'])).fetchone()
        return {'response': r, 'message': 'message:'+str(message['id']) if message else None,
                'activities': activities, 'provenance': provenance, 'offset': offset,
                'count': self.db.execute('SELECT COUNT(*) FROM activities WHERE source=? AND following=?', (r['source'], r['key'])).fetchone()[0]}

    def findings(self, args):
        where, values = self.filters(args)
        # Scope includes only activity linked to a response in scope. Unassociated activity is separately paged.
        base = f'''FROM activities t WHERE t.kind='output' AND EXISTS
            (SELECT 1 FROM appearances a WHERE a.source=t.source AND a.key=t.following AND {where})'''
        largest = [dict(r) for r in self.db.execute('SELECT t.*, (SELECT MIN(a.id) FROM appearances a WHERE a.source=t.source AND a.key=t.following) following_id '+base+' ORDER BY bytes DESC LIMIT 10', values)]
        groups = []
        for category, extra in [('Repeated unchanged output', ''), ('Repeated command failures', ' AND t.failed=1')]:
            sql = '''SELECT t.source,t.action_key,t.hash,COUNT(*) occurrences,MIN(t.timestamp) first,MAX(t.timestamp) last,
                     MIN(t.boundary) first_boundary,MAX(t.boundary) last_boundary,MAX(t.truncated) truncated,
                     MIN(t.action) action,MIN(t.tool) tool '''+base+extra+''' AND t.action_key IS NOT NULL
                     GROUP BY t.source,t.action_key,t.hash HAVING COUNT(*)>1 ORDER BY occurrences DESC LIMIT 10'''
            for row in self.db.execute(sql, values):
                r = dict(row); r['category'] = category
                r['evidence'] = [dict(x) for x in self.db.execute('SELECT t.id,t.timestamp,t.following,t.source,t.boundary '+base+
                    ' AND t.source=? AND t.action_key=? AND t.hash=? ORDER BY t.offset LIMIT 20', values+[r['source'], r['action_key'], r['hash']])]
                groups.append(r)
        sql, params = self.scoped(args)
        # SQLite window calculates context changes across the complete selected response scope, not just this page.
        jumps = [dict(r) for r in self.db.execute('''WITH selected AS ('''+sql+'''), changes AS (
            SELECT id,source,key,timestamp,turn,conflict,json_extract(usage,'$.input_tokens') input,
            json_extract(usage,'$.input_tokens') - LAG(json_extract(usage,'$.input_tokens'))
            OVER(PARTITION BY source ORDER BY timestamp,id) jump FROM selected WHERE kind='native' AND conflict=0 AND json_array_length(json_extract(usage,'$.errors'))=0)
            SELECT * FROM changes WHERE jump>0 AND conflict=0 ORDER BY jump DESC LIMIT 10''', params)]
        reasoning = [dict(r) for r in self.db.execute('''SELECT id,source,key,timestamp,turn,
            json_extract(usage,'$.reasoning_output_tokens') reasoning FROM ('''+sql+''')
            WHERE kind='native' AND conflict=0 AND json_array_length(json_extract(usage,'$.errors'))=0
            ORDER BY reasoning DESC LIMIT 10''', params)]
        return {'largest': largest, 'repeated': groups, 'jumps': jumps, 'reasoning': reasoning}

    def legacy(self, args):
        sql, values = self.scoped(args)
        offset = page_offset(args)
        return {'items': [self.response(r) for r in self.db.execute(sql+" AND a.kind!='native' ORDER BY timestamp,id LIMIT 50 OFFSET ?", values+[offset])],
                'count': self.db.execute('SELECT COUNT(*) FROM ('+sql+") WHERE kind!='native'", values).fetchone()[0], 'offset': offset}

    def activity(self, args):
        where, values = self.filters(args)
        # Use sessions for unassociated activity; model/date filters on activity cannot establish model provenance.
        source_scope = '1'; params = []
        if args.get('session'):
            source_scope = 'source IN (SELECT source FROM sessions WHERE sid=?)'; params = [args['session']]
        if args.get('turn'):
            source_scope += ' AND turn=?'; params.append(args['turn'])
        if args.get('activity'):
            source_scope += ' AND id=?'; params.append(args['activity'])
        rows = [dict(r) for r in self.db.execute('SELECT activities.*, (SELECT MIN(a.id) FROM appearances a WHERE a.source=activities.source AND a.key=activities.following) following_id FROM activities WHERE '+source_scope+' ORDER BY offset LIMIT 50 OFFSET ?', params+[page_offset(args)])]
        return {'activities': rows, 'offset': page_offset(args), 'count': self.db.execute('SELECT COUNT(*) FROM activities WHERE '+source_scope, params).fetchone()[0]}

    def diagnostics(self, args):
        where, values = ('source IN (SELECT source FROM sessions WHERE sid=?)', [args['session']]) if args.get('session') else ('1', [])
        return {'count': self.db.execute('SELECT COUNT(*) FROM diagnostics WHERE '+where, values).fetchone()[0],
                'items': [dict(r) for r in self.db.execute('SELECT * FROM diagnostics WHERE '+where+' ORDER BY id DESC LIMIT 50 OFFSET ?', values+[page_offset(args)])]}


def page_offset(args):
    try:
        return max(0, min(10**9, int(args.get('offset', 0))))
    except (TypeError, ValueError):
        return 0
