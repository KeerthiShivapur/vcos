import sqlite3

conn = sqlite3.connect('./vcos.db')
cursor = conn.cursor()

# Check organizations
cursor.execute('SELECT name, slug FROM organizations')
orgs = cursor.fetchall()
print("Organizations:")
for o in orgs:
    print(f"  {o}")

# Check users
cursor.execute('SELECT email, full_name FROM users')
users = cursor.fetchall()
print("\nUsers:")
for u in users:
    print(f"  {u}")

conn.close()