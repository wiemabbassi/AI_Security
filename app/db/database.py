import json
import sqlite3
import os
from typing import List, Dict, Any

DB_PATH = "security_events.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
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
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_behavior (
            user_id TEXT PRIMARY KEY,
            request_count INTEGER DEFAULT 0,
            blocked_count INTEGER DEFAULT 0,
            avg_risk_score REAL DEFAULT 0.0,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def log_event(event_data: Dict[str, Any]):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO security_events (
            user_id, api_key, client_ip, raw_prompt, masked_prompt,
            action, risk_score, injection_score, jailbreak_score,
            anomaly_score, llama_guard_status, raw_response, final_response, flagged, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
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
        json.dumps(event_data.get("metadata", {}))
    ))
    conn.commit()
    conn.close()

def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM security_events ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    events = [dict(row) for row in rows]
    conn.close()
    return events

def get_timescaledb_hourly_aggregates() -> List[Dict[str, Any]]:
    """
    TimescaleDB continuous aggregate query helper:
    Aggregates blocked vs allowed request counts and average risk score per hour.
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT strftime('%Y-%m-%d %H:00:00', timestamp) as hourly_bucket,
               COUNT(*) as total_events,
               SUM(CASE WHEN action = 'BLOCK' THEN 1 ELSE 0 END) as blocked_events,
               AVG(risk_score) as avg_risk
        FROM security_events
        GROUP BY hourly_bucket
        ORDER BY hourly_bucket DESC
        LIMIT 24
    """)
    rows = cursor.fetchall()
    aggregates = [dict(row) for row in rows]
    conn.close()
    return aggregates
