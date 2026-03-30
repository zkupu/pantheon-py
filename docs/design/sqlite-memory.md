# Design: SQLite Memory Backend

**Status:** Proposal
**Phase:** 6B — Pantheon review backlog
**Author:** Athena (architecture) + Eris (red-team)
**Date:** 2026-03-29

---

## Problem

`FileStore` (`src/pantheon/memory.py:51-174`) persists sessions as individual
JSON files.  Four structural weaknesses emerge under real workloads:

| Issue | Root Cause | Impact |
|-------|-----------|--------|
| Linear scan on list/search | `list_sessions()` globs `*.json`, reads each | O(n) per call; degrades at ~200+ sessions |
| No full-text search | `search()` loads every file, scans content in-memory | CPU-bound, no ranking, no stemming |
| No concurrent-write safety | `path.write_text()` with no locking | Corrupted JSON under parallel CLI invocations |
| Directory bloat | One `.json` per session | inode pressure on ext4/HFS+ at scale |

These are not hypothetical.  A multi-agent orchestration run (`orchestrate.py`)
can spawn 5-10 agents, each saving history concurrently via the same
`FileStore(MEMORY_DIR)`.

## Constraints

1. **Zero new dependencies** — `sqlite3` is stdlib since Python 3.0.
2. **Store protocol compatibility** — must satisfy `Store(Protocol)` at `memory.py:22-27`.
3. **Non-breaking rollout** — `FileStore` remains default; `SqliteStore` is opt-in.
4. **Migration path** — existing JSON sessions must be importable without data loss.
5. **Python 3.10+** — minimum supported version (per `pyproject.toml`).

## Current Architecture

```
FileStore
├── save()          → json.dumps(asdict(sess)) → path.write_text()  [full overwrite]
├── load()          → path.read_text() → json.loads()               [full parse]
├── list_sessions() → dir.glob("*.json") → _load_raw() each         [linear scan]
└── search()        → glob + load + str.lower().find()               [brute force]
```

Key data structures:
- `_Session` dataclass (`memory.py:40-48`): `id`, `agent`, `messages` (list of dicts), timestamps, tags, tier
- `SessionInfo` dataclass (`memory.py:30-37`): metadata without message bodies
- `Message` dataclass (`_types.py`): role, content, tool_calls, tool_call_id, name

Integration points:
- `cli.py:145-146` — `store = FileStore(config.memory_dir())` / `sid = session_id(name, "interactive")`
- `cli.py:172,180` — `store.save(sid, agent.history, ...)`
- `config.py:172-173` — `MEMORY_DIR` env var, defaults to `.memory`

## Proposed Design

### Schema

```sql
-- Core session metadata and message payload
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    agent       TEXT NOT NULL DEFAULT '',
    tier        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,  -- ISO 8601
    updated_at  TEXT NOT NULL,  -- ISO 8601
    messages    TEXT NOT NULL   -- JSON array of message dicts
) STRICT;

-- Normalized tags for filtered queries
CREATE TABLE session_tags (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (session_id, tag)
);

-- Full-text search over message content
CREATE VIRTUAL TABLE messages_fts USING fts5(
    session_id,
    content,
    content='',                   -- contentless (external content mode)
    tokenize='porter unicode61'   -- stemming + unicode normalization
);

-- Fast lookups
CREATE INDEX idx_sessions_agent ON sessions(agent);
CREATE INDEX idx_sessions_tier  ON sessions(tier);
CREATE INDEX idx_sessions_updated ON sessions(updated_at DESC);
```

**Design decisions:**

- **Messages stored as JSON blob, not normalized rows.** Messages are always
  loaded/saved as a complete list per session — never queried individually.
  Normalizing into a `messages` table would add join overhead for zero query
  benefit.  The JSON blob matches `FileStore`'s current serialization model
  exactly.

- **Contentless FTS5 (`content=''`).** The FTS index stores tokens only, not the
  original text — saves ~40% disk vs. content-backed FTS.  Rebuild requires
  re-extracting from `sessions.messages`, but this is a one-shot migration
  operation, not a runtime concern.

- **`STRICT` mode on `sessions`.** Enforces type affinity (TEXT columns reject
  integers/blobs).  Available since SQLite 3.37 (2021-11); all Python 3.10+
  bundles ≥ 3.37.

