import sqlite3

conn = sqlite3.connect('./vcos.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print("Tables in DB:")
for t in tables:
    print(f"  {t[0]}")

conn.close()