"""
Project 4: Plivo IVR answer webhook.
POST /api/answer  — Plivo calls this when someone dials your number.
Returns XML that plays a greeting and collects a DTMF digit.
"""
from http.server import BaseHTTPRequestHandler
import os, json, urllib.parse
from datetime import datetime, timezone


def store_session(caller_id: str, called_id: str, call_uuid: str):
    """Store call session in Redis via Upstash REST API."""
    url   = os.getenv("KV_REST_API_URL", "")
    token = os.getenv("KV_REST_API_TOKEN", "")
    if not url or not token:
        return
    import urllib.request
    key  = f"session:{caller_id}"
    data = json.dumps({
        "step": "greeting",
        "from": caller_id,
        "to": called_id,
        "call_uuid": call_uuid,
        "digit_pressed": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    req  = urllib.request.Request(
        f"{url}/set/{urllib.parse.quote(key)}/{urllib.parse.quote(data)}?ex=1800",
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def log_call_db(caller: str, called: str, call_uuid: str):
    """Insert a call_log row into Postgres."""
    url = os.getenv("POSTGRES_URL", "") or os.getenv("POSTGRES_URL_NON_POOLING", "")
    if not url:
        return
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(url)
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO call_logs (caller_number, called_number, call_uuid, call_status, created_at) VALUES (%s, %s, %s, 'started', NOW())",
            (caller, called, call_uuid),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        import sys
        print(f"DB ERROR: {e}", file=sys.stderr)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length).decode()
        params = dict(urllib.parse.parse_qsl(body))

        caller    = params.get("From", "unknown")
        called    = params.get("To", "unknown")
        call_uuid = params.get("CallUUID", "unknown")

        store_session(caller, called, call_uuid)
        log_call_db(caller, called, call_uuid)

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <GetDigits action="https://ivr-sessions.vercel.app/api/handle-input" method="POST" numDigits="1" timeout="10" retries="3">
    <Speak>Welcome to Mario's Italian Kitchen.
      Press 1 for hours and location.
      Press 2 to make a reservation.
      Press 3 to hear this menu again.</Speak>
  </GetDigits>
  <Speak>We did not receive your input. Goodbye.</Speak>
</Response>"""

        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.end_headers()
        self.wfile.write(xml.encode())

    def log_message(self, *args):
        pass
