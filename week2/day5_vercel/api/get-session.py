"""
Project 2: Get a Redis session by caller ID.
GET /api/get-session?caller_id=+1234567890
"""
from http.server import BaseHTTPRequestHandler
import os, json, urllib.parse, urllib.request


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed    = urllib.parse.urlparse(self.path)
        params    = dict(urllib.parse.parse_qsl(parsed.query))
        caller_id = params.get("caller_id", "unknown")

        url   = os.getenv("KV_REST_API_URL", "")
        token = os.getenv("KV_REST_API_TOKEN", "")

        if not url or not token:
            body, status = json.dumps({"error": "KV not configured"}), 500
        else:
            key = f"session:{caller_id}"
            try:
                req = urllib.request.Request(
                    f"{url}/get/{urllib.parse.quote(key)}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    result = json.loads(r.read())
                    body   = json.dumps({"caller_id": caller_id, "session": result.get("result")})
                    status = 200
            except Exception as e:
                body, status = json.dumps({"error": str(e)}), 500

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
