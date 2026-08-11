"""
Dual-mode Database Layer
========================
- PostgreSQL + TimescaleDB when POSTGRES_URI env var is set (production)
- SQLite fallback for local development

Connection is determined at import time via settings.POSTGRES_URI.
If the URI starts with "postgresql://" or "postgres://", psycopg2 is used.
Otherwise, sqlite3 is used — zero code changes needed by callers.
"""

import json
import os
import sqlite3
from typing import List, Dict, Any
from app.config import settings

# ── Determine backend mode ────────────────────────────────────────────────────
_POSTGRES_URI = settings.POSTGRES_URI
_USE_POSTGRES = _POSTGRES_URI.startswith("postgresql://") or _POSTGRES_URI.startswith("postgres://")

# Try importing psycopg2 for PostgreSQL mode
_psycopg2 = None
if _USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
        _psycopg2 = psycopg2
    except ImportError:
        print("[DB] psycopg2 not installed — falling back to SQLite")
        _USE_POSTGRES = False

# SQLite path for fallback
DB_PATH = "security_events.db"

print(f"[DB] Backend: {'PostgreSQL/TimescaleDB' if _USE_POSTGRES else 'SQLite (dev mode)'}")


# ── Schema ────────────────────────────────────────────────────────────────────

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT,
    api_key TEXT,
    client_ip TEXT,
    raw_prompt TEXT,
    masked_prompt TEXT,
    action TEXT,
    risk_score REAL,
    injection_score REAL,
    jailbreak_score REAL,
    anomaly_score REAL,
    llama_guard_status TEXT,
    raw_response TEXT,
    final_response TEXT,
    flagged BOOLEAN DEFAULT 0,
    metadata TEXT
);
CREATE TABLE IF NOT EXISTS user_behavior (
    user_id TEXT PRIMARY KEY,
    request_count INTEGER DEFAULT 0,
    blocked_count INTEGER DEFAULT 0,
    avg_risk_score REAL DEFAULT 0.0,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ DEFAULT NOW(),
    user_id     TEXT,
    api_key     TEXT,
    client_ip   TEXT,
    raw_prompt  TEXT,
    masked_prompt TEXT,
    action      TEXT,
    risk_score  DOUBLE PRECISION,
    injection_score DOUBLE PRECISION,
    jailbreak_score DOUBLE PRECISION,
    anomaly_score   DOUBLE PRECISION,
    llama_guard_status TEXT,
    raw_response  TEXT,
    final_response TEXT,
    flagged     BOOLEAN DEFAULT FALSE,
    metadata    JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS user_behavior (
    user_id         TEXT PRIMARY KEY,
    request_count   INTEGER DEFAULT 0,
    blocked_count   INTEGER DEFAULT 0,
    avg_risk_score  DOUBLE PRECISION DEFAULT 0.0,
    last_seen       TIMESTAMPTZ DEFAULT NOW()
);

-- TimescaleDB hypertable for time-series event storage (auto-partitioned by time)
-- Only runs if TimescaleDB extension is available
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'security_events', 'timestamp',
            if_not_exists => TRUE,
            migrate_data  => TRUE
        );
    END IF;
END
$$;
"""


# ── Connection helpers ─────────────────────────────────────────────────────────

def _get_pg_conn():
    """Opens a psycopg2 connection to PostgreSQL."""
    conn = _psycopg2.connect(_POSTGRES_URI)
    conn.autocommit = False
    return conn


def _get_sqlite_conn():
    """Opens a sqlite3 connection."""
    return sqlite3.connect(DB_PATH)


# ── Initialisation ─────────────────────────────────────────────────────────────

def init_db():
    """Creates tables (and TimescaleDB hypertable) if they don't exist."""
    if _USE_POSTGRES:
        try:
            conn = _get_pg_conn()
            cur = conn.cursor()
            cur.execute(_POSTGRES_SCHEMA)
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[DB] PostgreSQL init error: {e}")
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(_SQLITE_SCHEMA)
        conn.commit()
        conn.close()


# ── Core operations ────────────────────────────────────────────────────────────

