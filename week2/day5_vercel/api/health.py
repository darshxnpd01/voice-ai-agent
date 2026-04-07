"""
Project 5: Health check endpoint — tests Redis + Postgres connectivity.
GET /api/health
"""
from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.error
from datetime import datetime, timezone


def check_redis() -> str:
    url   = os.getenv("KV_REST_API_URL", "")
    token = os.getenv("KV_REST_API_TOKEN", "")
    if not url or not token:
        return "not configured"
    try:
        req = urllib.request.Request(
            f"{url}/ping",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return "ok" if r.status == 200 else f"error {r.status}"
    except Exception as e:
        return f"error: {e}"


def check_postgres() -> str:
    url = os.getenv("POSTGRES_URL", "") or os.getenv("POSTGRES_URL_NON_POOLING", "")
    if not url:
        return "not configured"
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(url, connect_timeout=3)
        conn.close()
        return "ok"
    except Exception as e:
        return f"error: {e}"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        redis_status    = check_redis()
        postgres_status = check_postgres()
        all_ok = redis_status == "ok" and postgres_status in ("ok", "not configured")
        body = json.dumps({
            "status":    "healthy" if all_ok else "unhealthy",
            "redis":     redis_status,
            "postgres":  postgres_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
