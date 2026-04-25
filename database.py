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
        CREATE TABLE IF NOT EXISTS conversations (
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
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user


def update_profile(user_id, profile_text):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET profile=? WHERE user_id=?", (profile_text, user_id))
    conn.commit()
    conn.close()


def save_message(user_id, role, content):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content)
    )
    conn.commit()
    conn.close()


def get_history(user_id, limit=40):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT role, content, created_at FROM conversations WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return list(reversed(rows))


def get_full_history(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT role, content, created_at FROM conversations WHERE user_id=? ORDER BY created_at ASC",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def clear_history(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM conversations WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
