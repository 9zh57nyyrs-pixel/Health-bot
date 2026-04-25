import sqlite3
import os

DB_PATH = 'health_bot.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Таблица профиля
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_profiles 
                      (user_id INTEGER PRIMARY KEY, age INTEGER, gender TEXT, weight REAL)''')
    conn.commit()
    conn.close()

def save_user(user_id, age=None, gender=None, weight=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Обновляем или вставляем данные
    cursor.execute('''INSERT INTO user_profiles (user_id, age, gender, weight) 
                      VALUES (?, ?, ?, ?) 
                      ON CONFLICT(user_id) DO UPDATE SET 
                      age=COALESCE(?, age), 
                      gender=COALESCE(?, gender), 
                      weight=COALESCE(?, weight)''', 
                   (user_id, age, gender, weight, age, gender, weight))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
