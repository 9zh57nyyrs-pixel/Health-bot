import sqlite3

def init_db():
    conn = sqlite3.connect('health_bot.db')
    cursor = conn.cursor()
    # Таблица профиля
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_profiles 
                      (user_id INTEGER PRIMARY KEY, age INTEGER, gender TEXT, weight REAL, goals TEXT)''')
    # Таблица истории (вес, симптомы, анализы)
    cursor.execute('''CREATE TABLE IF NOT EXISTS health_logs 
                      (user_id INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                       type TEXT, value TEXT)''')
    conn.commit()
    conn.close()

def save_user(user_id, age=None, gender=None, weight=None):
    conn = sqlite3.connect('health_bot.db')
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO user_profiles (user_id, age, gender, weight)
                      VALUES (?, 
                              COALESCE(?, (SELECT age FROM user_profiles WHERE user_id = ?)),
                              COALESCE(?, (SELECT gender FROM user_profiles WHERE user_id = ?)),
                              COALESCE(?, (SELECT weight FROM user_profiles WHERE user_id = ?)))''', 
                   (user_id, age, user_id, gender, user_id, weight, user_id))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('health_bot.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row
