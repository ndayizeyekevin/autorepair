import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL")

if not url:
    raise SystemExit("DATABASE_URL not found. Check your .env file.")

with psycopg.connect(url, connect_timeout=30) as conn:
    row = conn.execute("SELECT current_database(), current_user, version()").fetchone()
    print("Connected!")
    print("Database:", row[0])
    print("User:", row[1])
    print("Server:", row[2])