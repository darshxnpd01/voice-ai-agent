"""
Project 3: Initialize Postgres tables. Hit this once in browser after deploy.
GET /api/setup-db
"""
from http.server import BaseHTTPRequestHandler
import os, json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = os.getenv("POSTGRES_URL", "") or os.getenv("POSTGRES_URL_NON_POOLING", "")
        if not url:
            body = json.dumps({"error": "POSTGRES_URL not set"})
            status = 500
        else:
            try:
                import psycopg2  # type: ignore
                conn = psycopg2.connect(url)
                cur  = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS call_logs (
                        id SERIAL PRIMARY KEY,
                        caller_number TEXT,
                        called_number TEXT,
                        call_status TEXT DEFAULT 'started',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                conn.commit()
                cur.close()
                conn.close()
                body   = json.dumps({"message": "Table created successfully"})
                status = 200
            except Exception as e:
                body   = json.dumps({"error": str(e)})
                status = 500

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
