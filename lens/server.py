"""Capability-protected loopback server. No general filesystem route."""
import json
import secrets
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .query import Report
from .storage import connect
from .memory import Memory
from .mcp import config

ASSETS = Path(__file__).with_name('assets')


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, db_path, refresh, import_report=None, demo=False):
        self.token = secrets.token_urlsafe(32)
        self.db_path, self.refresh = db_path, refresh
        self.import_report = import_report or {}
        self.demo = demo
        self.lock = threading.Lock()
        super().__init__(('127.0.0.1', 0), Handler)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.url = self.origin + '/#' + self.token


class Handler(BaseHTTPRequestHandler):
    server_version = 'AgentLedger'

    def setup(self):
        self.request.settimeout(15)
        super().setup()

    def log_message(self, *_args):
        pass  # Do not log capability tokens, private URLs, or untrusted input.

    def reply(self, status, body, mime='application/json'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime+'; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self, api=False):
        expected = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected:
            self.reply(403, {'error': 'Untrusted host'}); return False
        origin = self.headers.get('Origin')
        if origin and origin != self.server.origin:
            self.reply(403, {'error': 'Cross-origin access denied'}); return False
        if self.headers.get('Sec-Fetch-Site') not in (None, 'none', 'same-origin'):
            self.reply(403, {'error': 'Cross-site access denied'}); return False
        if api and not secrets.compare_digest(self.headers.get('X-Lens-Token', '').encode('utf-8'), self.server.token.encode('ascii')):
            self.reply(403, {'error': 'Open the URL printed by report.py to authorize this tab'}); return False
        return True

    def do_GET(self):
        parts = urlsplit(self.path)
        api = parts.path.startswith('/api/')
        if not self.allowed(api):
            return
        routes = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                  '/app.css': ('app.css', 'text/css'), '/workspace.js': ('workspace.js', 'text/javascript')}
        if parts.path in routes:
            filename, mime = routes[parts.path]
            self.reply(200, (ASSETS/filename).read_bytes(), mime); return
        if parts.path == '/favicon.ico':
            self.reply(204, b''); return
        methods = {'/api/options': 'options', '/api/overview': 'overview', '/api/session': 'session',
                   '/api/detail': 'detail', '/api/findings': 'findings', '/api/diagnostics': 'diagnostics',
                   '/api/activity': 'activity', '/api/legacy': 'legacy', '/api/locate': 'locate'}
        memory_methods = {'/api/briefing':'briefing','/api/home':'home','/api/search':'search','/api/read':'read','/api/notes':'notes','/api/recent':'sessions','/api/insights':'insights'}
        if parts.path not in methods and parts.path not in memory_methods and parts.path != '/api/connection':
            self.reply(404, {'error': 'Not found'}); return
        try:
            args = {key: values[0][:4096] for key, values in parse_qs(parts.query, max_num_fields=30).items()}
        except ValueError:
            self.reply(400, {'error': 'Too many query parameters'}); return
        with self.server.lock:
            db = connect(self.server.db_path)
            try:
                report = Report(db)
                if parts.path == '/api/connection':
                    result = config(self.server.db_path)
                elif parts.path in memory_methods:
                    result = getattr(Memory(db),memory_methods[parts.path])(args)
                else:
                    result = report.options() if parts.path == '/api/options' else getattr(report, methods[parts.path])(args)
                if parts.path == '/api/options':
                    result['import'] = self.server.import_report
                    result['demo'] = self.server.demo
                self.reply(200, result)
            except (ValueError, TypeError):
                self.reply(400, {'error': 'Invalid report query'})
            except sqlite3.Error:
                self.reply(500, {'error': 'Cache query failed. Stop the report and rebuild in a new cache directory.'})
            finally:
                db.close()

    def do_POST(self):
        if not self.allowed(True):
            return
        if self.path in ('/api/notes/save','/api/notes/delete'):
            self.write_note(); return
        if self.path != '/api/refresh':
            self.reply(404, {'error': 'Not found'}); return
        if not self.server.lock.acquire(blocking=False):
            self.reply(409, {'error': 'An import or report query is already running'}); return
        try:
            self.server.import_report = self.server.refresh()
            self.reply(200, self.server.import_report)
        except (OSError, ValueError, sqlite3.Error):
            self.reply(500, {'error': 'Refresh failed. Check local cache and history permissions.'})
        finally:
            self.server.lock.release()

    def write_note(self):
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type') != 'application/json':
            self.reply(400, {'error':'Use a bounded JSON request'}); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 200000:
                raise ValueError()
            args = json.loads(self.rfile.read(length))
            if not isinstance(args,dict): raise ValueError()
        except (ValueError,UnicodeError,RecursionError):
            self.reply(400, {'error':'Invalid or oversized note request'}); return
        with self.server.lock:
            db=connect(self.server.db_path)
            try:
                memory=Memory(db)
                result=memory.save_note(args) if self.path.endswith('/save') else memory.delete_note(args)
                self.reply(200,result)
            except (ValueError,TypeError,sqlite3.Error):
                self.reply(400, {'error':'Could not save context. Check field lengths and whether the note still exists.'})
            finally: db.close()

    def do_OPTIONS(self):
        self.reply(403, {'error': 'Cross-origin requests are not supported'})
