import sqlite3
from datetime import datetime
from typing import Optional, List, Dict

class Database:
def **init**(self, db_path: str = “health_bot.db”):
self.db_path = db_path
self._init_db()

```
def _get_conn(self):
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db(self):
    with self._get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                age         INTEGER,
                gender      TEXT,
                height      REAL,
                weight      REAL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS weight_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                weight      REAL NOT NULL,
                date        TEXT DEFAULT (date('now')),
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS food_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                description TEXT NOT NULL,
                date        TEXT DEFAULT (date('now')),
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                description TEXT NOT NULL,
                date        TEXT DEFAULT (date('now')),
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS analyses_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                title       TEXT,
                result      TEXT,
                date        TEXT DEFAULT (date('now')),
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)

# ── Users ──────────────────────────────────────────────────────────────

def create_user(self, user_id: int, name: str, age: int,
                gender: str, height: float, weight: float):
    with self._get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, name, age, gender, height, weight) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, age, gender, height, weight)
        )

def get_user(self, user_id: int) -> Optional[Dict]:
    with self._get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

def update_user_weight(self, user_id: int, weight: float):
    with self._get_conn() as conn:
        conn.execute(
            "UPDATE users SET weight = ? WHERE user_id = ?", (weight, user_id)
        )

# ── Weight ─────────────────────────────────────────────────────────────

def log_weight(self, user_id: int, weight: float):
    with self._get_conn() as conn:
        conn.execute(
            "INSERT INTO weight_log (user_id, weight) VALUES (?, ?)",
            (user_id, weight)
        )

def get_weight_history(self, user_id: int, limit: int = 10) -> List[Dict]:
    with self._get_conn() as conn:
        rows = conn.execute(
            "SELECT weight, date FROM weight_log WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

# ── Food ───────────────────────────────────────────────────────────────

def log_food(self, user_id: int, description: str):
    with self._get_conn() as conn:
        conn.execute(
            "INSERT INTO food_log (user_id, description) VALUES (?, ?)",
            (user_id, description)
        )

def get_recent_food(self, user_id: int, limit: int = 5) -> List[Dict]:
    with self._get_conn() as conn:
        rows = conn.execute(
            "SELECT description, date FROM food_log WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

# ── Activity ───────────────────────────────────────────────────────────

def log_activity(self, user_id: int, description: str):
    with self._get_conn() as conn:
        conn.execute(
            "INSERT INTO activity_log (user_id, description) VALUES (?, ?)",
            (user_id, description)
        )

def get_recent_activity(self, user_id: int, limit: int = 5) -> List[Dict]:
    with self._get_conn() as conn:
        rows = conn.execute(
            "SELECT description, date FROM activity_log WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

# ── Analyses ───────────────────────────────────────────────────────────

def log_analysis(self, user_id: int, title: str, result: str):
    with self._get_conn() as conn:
        conn.execute(
            "INSERT INTO analyses_log (user_id, title, result) VALUES (?, ?, ?)",
            (user_id, title, result)
        )

def get_recent_analyses(self, user_id: int, limit: int = 3) -> List[Dict]:
    with self._get_conn() as conn:
        rows = conn.execute(
            "SELECT title, result, date FROM analyses_log WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

# ── Chat history ───────────────────────────────────────────────────────

def save_chat_message(self, user_id: int, role: str, content: str):
    with self._get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )

def get_chat_history(self, user_id: int, limit: int = 10) -> List[Dict]:
    with self._get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_history WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
```