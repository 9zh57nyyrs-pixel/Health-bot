import sqlite3
from config import DATABASE_PATH


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            profile TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    conn.commit()
    conn.close()


def save_user(user_id, username, first_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user_id, username, first_name)
    )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row


def save_profile(user_id, profile):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET profile = ? WHERE user_id = ?", (profile, user_id))
    conn.commit()
    conn.close()


def add_message(user_id, role, content):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content)
    )
    conn.commit()
    conn.close()


def get_recent_messages(user_id, limit=30):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return list(reversed(rows))


def get_all_messages(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT role, content, created_at FROM messages WHERE user_id = ? ORDER BY created_at ASC",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def clear_messages(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
