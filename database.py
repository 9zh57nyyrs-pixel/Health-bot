import sqlite3
import logging
from datetime import datetime

DB_PATH = 'health_bot.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_profiles 
                      (user_id INTEGER PRIMARY KEY, age INTEGER, gender TEXT, 
                       weight REAL, height REAL, chronic_diseases TEXT, created_at DATETIME)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, time DATETIME)''')
    conn.commit()
    conn.close()

def save_user(user_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM user_profiles WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO user_profiles (user_id, created_at) VALUES (?, ?)", (user_id, datetime.now()))
    
    for key, value in kwargs.items():
        cursor.execute(f"UPDATE user_profiles SET {key} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return dict(res) if res else None
