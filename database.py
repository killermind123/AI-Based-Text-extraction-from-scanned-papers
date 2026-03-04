import sqlite3
import os

DATABASE_NAME = "database.db"

def get_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():

    try:
        if os.path.exists(DATABASE_NAME):
            os.remove(DATABASE_NAME)
    except PermissionError:
        print("Database file is in use. Skipping deletion.")


    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS documents")

    

    # Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        file_name TEXT,
        file_path TEXT,
        upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'uploaded',
        extracted_text TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS extracted_fields (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER,
        field_name TEXT,
        field_value TEXT,
        confidence REAL,
        FOREIGN KEY (document_id) REFERENCES documents(id)
    )
    """)


    conn.commit()
    conn.close()