- **Tags normalized, not JSON array.** Enables `WHERE tag = ?` queries without
  JSON path extraction.  Tag merge logic (`save()` merges new + existing tags)
  maps naturally to `INSERT OR IGNORE`.

### SqliteStore Implementation

```python
class SqliteStore:
    """SQLite-backed session persistence with FTS5 search and WAL concurrency."""

    def __init__(self, path: str | Path) -> None:
        self._db_path = Path(path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._lock = threading.Lock()
        self._create_tables()

    # --- Store protocol ---

    def save(
        self,
        session_id: str,
        messages: list[Message],
        agent: str = "",
        tags: list[str] | None = None,
        tier: str = "",
    ) -> None:
        _validate_session_id(session_id)
        now = datetime.now(timezone.utc).isoformat()
        messages_json = json.dumps([m.to_dict() for m in messages])

        with self._lock, self._conn:
            # Upsert session — preserve created_at and non-empty fields
            self._conn.execute("""
                INSERT INTO sessions (id, agent, tier, created_at, updated_at, messages)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    agent     = COALESCE(NULLIF(excluded.agent, ''), sessions.agent),
                    tier      = COALESCE(NULLIF(excluded.tier, ''), sessions.tier),
                    updated_at = excluded.updated_at,
                    messages  = excluded.messages
            """, (session_id, agent, tier, now, now, messages_json))

            # Merge tags
            for tag in (tags or []):
                self._conn.execute(
                    "INSERT OR IGNORE INTO session_tags (session_id, tag) VALUES (?, ?)",
                    (session_id, tag),
                )

            # Update FTS index
            self._conn.execute(
                "DELETE FROM messages_fts WHERE session_id = ?",
                (session_id,),
            )
            content = " ".join(
                m.content for m in messages if m.content and m.role != "system"
            )
            if content:
                self._conn.execute(
                    "INSERT INTO messages_fts (session_id, content) VALUES (?, ?)",
                    (session_id, content),
                )

    def load(self, session_id: str) -> list[Message]:
        _validate_session_id(session_id)
        row = self._conn.execute(
            "SELECT messages FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return []
        return [
            Message(
                role=m.get("role", ""),
                content=m.get("content") or "",
                tool_calls=m.get("tool_calls", []),
                tool_call_id=m.get("tool_call_id", ""),
                name=m.get("name", ""),
            )
            for m in json.loads(row[0])
        ]

    def list_sessions(self) -> list[SessionInfo]:
        rows = self._conn.execute("""
            SELECT s.id, s.agent, json_array_length(s.messages),
                   s.updated_at, s.tier
            FROM sessions s
            ORDER BY s.updated_at DESC
        """).fetchall()
        result = []
        for row in rows:
            tags = [
                r[0] for r in self._conn.execute(
                    "SELECT tag FROM session_tags WHERE session_id = ?",
                    (row[0],),
                ).fetchall()
            ]
            result.append(SessionInfo(
                id=row[0], agent=row[1], messages=row[2],
                updated_at=row[3], tags=tags, tier=row[4],
            ))
        return result

    # --- Extended API ---

    def search(self, query: str, limit: int = 20) -> list[SessionInfo]:
        """Full-text search across all session message content."""
        rows = self._conn.execute("""
            SELECT s.id, s.agent, json_array_length(s.messages),
                   s.updated_at, s.tier
            FROM messages_fts f
            JOIN sessions s ON s.id = f.session_id
            WHERE f.content MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
        return [
            SessionInfo(id=r[0], agent=r[1], messages=r[2],
                        updated_at=r[3], tier=r[4])
            for r in rows
        ]

    def delete(self, session_id: str) -> bool:
        """Delete a session and its tags/FTS entries (CASCADE)."""
        _validate_session_id(session_id)
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM messages_fts WHERE session_id = ?",
                (session_id,),
            )
            cursor = self._conn.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,),
            )
            return cursor.rowcount > 0

    def vacuum(self) -> None:
        """Reclaim disk space after bulk deletions."""
        self._conn.execute("VACUUM")

    def close(self) -> None:
        """Checkpoint WAL and close the connection."""
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._conn.close()
```

### WAL Mode — Why and How

