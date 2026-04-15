"""
Project 4: Plivo IVR digit handler.
POST /api/handle-input  — Plivo calls this with the digit the caller pressed.
"""
from http.server import BaseHTTPRequestHandler
import os, json, urllib.parse


def update_session(caller_id: str, step: str, digit: str):
    url   = os.getenv("KV_REST_API_URL", "")
    token = os.getenv("KV_REST_API_TOKEN", "")
    if not url or not token:
        return
    import urllib.request

    # First read existing session to preserve from/to/call_uuid
    existing = {}
    try:
        key = f"session:{caller_id}"
        req = urllib.request.Request(
            f"{url}/get/{urllib.parse.quote(key)}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            result = json.loads(r.read())
            if result.get("result"):
                existing = json.loads(result["result"])
    except Exception:
        pass

    existing.update({"step": step, "digit_pressed": digit})
    data = json.dumps(existing)
    key  = f"session:{caller_id}"
    req  = urllib.request.Request(
        f"{url}/set/{urllib.parse.quote(key)}/{urllib.parse.quote(data)}?ex=1800",
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def log_digit_db(caller: str, digit: str, step: str):
    db_url = os.getenv("POSTGRES_URL", "") or os.getenv("POSTGRES_URL_NON_POOLING", "")
    if not db_url:
        return
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO call_logs (caller_number, called_number, digit_pressed, call_status, created_at) VALUES (%s, %s, %s, %s, NOW())",
            (caller, "IVR", digit, step),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


RESPONSES = {
    "1": ("hours", "We are open Monday through Sunday, 5 PM to 10 PM. We are located at 123 Main Street. Goodbye!"),
    "2": ("reservation", "To make a reservation, please call us back during business hours or visit our website. Goodbye!"),
    "3": ("replay", None),  # replay menu
}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length).decode()
        params = dict(urllib.parse.parse_qsl(body))

        digit  = params.get("Digits", "")
        caller = params.get("From", "unknown")

        if digit in RESPONSES:
            step, message = RESPONSES[digit]
            update_session(caller, step, digit)
            log_digit_db(caller, digit, step)

            if step == "replay":
                xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <GetDigits action="https://ivr-sessions.vercel.app/api/handle-input" method="POST" numDigits="1" timeout="10" retries="3">
    <Speak>Press 1 for hours and location. Press 2 to make a reservation. Press 3 to hear this menu again.</Speak>
  </GetDigits>
</Response>"""
            else:
                xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Speak>{message}</Speak>
</Response>"""
        else:
            update_session(caller, "invalid_input", digit)
            log_digit_db(caller, digit, "invalid_input")
            xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <GetDigits action="https://ivr-sessions.vercel.app/api/handle-input" method="POST" numDigits="1" timeout="10" retries="3">
    <Speak>Invalid option. Press 1 for hours. Press 2 for reservations. Press 3 to replay.</Speak>
  </GetDigits>
</Response>"""

        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.end_headers()
        self.wfile.write(xml.encode())

    def log_message(self, *args):
        pass
