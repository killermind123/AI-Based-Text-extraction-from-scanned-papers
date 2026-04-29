import sqlite3
import os

DATABASE_NAME = "database.db"

def get_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_time TIMESTAMP,
            processing_status TEXT DEFAULT 'uploaded',
            document_type TEXT,
            extracted_text TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Extracted fields table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extracted_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            field_value TEXT,
            confidence REAL,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)

    # Indexes for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_user 
        ON documents(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_fields_document 
        ON extracted_fields(document_id)
    """)

    conn.commit()
    conn.close()
    print("Database initialised successfully")