Write-Ahead Logging (`PRAGMA journal_mode=WAL`) is the critical enabler for
multi-agent concurrency:

```
                FileStore (current)          SqliteStore (proposed)
Concurrent      Undefined — last write       WAL: readers never block,
read/write      wins, possible corruption    writers queue with busy_timeout
Crash safety    Partial write = corrupt      WAL journal survives crashes;
                JSON; _load_raw returns      automatic recovery on next open
                None
Write perf      Full file rewrite per save   Append-only WAL; periodic
                                             checkpoint merges to main DB
```

**`busy_timeout=5000`** — if another process holds the write lock, wait up to 5s
before raising `OperationalError`.  Covers the orchestrator case where multiple
agents save near-simultaneously.

**WAL checkpoint strategy:**
- SQLite auto-checkpoints when the WAL reaches 1000 pages (~4 MB).
- `close()` forces a `TRUNCATE` checkpoint to collapse the WAL.
- No periodic background checkpointing needed for typical CLI lifetimes.

### FTS5 — Search Semantics

Current `FileStore.search()` (`memory.py:148-174`):
- Loads every JSON file, scans content with `str.lower().find()`
- No stemming: "running" won't match "run"
- No ranking: results ordered by filename, not relevance
- O(n × m) where n = sessions, m = avg messages per session

Proposed `SqliteStore.search()`:
- FTS5 inverted index — O(log n) lookup
- Porter stemmer: "running" matches "run", "runner", "runs"
- BM25 ranking via `ORDER BY rank`
- Limit clause prevents runaway result sets

**Contentless trade-off:** `content=''` means `MATCH` highlights and snippets are
unavailable.  This is acceptable — search returns `SessionInfo` metadata, and
the caller uses `load()` to retrieve full messages when needed.

### Migration

```python
def migrate_filestore_to_sqlite(
    file_store: FileStore,
    sqlite_store: SqliteStore,
) -> tuple[int, int]:
    """Migrate all FileStore sessions to SqliteStore.

    Returns (migrated_count, error_count).
    Non-destructive: original JSON files are untouched.
    Idempotent: safe to re-run via ON CONFLICT upsert.
    """
    migrated = errors = 0
    for info in file_store.list_sessions():
        try:
            messages = file_store.load(info.id)
            sqlite_store.save(
                info.id, messages,
                agent=info.agent, tags=info.tags, tier=info.tier,
            )
            migrated += 1
        except Exception:
            _log.warning("failed to migrate session %s", info.id, exc_info=True)
            errors += 1
    return migrated, errors
```

**Auto-detection:** On first `SqliteStore.__init__`, check for `*.json` files in
the parent directory.  If found and the DB is empty, log a suggestion:
`"Found N JSON session files. Run 'pantheon migrate-memory' to import them."`
Do not auto-migrate silently — the user should opt in.

### Configuration

```python
# In config.py — extend memory_dir() with backend selection

def memory_backend() -> str:
    return os.environ.get("MEMORY_BACKEND", "file")

def memory_sqlite_path() -> str:
    return os.environ.get(
        "MEMORY_SQLITE_PATH",
        str(Path(memory_dir()) / "pantheon.db"),
    )
```

```python
# In cli.py — factory pattern for store selection

def _create_store(cfg: Config) -> Store:
    if cfg.memory_backend() == "sqlite":
        from .memory import SqliteStore
        return SqliteStore(cfg.memory_sqlite_path())
    return FileStore(cfg.memory_dir())
```

### Component Map

```
┌─────────────────────────────────────────────────────────┐
│                      CLI / Agent                        │
│   cli.py:145  store = _create_store(config)             │
│   cli.py:172  store.save(sid, agent.history, ...)       │
│   cli.py:180  store.save(sid, agent.history, ...)       │
└──────────────────────┬──────────────────────────────────┘
                       │ Store protocol
          ┌────────────┴────────────┐
          │                         │
          v                         v
   ┌──────────────┐         ┌──────────────┐
   │  FileStore   │         │ SqliteStore  │
   │  (default)   │         │  (opt-in)    │
   │              │         │              │
   │ .memory/     │ migrate │ .memory/     │
   │  *.json      │ ──────> │ pantheon.db  │
   │              │         │ ├── sessions │
   │  O(n) scan   │         │ ├── tags     │
   │  No locking  │         │ ├── FTS5     │
   │  No search   │         │ └── WAL      │
   └──────────────┘         └──────────────┘
                                    │
                            ┌───────┴───────┐
                            │ threading.Lock│
                            │ busy_timeout  │
                            │ WAL journal   │
                            └───────────────┘
```

