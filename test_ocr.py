import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

for table in tables:
    table_name = table[0]

    # Skip internal SQLite table
    if table_name == "sqlite_sequence":
        continue

    print(f"\n📦 TABLE: {table_name}")
    print("-" * 50)

    # Get all rows from table
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    if not rows:
        print("No data found.")
    else:
        for row in rows:
            print(row)

conn.close()