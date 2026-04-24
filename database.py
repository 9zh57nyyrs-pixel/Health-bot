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
            age INTEGER,
            gender TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS health_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            record_type TEXT,
            value TEXT,
            notes TEXT,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
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


def save_health_record(user_id, record_type, value, notes=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO health_records (user_id, record_type, value, notes) VALUES (?, ?, ?, ?)",
        (user_id, record_type, value, notes)
    )
    conn.commit()
    conn.close()


def get_health_records(user_id, record_type=None, limit=10):
    conn = get_connection()
    c = conn.cursor()
    if record_type:
        c.execute(
            "SELECT * FROM health_records WHERE user_id=? AND record_type=? ORDER BY recorded_at DESC LIMIT ?",
            (user_id, record_type, limit)
        )
    else:
        c.execute(
            "SELECT * FROM health_records WHERE user_id=? ORDER BY recorded_at DESC LIMIT ?",
            (user_id, limit)
        )
    rows = c.fetchall()
    conn.close()
    return rows


def save_conversation(user_id, role, content):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content)
    )
    conn.commit()
    conn.close()


def get_conversation_history(user_id, limit=20):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM conversations WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return list(reversed(rows))


def get_user_info(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user


def update_user_info(user_id, age=None, gender=None):
    conn = get_connection()
    c = conn.cursor()
    if age is not None:
        c.execute("UPDATE users SET age=? WHERE user_id=?", (age, user_id))
    if gender is not None:
        c.execute("UPDATE users SET gender=? WHERE user_id=?", (gender, user_id))
    conn.commit()
    conn.close()