---

## Risk Analysis (Athena)

### R1: FTS5 Availability — Low Risk

FTS5 requires SQLite ≥ 3.9.0 (2015-10-14).  Python 3.10 bundles SQLite ≥ 3.35.
However, some Linux distros compile Python against the system `libsqlite3`, which
could theoretically be ancient.

**Mitigation:** Add a runtime check in `SqliteStore.__init__`:

```python
version = sqlite3.sqlite_version_info
if version < (3, 9, 0):
    raise RuntimeError(
        f"SqliteStore requires SQLite >= 3.9.0 for FTS5 (found {sqlite3.sqlite_version})"
    )
```

### R2: WAL File Growth — Low Risk

WAL files grow until checkpointed.  Default auto-checkpoint triggers at 1000
pages (~4 MB).  For typical CLI usage (seconds-to-minutes), this is negligible.

**Edge case:** A long-running orchestrator that saves thousands of sessions
without closing could grow the WAL.  Mitigation: `close()` forces
`wal_checkpoint(TRUNCATE)`.  Document that callers should use `SqliteStore` as a
context manager.

### R3: Network Filesystem Locking — Medium Risk

SQLite's locking protocol is unreliable on NFS, CIFS, and some FUSE mounts.
WAL mode compounds this — it requires shared-memory (`-shm`) files that don't
work over network FS.

**Mitigation:** Detect and warn:

```python
import shutil
if shutil.disk_usage(self._db_path.parent).total == 0:
    _log.warning("MEMORY_DIR may be on a network filesystem; SQLite WAL is unreliable there")
```

Better: document in `configuration-reference.md` that `MEMORY_DIR` must be local.

### R4: Thread Safety — Low Risk

`check_same_thread=False` allows cross-thread access. The `threading.Lock`
serializes writes.  Reads are inherently safe under WAL (readers see a
consistent snapshot).

**Not covered:** multi-process writes (separate CLI invocations).  WAL +
`busy_timeout` handles this at the SQLite level — no application-level locking
needed.

### R5: Migration Data Loss — Low Risk

Corrupt JSON files cause `_load_raw()` to return `None` → `load()` returns `[]`.
Migration skips these with a warning.  Original files are untouched.

**Edge case:** A session that saves successfully but has messages that fail
`json.loads()` on a subsequent parse.  This is already a `FileStore` bug, not a
migration risk.

---

## Stress Test (Eris)

### Assumptions Challenged

**A1: "Messages should stay as a JSON blob, not normalized rows."**

