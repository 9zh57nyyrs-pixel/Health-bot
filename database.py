import sqlite3
import logging

DB_PATH = 'health_bot.db'

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Таблица профиля
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_profiles 
                          (user_id INTEGER PRIMARY KEY, 
                           age INTEGER, gender TEXT, weight REAL, 
                           chronic_diseases TEXT, goals TEXT, 
                           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        # Таблица медицинских показателей (сахар, холестерин и т.д.)
        cursor.execute('''CREATE TABLE IF NOT EXISTS health_metrics 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT,
                           user_id INTEGER, 
                           metric_name TEXT, 
                           value REAL, 
                           unit TEXT,
                           date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Database init error: {e}")

def save_user_profile(user_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    columns = ', '.join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    
    # Сначала проверяем существование
    cursor.execute("SELECT user_id FROM user_profiles WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        cursor.execute(f"UPDATE user_profiles SET {columns} WHERE user_id = ?", values)
    else:
        cols = ', '.join(kwargs.keys())
        placeholders = ', '.join(['?' * len(kwargs)])
        cursor.execute(f"INSERT INTO user_profiles (user_id, {cols}) VALUES (?, {placeholders})", [user_id] + list(kwargs.values()))
    conn.commit()
    conn.close()

def get_full_context(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    profile = cursor.fetchone()
    cursor.execute("SELECT * FROM health_metrics WHERE user_id = ? ORDER BY date DESC LIMIT 10", (user_id,))
    metrics = cursor.fetchall()
    conn.close()
    return profile, metrics
