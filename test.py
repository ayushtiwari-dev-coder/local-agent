from database.connection import DATABASE_PATH, get_connection

print(f"The live database is located exactly here:\n{DATABASE_PATH}\n")

conn = get_connection()
rows = conn.execute("SELECT id, tool_name, created_at FROM tool_logs ORDER BY id DESC LIMIT 5;").fetchall()

print("The 5 most recent tool logs in this database:")
for row in rows:
    print(f"Log ID: {row['id']} | Tool: {row['tool_name']} | Time: {row['created_at']}")
    
conn.close()