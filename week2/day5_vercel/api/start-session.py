"""
Project 2: Start a Redis session for a caller.
POST /api/start-session?caller_id=+1234567890
"""
from http.server import BaseHTTPRequestHandler
import os, json, urllib.parse, urllib.request
from datetime import datetime, timezone


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        parsed    = urllib.parse.urlparse(self.path)
        params    = dict(urllib.parse.parse_qsl(parsed.query))
        caller_id = params.get("caller_id", "unknown")

        url   = os.getenv("KV_REST_API_URL", "")
        token = os.getenv("KV_REST_API_TOKEN", "")

        if not url or not token:
            body, status = json.dumps({"error": "KV_REST_API_URL/TOKEN not set"}), 500
        else:
            key  = f"session:{caller_id}"
            data = json.dumps({"step": "greeting", "started_at": datetime.now(timezone.utc).isoformat()})
            try:
                req = urllib.request.Request(
                    f"{url}/set/{urllib.parse.quote(key)}/{urllib.parse.quote(data)}?ex=1800",
                    method="GET",
                    headers={"Authorization": f"Bearer {token}"},
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    body   = json.dumps({"message": "session started", "caller_id": caller_id, "ttl": 1800})
                    status = 200
            except Exception as e:
                body, status = json.dumps({"error": str(e)}), 500

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
