"""Quick check that DATABASE_URL in .env can reach Supabase."""
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL is not set. Add it to services/ingestion/.env")

with psycopg.connect(url) as conn:
    count = conn.execute("SELECT count(*) FROM skills").fetchone()[0]
    print(f"Connected. skills table has {count} rows.")