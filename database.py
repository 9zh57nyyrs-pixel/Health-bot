"""
database.py — SQLite persistence layer for the Medical Bot.

Tables:
  - users:    profile data (gender, age, weight, height, conditions)
  - messages: conversation history (role, content, timestamp)
"""

import logging
import sqlite3
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger(__name__)

DB_PATH = "medical_bot.db"


# ─── Connection Pool ──────────────────────────────────────────────────────────

@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that provides a thread-safe SQLite connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # Better concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error, rolling back: {e}", exc_info=True)
        raise
    finally:
        conn.close()


# ─── Schema ───────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                gender      TEXT,
                age         INTEGER,
                weight      INTEGER,
                height      INTEGER,
                conditions  TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                role        TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content     TEXT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_user_id
                ON messages(user_id, created_at DESC);
        """)
    logger.info("Database schema verified/created successfully.")


# ─── User Profile ─────────────────────────────────────────────────────────────

def get_user_profile(user_id: int) -> Optional[dict]:
    """Return user profile as dict, or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return dict(row)
        return None


def update_user_profile(
    user_id: int,
    gender: Optional[str] = ...,
    age: Optional[int] = ...,
    weight: Optional[int] = ...,
    height: Optional[int] = ...,
    conditions: Optional[str] = ...,
) -> None:
    """
    Upsert user profile. Only updates fields explicitly passed (not ...sentinel).
    Pass None to explicitly clear a field.
    """
    with get_connection() as conn:
        # Ensure user row exists
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )

        updates = {}
        if gender is not ...:
            updates["gender"] = gender
        if age is not ...:
            updates["age"] = age
        if weight is not ...:
            updates["weight"] = weight
        if height is not ...:
            updates["height"] = height
        if conditions is not ...:
            updates["conditions"] = conditions

        if not updates:
            return

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [user_id]
        conn.execute(
            f"UPDATE users SET {set_clauses}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            values,
        )

    logger.debug(f"Profile updated for user {user_id}: {updates}")


# ─── Message History ──────────────────────────────────────────────────────────

def save_message(user_id: int, role: str, content: str) -> None:
    """Append a message to the conversation history."""
    if role not in ("user", "assistant"):
        raise ValueError(f"Invalid role: {role}")

    # Ensure user exists
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        conn.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )

    # Auto-prune: keep only last 100 messages per user to avoid DB bloat
    _prune_history(user_id, keep=100)
    logger.debug(f"Message saved for user {user_id}, role={role}, len={len(content)}")


def get_history(user_id: int, limit: int = 10) -> list[tuple[str, str, str]]:
    """
    Return the last `limit` messages for a user, ordered oldest→newest.
    Returns list of (role, content, timestamp) tuples.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content, created_at
            FROM (
                SELECT role, content, created_at
                FROM messages
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            )
            ORDER BY created_at ASC
            """,
            (user_id, limit),
        ).fetchall()
        return [(row["role"], row["content"], row["created_at"]) for row in rows]


def clear_history(user_id: int) -> None:
    """Delete all messages for a user (e.g., on profile reset)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    logger.info(f"History cleared for user {user_id}")


def _prune_history(user_id: int, keep: int = 100) -> None:
    """Keep only the most recent `keep` messages per user."""
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM messages
            WHERE user_id = ?
              AND id NOT IN (
                SELECT id FROM messages
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
              )
            """,
            (user_id, user_id, keep),
        )
