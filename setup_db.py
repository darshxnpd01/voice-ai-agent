#!/usr/bin/env python3
"""
Database initialization script.
Run once to create the call_logs table.

Usage:
    python setup_db.py
"""

import os
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

POSTGRES_URL = os.getenv("POSTGRES_URL")


async def setup_database():
    if not POSTGRES_URL:
        print("❌ POSTGRES_URL not set in .env")
        return

    print("Connecting to PostgreSQL...")
    conn = await asyncpg.connect(POSTGRES_URL)

    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                id                 SERIAL PRIMARY KEY,
                caller_number      VARCHAR(20),
                called_number      VARCHAR(20),
                call_status        VARCHAR(50),
                detected_intent    VARCHAR(50),
                transcript_summary TEXT,
                duration_seconds   INTEGER,
                created_at         TIMESTAMP DEFAULT NOW()
            )
        """)
        print("✅ call_logs table created (or already exists)")

        # Verify by listing columns
        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'call_logs'
            ORDER BY ordinal_position
        """)
        print("\nTable schema:")
        for col in columns:
            print(f"  {col['column_name']:25} {col['data_type']}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(setup_database())
