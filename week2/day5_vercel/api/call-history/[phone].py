"""
Project 3: Get call history for a specific phone number.
GET /api/call-history/+1234567890
"""
from http.server import BaseHTTPRequestHandler
import os, json, urllib.parse


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Extract phone from path: /api/call-history/<phone>
        phone = self.path.split("/")[-1]
        phone = urllib.parse.unquote(phone)

        url = os.getenv("POSTGRES_URL", "") or os.getenv("POSTGRES_URL_NON_POOLING", "")
        if not url:
            body, status = json.dumps({"error": "POSTGRES_URL not set"}), 500
        else:
            try:
                import psycopg2, psycopg2.extras  # type: ignore
                conn = psycopg2.connect(url)
                cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(
                    "SELECT * FROM call_logs WHERE caller_number = %s ORDER BY created_at DESC LIMIT 50",
                    (phone,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    if r.get("created_at"):
                        r["created_at"] = r["created_at"].isoformat()
                cur.close()
                conn.close()
                body, status = json.dumps({"phone": phone, "calls": rows, "count": len(rows)}), 200
            except Exception as e:
                body, status = json.dumps({"error": str(e)}), 500

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
