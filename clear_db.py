import sqlite3

conn = sqlite3.connect('data/extractions.db')
cursor = conn.cursor()
cursor.execute("DELETE FROM logs")
cursor.execute("DELETE FROM extractions")
cursor.execute("DELETE FROM sqlite_sequence WHERE name='extractions'")
cursor.execute("DELETE FROM sqlite_sequence WHERE name='logs'")
conn.commit()
conn.close()
print("Database cleared successfully!")
