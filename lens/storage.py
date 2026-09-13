"""Cache schema. Source appearances own data; views union native response identities."""
import sqlite3

SCHEMA = '''
CREATE TABLE IF NOT EXISTS sources (
 id INTEGER PRIMARY KEY, path TEXT UNIQUE, identity TEXT, size INTEGER DEFAULT 0,
 mtime INTEGER DEFAULT 0, offset INTEGER DEFAULT 0, anchor TEXT, state TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS sessions (
 source INTEGER PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
 sid TEXT, project TEXT, title TEXT, parent TEXT, relationship TEXT, provider TEXT);
CREATE INDEX IF NOT EXISTS session_sid ON sessions(sid);
CREATE TABLE IF NOT EXISTS contexts (
 source INTEGER REFERENCES sources(id) ON DELETE CASCADE, turn TEXT, offset INTEGER,
 timestamp TEXT, model TEXT, speed TEXT, context_limit INTEGER, PRIMARY KEY(source, offset));
CREATE INDEX IF NOT EXISTS context_turn ON contexts(source,turn,offset);
CREATE TABLE IF NOT EXISTS appearances (
 id INTEGER PRIMARY KEY, source INTEGER REFERENCES sources(id) ON DELETE CASCADE,
 offset INTEGER, key TEXT, rid TEXT, turn TEXT, timestamp TEXT, model TEXT, speed TEXT,
 provider TEXT, context_limit INTEGER, usage TEXT, signature TEXT, kind TEXT, owner TEXT,
 UNIQUE(source,offset));
CREATE INDEX IF NOT EXISTS appearance_key ON appearances(key);
CREATE INDEX IF NOT EXISTS appearance_source_key ON appearances(source,key,offset);
CREATE INDEX IF NOT EXISTS appearance_scope ON appearances(source,turn,timestamp);
CREATE TABLE IF NOT EXISTS activities (
 id INTEGER PRIMARY KEY, source INTEGER REFERENCES sources(id) ON DELETE CASCADE,
 offset INTEGER, turn TEXT, timestamp TEXT, call_id TEXT, kind TEXT, tool TEXT, action TEXT,
 action_key TEXT, preview TEXT, bytes INTEGER, chars INTEGER, hash TEXT, truncated INTEGER,
 failed INTEGER, boundary INTEGER, following TEXT, association TEXT, operations TEXT,
 UNIQUE(source,call_id,kind));
CREATE INDEX IF NOT EXISTS activity_scope ON activities(source,turn,following);
CREATE INDEX IF NOT EXISTS activity_pending ON activities(source,turn,offset)
 WHERE following IS NULL AND kind='output';
CREATE INDEX IF NOT EXISTS activity_response ON activities(source,following,offset);
CREATE TABLE IF NOT EXISTS diagnostics (
 id INTEGER PRIMARY KEY, source INTEGER REFERENCES sources(id) ON DELETE CASCADE,
 offset INTEGER, code TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source INTEGER REFERENCES sources(id) ON DELETE CASCADE,
 offset INTEGER, identity TEXT, role TEXT, timestamp TEXT, text TEXT, truncated INTEGER,
 UNIQUE(source,identity));
CREATE INDEX IF NOT EXISTS message_source ON messages(source,offset);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, content='messages', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
 INSERT INTO messages_fts(rowid,text) VALUES(new.id,new.text); END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
 INSERT INTO messages_fts(messages_fts,rowid,text) VALUES('delete',old.id,old.text); END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
 INSERT INTO messages_fts(messages_fts,rowid,text) VALUES('delete',old.id,old.text);
 INSERT INTO messages_fts(rowid,text) VALUES(new.id,new.text); END;
CREATE TABLE IF NOT EXISTS notes (
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, text TEXT NOT NULL, project TEXT NOT NULL DEFAULT '',
 citation TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT);
CREATE VIEW IF NOT EXISTS canonical AS
 SELECT a.*, CASE WHEN (SELECT COUNT(DISTINCT signature) FROM appearances b WHERE b.key=a.key)>1
 THEN 1 ELSE 0 END AS conflict
 FROM appearances a WHERE a.id=(SELECT MIN(b.id) FROM appearances b WHERE b.key=a.key);
'''


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA cache_size=-8192')
    db.execute('PRAGMA temp_store=FILE')
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (0, 1):
        db.close()
        raise ValueError('Unsupported cache version; choose a new --cache-dir')
    db.executescript(SCHEMA)
    db.execute('PRAGMA user_version=1')
    return db
