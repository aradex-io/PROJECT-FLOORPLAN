"""SQLite session store — recording, playback, and device history."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from floorplan.models import Position
from floorplan.tracking.device import TrackedDevice

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    site_config TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS position_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    mac TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL DEFAULT 0.0,
    uncertainty_m REAL DEFAULT 0.0,
    confidence REAL DEFAULT 0.0,
    timestamp REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS ranging_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    target_mac TEXT NOT NULL,
    distance_m REAL NOT NULL,
    std_dev_m REAL NOT NULL,
    rssi_dbm INTEGER,
    rtt_ns REAL,
    is_nlos INTEGER DEFAULT 0,
    timestamp REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS device_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    mac TEXT NOT NULL,
    mac_history TEXT,
    fingerprint_hash TEXT,
    first_seen REAL,
    last_seen REAL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS zone_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    zone_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    x REAL,
    y REAL,
    dwell_time_s REAL,
    timestamp REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_position_session_time
    ON position_records(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_position_device
    ON position_records(device_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ranging_session_time
    ON ranging_records(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_zone_events_session
    ON zone_events(session_id, timestamp);
"""


class SessionStore:
    """SQLite-based session recording and retrieval.

    Stores position tracks, ranging measurements, device info, and zone events
    for recording, playback, and report generation.
    """

    def __init__(self, db_path: str | Path = "floorplan.db") -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._current_session_id: int | None = None

    def connect(self) -> None:
        """Open database connection and ensure schema exists."""
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()
        logger.info("Database connected: %s", self.db_path)

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        if not self._conn:
            self.connect()
        assert self._conn is not None
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # --- Session management ---

    def start_session(self, name: str, site_config: str = "", notes: str = "") -> int:
        """Start a new recording session. Returns session ID."""
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (name, site_config, started_at, notes) VALUES (?, ?, ?, ?)",
                (name, site_config, time.time(), notes),
            )
            session_id = cur.lastrowid
            assert session_id is not None
            self._current_session_id = session_id
            logger.info("Started session %d: %s", session_id, name)
            return session_id

    def end_session(self, session_id: int | None = None) -> None:
        """End a recording session."""
        sid = session_id or self._current_session_id
        if sid is None:
            return
        with self._cursor() as cur:
            cur.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (time.time(), sid),
            )
        if sid == self._current_session_id:
            self._current_session_id = None
        logger.info("Ended session %d", sid)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all recorded sessions."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM sessions ORDER BY started_at DESC")
            return [dict(row) for row in cur.fetchall()]

    # --- Position recording ---

    def record_position(
        self,
        device_id: str,
        mac: str,
        position: Position,
        confidence: float = 0.0,
        timestamp: float = 0.0,
        session_id: int | None = None,
    ) -> None:
        """Record a device position."""
        sid = session_id or self._current_session_id
        if sid is None:
            return
        ts = timestamp or time.time()
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO position_records
                   (session_id, device_id, mac, x, y, z, uncertainty_m, confidence, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid,
                    device_id,
                    mac,
                    position.x,
                    position.y,
                    position.z,
                    position.uncertainty_m,
                    confidence,
                    ts,
                ),
            )

    def record_ranging(
        self,
        target_mac: str,
        distance_m: float,
        std_dev_m: float,
        rssi_dbm: int = 0,
        rtt_ns: float = 0.0,
        is_nlos: bool = False,
        timestamp: float = 0.0,
        session_id: int | None = None,
    ) -> None:
        """Record a ranging measurement."""
        sid = session_id or self._current_session_id
        if sid is None:
            return
        ts = timestamp or time.time()
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO ranging_records
                   (session_id, target_mac, distance_m,
                    std_dev_m, rssi_dbm, rtt_ns,
                    is_nlos, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sid, target_mac, distance_m, std_dev_m, rssi_dbm, rtt_ns, int(is_nlos), ts),
            )

    def record_device(
        self,
        device: TrackedDevice,
        session_id: int | None = None,
    ) -> None:
        """Record device information."""
        sid = session_id or self._current_session_id
        if sid is None:
            return
        with self._cursor() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO device_records
                   (session_id, device_id, mac,
                    mac_history, fingerprint_hash,
                    first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid,
                    device.device_id,
                    device.mac,
                    json.dumps(device.mac_history),
                    device.fingerprint_hash,
                    device.first_seen,
                    device.last_seen,
                ),
            )

    def record_zone_event(
        self,
        device_id: str,
        zone_name: str,
        event_type: str,
        position: Position,
        dwell_time_s: float | None = None,
        timestamp: float = 0.0,
        session_id: int | None = None,
    ) -> None:
        """Record a zone event."""
        sid = session_id or self._current_session_id
        if sid is None:
            return
        ts = timestamp or time.time()
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO zone_events
                   (session_id, device_id, zone_name, event_type, x, y, dwell_time_s, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sid, device_id, zone_name, event_type, position.x, position.y, dwell_time_s, ts),
            )

    # --- Playback / query ---

    def get_position_track(
        self,
        session_id: int,
        device_id: str | None = None,
        start_time: float = 0.0,
        end_time: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Retrieve position records for playback."""
        with self._cursor() as cur:
            query = "SELECT * FROM position_records WHERE session_id = ?"
            params: list[Any] = [session_id]

            if device_id:
                query += " AND device_id = ?"
                params.append(device_id)
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            query += " ORDER BY timestamp"
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def get_session_devices(self, session_id: int) -> list[dict[str, Any]]:
        """Get all devices observed in a session."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM device_records WHERE session_id = ?",
                (session_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_zone_events(
        self,
        session_id: int,
        zone_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get zone events for a session."""
        with self._cursor() as cur:
            query = "SELECT * FROM zone_events WHERE session_id = ?"
            params: list[Any] = [session_id]
            if zone_name:
                query += " AND zone_name = ?"
                params.append(zone_name)
            query += " ORDER BY timestamp"
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def get_session_stats(self, session_id: int) -> dict[str, Any]:
        """Get summary statistics for a session."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as count FROM position_records WHERE session_id = ?",
                (session_id,),
            )
            pos_count = cur.fetchone()["count"]

            cur.execute(
                "SELECT COUNT(DISTINCT device_id) as count "
                "FROM position_records WHERE session_id = ?",
                (session_id,),
            )
            device_count = cur.fetchone()["count"]

            cur.execute(
                "SELECT COUNT(*) as count FROM zone_events WHERE session_id = ?",
                (session_id,),
            )
            event_count = cur.fetchone()["count"]

            cur.execute(
                "SELECT MIN(timestamp) as start_t, "
                "MAX(timestamp) as end_t "
                "FROM position_records WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            duration = (row["end_t"] or 0) - (row["start_t"] or 0)

            return {
                "session_id": session_id,
                "position_records": pos_count,
                "unique_devices": device_count,
                "zone_events": event_count,
                "duration_s": duration,
            }

    def __enter__(self) -> SessionStore:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