- **Risk if wrong:** If a future feature needs per-message queries (e.g., "find
  all tool calls across sessions," "count tokens per message"), the JSON blob
  forces full deserialization.  `json_array_length()` works for counts, but
  `json_extract()` on large blobs is slow.
- **Evidence for:** Current `Store` protocol only loads/saves full message lists.
  No caller queries individual messages.  `list_sessions()` needs message count,
  which `json_array_length()` provides without parsing.
- **Evidence against:** `search()` already needs per-message content — we extract
  and flatten into FTS.  If search needs expand (e.g., filter by role, by tool
  name), the blob becomes a bottleneck.
- **Verdict:** JSON blob is correct *for now*.  Add a `schema_version` integer to
  the DB (default 1) so a future migration can normalize without breaking
  existing installs.

**A2: "Contentless FTS5 is sufficient."**

- **Risk if wrong:** Contentless mode means no `snippet()` or `highlight()`
  support.  If the CLI ever wants to show search result previews ("...matched
  near: *running the pipeline*..."), this requires re-loading the full session
  and scanning again.
- **Evidence for:** Current `search()` returns `SessionInfo` with no content
  preview.  The 40% disk savings is meaningful — FTS indexes can be large.
- **Evidence against:** Search UX in tools like Obsidian and Notion relies heavily
  on result previews.  Rebuilding the index from the JSON blob is O(n) and not
  instantaneous.
- **Verdict:** Start contentless.  If preview demand emerges, switch to
  content-backed FTS (one-time `DROP` + `CREATE` + re-index migration).
  Document the trade-off.

**A3: "`busy_timeout=5000` is enough for concurrent agents."**

- **Risk if wrong:** If 10 agents all save within a tight loop (e.g.,
  orchestrator batch-completing), the 5s timeout could be exceeded if each write
  takes ~1s due to large message payloads.
- **Evidence for:** Individual session saves are fast (~1-10ms for typical message
  counts).  SQLite WAL allows concurrent reads even during writes.  The lock
  contention window is tiny.
- **Evidence against:** No load testing data yet.  Large sessions (1000+ messages
  with tool calls) could mean multi-MB JSON blobs serialized in the critical
  section.
- **Verdict:** 5s is generous for expected workloads.  Add a log warning if
  `busy_timeout` is triggered (catch `OperationalError` with "database is
  locked" and log at WARNING before re-raising).

### Questions Raised

1. **Should `SqliteStore` implement `__enter__`/`__exit__`** for context-manager
   usage?  The `close()` method exists but nothing enforces it.  An unclosed
   store leaks the WAL file.  Recommendation: yes, add context-manager protocol.

2. **What happens to the FTS index if `save()` is called with an empty message
   list?** The current implementation deletes the old FTS entry and inserts
   nothing.  Is an empty session valid?  Should `delete()` be called instead?
   Recommendation: allow empty saves (noop for FTS), document the behavior.

3. **Should `search()` accept `agent` and `tier` filters** like the current
   `FileStore.search()`?  The proposed `SqliteStore.search()` drops those
   parameters.  This is a silent API regression.  Recommendation: add optional
   `agent` and `tier` parameters to the `WHERE` clause for parity.

4. **What is the upgrade path from `SqliteStore` schema v1 to v2?**  If
   `schema_version` is added, there needs to be a migration runner.
   Recommendation: add a `_migrate()` method called from `__init__` that checks
   `PRAGMA user_version` and applies DDL changes sequentially.

### Alternatives Suggested

**Alternative: Use `messages` as a content-backed FTS table directly** — store
each message as a row in FTS5 (with `session_id` as a column), eliminating the
separate `sessions.messages` JSON blob for search.  Trade-off: doubles storage
(messages in both `sessions` and FTS), but enables `snippet()` and per-message
queries without JSON parsing.  Worth evaluating if search UX becomes a priority.

### Scaling Risks

- **At 10K sessions:** `list_sessions()` returns 10K rows.  Consider pagination
  (`LIMIT/OFFSET` or cursor-based) before promoting to default.
- **At 100K messages across sessions:** FTS index rebuild (if ever needed) takes
  seconds, not milliseconds.  Background rebuild or `PRAGMA integrity_check`
  should be async.
- **With 10 concurrent agents:** WAL handles this well.  At 50+ concurrent
  writers, WAL contention rises — but that scenario implies an architectural
  problem (too many agents sharing one store), not a storage problem.

---

## Decision

Implement `SqliteStore` as an **opt-in backend** (`MEMORY_BACKEND=sqlite`) with
these specifics:

1. Add `SqliteStore` class to `memory.py` implementing the `Store` protocol.
2. Schema v1 with `PRAGMA user_version = 1` for future migrations.
3. WAL mode + `busy_timeout=5000` + `threading.Lock` for write serialization.
4. Contentless FTS5 with porter stemming for `search()`.
5. `search()` includes `agent` and `tier` filter parameters for `FileStore` parity.
6. Context-manager protocol (`__enter__`/`__exit__`) with WAL checkpoint on close.
7. `migrate_filestore_to_sqlite()` utility — non-destructive, idempotent, user-initiated.
8. `FileStore` remains default.  Promote `SqliteStore` to default after field testing in a future minor version.

**Implementation order:**
1. Schema + `SqliteStore.__init__` with WAL/FTS5 setup
2. `save()` / `load()` / `list_sessions()` — Store protocol
3. `search()` with FTS5 + filters
4. `delete()` / `vacuum()` / `close()` — extended API
5. Migration utility
6. Config/CLI wiring
7. Tests (mirror `TestFileStore` structure)
