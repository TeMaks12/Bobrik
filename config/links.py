import sqlite3
import time
import logging
import os

logger = logging.getLogger(__name__)

LINKS_DB = 'bobrik/DataBases/links.db'

def ensure_links_db():
    os.makedirs('bobrik/DataBases', exist_ok=True)
    conn = sqlite3.connect(LINKS_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_links
                 (user_id INTEGER PRIMARY KEY,
                  group_id INTEGER,
                  group_name TEXT,
                  linked_at TEXT)''')
    conn.commit()
    conn.close()

def link_group(user_id, group_id, group_name):
    try:
        ensure_links_db()
        conn = sqlite3.connect(LINKS_DB)
        c = conn.cursor()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        c.execute('''INSERT OR REPLACE INTO user_links 
                     (user_id, group_id, group_name, linked_at) 
                     VALUES (?, ?, ?, ?)''',
                  (user_id, group_id, group_name, timestamp))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при привязке группы: {e}")
        return False

def unlink_group(user_id):
    try:
        ensure_links_db()
        conn = sqlite3.connect(LINKS_DB)
        c = conn.cursor()
        c.execute('DELETE FROM user_links WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при отвязке группы: {e}")
        return False

def get_linked_group(user_id):
    try:
        ensure_links_db()
        conn = sqlite3.connect(LINKS_DB)
        c = conn.cursor()
        c.execute('SELECT group_id, group_name FROM user_links WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Ошибка при получении привязанной группы: {e}")
        return None