def log_event(event_data: Dict[str, Any]):
    """Persists a security event. Works with both PostgreSQL and SQLite."""
    init_db()

    fields = (
        event_data.get("user_id", "anonymous"),
        event_data.get("api_key", "public"),
        event_data.get("client_ip", "127.0.0.1"),
        event_data.get("raw_prompt", ""),
        event_data.get("masked_prompt", ""),
        event_data.get("action", "ALLOW"),
        event_data.get("risk_score", 0.0),
        event_data.get("injection_score", 0.0),
        event_data.get("jailbreak_score", 0.0),
        event_data.get("anomaly_score", 0.0),
        event_data.get("llama_guard_status", "SAFE"),
        event_data.get("raw_response", ""),
        event_data.get("final_response", ""),
        1 if event_data.get("action") in ["FLAG", "BLOCK"] else 0,
        json.dumps(event_data.get("metadata", {})),
    )

    if _USE_POSTGRES:
        try:
            conn = _get_pg_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO security_events (
                    user_id, api_key, client_ip, raw_prompt, masked_prompt,
                    action, risk_score, injection_score, jailbreak_score,
                    anomaly_score, llama_guard_status, raw_response,
                    final_response, flagged, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, fields[:-1] + (json.loads(fields[-1]),))   # JSONB takes dict
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[DB] log_event PostgreSQL error: {e} — falling back to SQLite")
            _sqlite_log_event(fields)
    else:
        _sqlite_log_event(fields)


def _sqlite_log_event(fields: tuple):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO security_events (
            user_id, api_key, client_ip, raw_prompt, masked_prompt,
            action, risk_score, injection_score, jailbreak_score,
            anomaly_score, llama_guard_status, raw_response,
            final_response, flagged, metadata
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, fields)
    conn.commit()
    conn.close()


def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetches the most recent security events ordered by newest first."""
    init_db()

    if _USE_POSTGRES:
        try:
            conn = _get_pg_conn()
            cur = conn.cursor(_psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM security_events ORDER BY timestamp DESC LIMIT %s",
                (limit,)
            )
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            print(f"[DB] get_recent_events PostgreSQL error: {e}")
            return []
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM security_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_timescaledb_hourly_aggregates() -> List[Dict[str, Any]]:
    """
    TimescaleDB continuous aggregate: blocked vs allowed counts + avg risk per hour.
    Falls back to SQLite strftime() grouping in dev mode.
    """
    init_db()

    if _USE_POSTGRES:
        try:
            conn = _get_pg_conn()
            cur = conn.cursor(_psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT
                    time_bucket('1 hour', timestamp)   AS hourly_bucket,
                    COUNT(*)                            AS total_events,
                    SUM(CASE WHEN action='BLOCK' THEN 1 ELSE 0 END) AS blocked_events,
                    AVG(risk_score)                     AS avg_risk
                FROM security_events
                GROUP BY hourly_bucket
                ORDER BY hourly_bucket DESC
                LIMIT 24
            """)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            print(f"[DB] hourly aggregates PostgreSQL error: {e}")
            return []
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT strftime('%Y-%m-%d %H:00:00', timestamp) as hourly_bucket,
                   COUNT(*) as total_events,
                   SUM(CASE WHEN action = 'BLOCK' THEN 1 ELSE 0 END) as blocked_events,
                   AVG(risk_score) as avg_risk
            FROM security_events
            GROUP BY hourly_bucket
            ORDER BY hourly_bucket DESC
            LIMIT 24
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_user_behavior_summary(user_id: str) -> Dict[str, Any]:
    """
    Fetches or upserts the behavioral profile for a given user.
    Used by behavioral_analysis.py to persist cross-session state.
    """
    init_db()

    if _USE_POSTGRES:
        try:
            conn = _get_pg_conn()
            cur = conn.cursor(_psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM user_behavior WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            return dict(row) if row else {}
        except Exception as e:
            print(f"[DB] get_user_behavior PostgreSQL error: {e}")
            return {}
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM user_behavior WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else {}


def upsert_user_behavior(user_id: str, request_count: int, blocked_count: int, avg_risk: float):
    """Upserts user behavioral profile. Called by BehavioralAnalyzer."""
    init_db()

    if _USE_POSTGRES:
        try:
            conn = _get_pg_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_behavior (user_id, request_count, blocked_count, avg_risk_score, last_seen)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    request_count  = EXCLUDED.request_count,
                    blocked_count  = EXCLUDED.blocked_count,
                    avg_risk_score = EXCLUDED.avg_risk_score,
                    last_seen      = NOW()
            """, (user_id, request_count, blocked_count, avg_risk))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[DB] upsert_user_behavior PostgreSQL error: {e}")
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO user_behavior (user_id, request_count, blocked_count, avg_risk_score)
            VALUES (?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                request_count  = excluded.request_count,
                blocked_count  = excluded.blocked_count,
                avg_risk_score = excluded.avg_risk_score,
                last_seen      = CURRENT_TIMESTAMP
        """, (user_id, request_count, blocked_count, avg_risk))
        conn.commit()
        conn.close()
