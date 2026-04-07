"""
Project 1: Webhook test endpoint — echoes back whatever Plivo POSTs.
POST /api/webhook-test
"""
from http.server import BaseHTTPRequestHandler
import json, urllib.parse


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length).decode()
        body   = json.dumps({
            "received": dict(urllib.parse.parse_qsl(raw)),
            "raw": raw,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
