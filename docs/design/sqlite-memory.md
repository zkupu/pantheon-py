# Design: SQLite Memory Backend

**Status:** Proposal
**Author:** Pantheon review backlog (Athena + Eris)
**Date:** 2026-03-29

## Problem

`FileStore` in `memory.py` persists sessions as individual JSON files:

- **Linear scan** — `list_sessions()` reads every `.json` file in the directory to build the session list
- **No search** — finding sessions by content requires loading and scanning all files
- **Concurrent access** — no locking; simultaneous writes from multiple CLI invocations can corrupt files
- **Growing directories** — hundreds of session files degrade filesystem performance on some OSes

## Current Implementation

```python
class FileStore:
    def save(self, session_id, messages, ...):
        path.write_text(json.dumps(asdict(sess)))  # Full overwrite
        path.chmod(0o600)

    def load(self, session_id):
        data = json.loads(path.read_text())  # Full read + parse

    def list_sessions(self):
        # Scans entire directory
        for p in sorted(self.dir.glob("*.json"), ...):
            ...
```

## Proposed Design

### SQLite via stdlib `sqlite3`

Replace `FileStore` with `SqliteStore` using Python's built-in `sqlite3` module. No new dependencies.

### Schema

```sql
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    agent       TEXT NOT NULL DEFAULT '',
    tier        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    messages    TEXT NOT NULL  -- JSON array
);

CREATE TABLE session_tags (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (session_id, tag)
);

-- FTS5 for full-text search over message content
CREATE VIRTUAL TABLE messages_fts USING fts5(
    session_id,
    content,
    content='',  -- external content mode
    tokenize='porter unicode61'
);
```

### Implementation

```python
class SqliteStore:
    def __init__(self, path: str | Path) -> None:
        self._db_path = Path(path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def save(self, session_id, messages, agent="", tags=None, tier=""):
        messages_json = json.dumps([m.to_dict() for m in messages])
        self._conn.execute("""
            INSERT INTO sessions (id, agent, tier, created_at, updated_at, messages)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                agent = COALESCE(NULLIF(excluded.agent, ''), sessions.agent),
                tier = COALESCE(NULLIF(excluded.tier, ''), sessions.tier),
                updated_at = excluded.updated_at,
                messages = excluded.messages
        """, (...))
        # Update FTS index
        self._update_fts(session_id, messages)
        self._conn.commit()

    def search(self, query: str, limit: int = 20) -> list[SessionInfo]:
        """Full-text search across message content."""
        rows = self._conn.execute("""
            SELECT s.id, s.agent, s.updated_at, s.tier
            FROM messages_fts f
            JOIN sessions s ON s.id = f.session_id
            WHERE f.content MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
        ...
```

### WAL Mode

Write-Ahead Logging (`PRAGMA journal_mode=WAL`) enables:

- **Concurrent readers** — multiple CLI invocations can read simultaneously
- **Non-blocking writes** — writers don't block readers
- **Crash safety** — WAL survives process crashes without corruption
- **Performance** — sequential writes are faster than file-per-session

### FTS5 for Search

FTS5 (Full-Text Search 5) is included in Python's bundled SQLite:

- Porter stemming for natural language queries
- Ranked results by relevance
- Incremental index updates on save
- Replaces the current approach of "load all files and scan"

### Migration

Existing `FileStore` sessions can be migrated:

```python
def migrate_from_filestore(file_store: FileStore, sqlite_store: SqliteStore):
    for info in file_store.list_sessions():
        messages = file_store.load(info.id)
        sqlite_store.save(info.id, messages, agent=info.agent,
                         tags=info.tags, tier=info.tier)
```

The migration is:
- **Non-destructive** — original JSON files are untouched
- **Idempotent** — safe to re-run via `ON CONFLICT` upsert
- **Automatic** — detect `*.json` files in `MEMORY_DIR` and offer migration on first `SqliteStore` init

### Store Protocol Compatibility

`SqliteStore` implements the existing `Store` protocol:

```python
class Store(Protocol):
    def save(self, session_id: str, messages: list[Message]) -> None: ...
    def load(self, session_id: str) -> list[Message]: ...
    def list_sessions(self) -> list[SessionInfo]: ...
```

Plus new capabilities:
- `search(query: str) -> list[SessionInfo]` — full-text search
- `delete(session_id: str) -> bool` — session deletion
- `vacuum() -> None` — reclaim space

### Configuration

```bash
# Use SQLite backend (default remains FileStore for now)
MEMORY_BACKEND=sqlite

# SQLite database path (defaults to MEMORY_DIR/pantheon.db)
MEMORY_SQLITE_PATH=.memory/pantheon.db
```

## What Could Go Wrong

1. **Python's sqlite3 version** — FTS5 requires SQLite 3.9+ (2015). All supported Python versions (3.10+) bundle a recent enough SQLite. Risk: minimal.

2. **WAL file growth** — WAL files grow until checkpointed. Long-running processes without commits can accumulate large WAL files. Mitigation: periodic `PRAGMA wal_checkpoint(TRUNCATE)` after N writes.

3. **Thread safety** — `sqlite3.connect(check_same_thread=False)` allows cross-thread access but requires external synchronization for writes. Mitigation: use a `threading.Lock` around write operations, matching the current `FileStore` behavior (which has no concurrency protection at all).

4. **Database locking on NFS/network mounts** — SQLite locking is unreliable on network filesystems. Mitigation: document that `MEMORY_DIR` should be on local storage; detect and warn.

5. **Migration data loss** — corrupted JSON files could fail to migrate. Mitigation: log and skip corrupt files rather than aborting; report a summary.

## Decision

Recommended approach: implement `SqliteStore` as an opt-in backend (`MEMORY_BACKEND=sqlite`) while keeping `FileStore` as the default. Add automatic migration detection. Promote `SqliteStore` to default in a future minor version after field testing.
