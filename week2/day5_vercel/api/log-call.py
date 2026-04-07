"""
Project 3: Insert a call log record.
POST /api/log-call  body: {"caller": "+1...", "called": "+1...", "status": "completed"}
"""
from http.server import BaseHTTPRequestHandler
import os, json


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data   = json.loads(self.rfile.read(length) or b"{}")

        url = os.getenv("POSTGRES_URL", "") or os.getenv("POSTGRES_URL_NON_POOLING", "")
        if not url:
            body, status = json.dumps({"error": "POSTGRES_URL not set"}), 500
        else:
            try:
                import psycopg2  # type: ignore
                conn = psycopg2.connect(url)
                cur  = conn.cursor()
                cur.execute(
                    "INSERT INTO call_logs (caller_number, called_number, call_status) VALUES (%s, %s, %s) RETURNING id",
                    (data.get("caller", "unknown"), data.get("called", "unknown"), data.get("status", "started")),
                )
                row_id = cur.fetchone()[0]
                conn.commit()
                cur.close()
                conn.close()
                body, status = json.dumps({"id": row_id, "message": "logged"}), 200
            except Exception as e:
                body, status = json.dumps({"error": str(e)}), 500

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
