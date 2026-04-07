"""
Day 6 - Production Server for Railway Deployment
=================================================
This is a copy of the Day 4 server, hardened for production:
- Reads PORT from environment (Railway sets this automatically)
- All config from environment variables (no .env file in production)
- Proper logging for Railway's log viewer
- Health check endpoint for Railway monitoring

To deploy to Railway:
  1. Create Railway account at railway.app
  2. Install CLI: npm install -g @railway/cli
  3. Login: railway login
  4. cd to this folder
  5. railway init
  6. Add environment variables in Railway dashboard (see railway.toml)
  7. railway up

After deployment:
  - Get your Railway URL from the dashboard
  - Set WEBSOCKET_BASE_URL = your-app.up.railway.app (in Railway env vars)
  - Update Plivo Answer URL to: https://your-app.up.railway.app/answer
  - No more ngrok needed!
"""

# This file re-uses the same server.py from day4 — just copy it here
# The Dockerfile already handles this by copying all files

import os
import sys

# Add parent directory to path so we can import from day4_pipecat_plivo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import and run the same app (dotenv loading is skipped in production — env vars are set directly)
from day4_pipecat_plivo.server import app
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
