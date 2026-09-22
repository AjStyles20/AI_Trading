import sqlite3
import os
import json

DB_PATH = r'c:\CODES\Python\AI_Trading\database\astral.db'

def check_db():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM settings")
        rows = cursor.fetchall()
        print(f"Settings rows: {rows}")
        
        if not rows:
            print("Inserting default row...")
            cursor.execute("INSERT INTO settings (id, api_keys, theme, paper_trading) VALUES (1, '{}', 'dark', 1)")
            conn.commit()
            print("Default row inserted.")
    except Exception as e:
        print(f"Error checking DB: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_db()
