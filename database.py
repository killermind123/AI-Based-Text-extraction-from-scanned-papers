import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", None)

_postgres_available = None


def is_postgres():
    """Check if PostgreSQL is available and cache result."""
    global _postgres_available
    if _postgres_available is not None:
        return _postgres_available

    if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
        _postgres_available = False
        return False

    try:
        import psycopg2
        conn = psycopg2.connect(
            DATABASE_URL,
            sslmode="require",
            connect_timeout=5,
        )
        conn.close()
        _postgres_available = True
        print("PostgreSQL available!")
        return True
    except Exception as e:
        print(f"PostgreSQL not available — using SQLite: {e}")
        _postgres_available = False
        return False


def get_connection():
    """Returns PostgreSQL or SQLite connection."""
    if is_postgres():
        import psycopg2
        conn = psycopg2.connect(
            DATABASE_URL,
            sslmode="require",
            connect_timeout=5,  
        )
        return conn

    import sqlite3
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def execute(cursor, sql, params=()):
    """
    Execute SQL with correct placeholder.
    PostgreSQL uses %s, SQLite uses ?
    """
    if not is_postgres():
        sql = sql.replace("%s", "?")
    cursor.execute(sql, params)


def row_to_dict(cursor, row):
    """Convert a single row to dictionary."""
    if row is None:
        return None
    try:
        return dict(row)
    except Exception:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))


def rows_to_dicts(cursor, rows):
    """Convert list of rows to list of dicts."""
    if not rows:
        return []
    try:
        return [dict(row) for row in rows]
    except Exception:
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]


def fetchone(cursor):
    """Fetch one row as dict."""
    return row_to_dict(cursor, cursor.fetchone())


def fetchall(cursor):
    """Fetch all rows as list of dicts."""
    return rows_to_dicts(cursor, cursor.fetchall())


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    postgres = is_postgres()

    if postgres:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_fields (
                id SERIAL PRIMARY KEY,
                document_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                field_value TEXT,
                confidence REAL,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_user
            ON documents(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_fields_document
            ON extracted_fields(document_id)
        """)

    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                field_value TEXT,
                confidence REAL,
                FOREIGN KEY (document_id) REFERENCES extracted_fields(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_user
            ON documents(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_fields_document
            ON extracted_fields(document_id)
        """)

    conn.commit()
    cursor.close()
    conn.close()
    print("Database initialised successfully")