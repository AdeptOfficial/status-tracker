#!/usr/bin/env python3
"""
Standalone webhook capture server for investigation.

Run this temporarily to capture raw webhook payloads from:
- Jellyseerr
- Radarr
- Sonarr

Usage:
    python capture_server.py

Then temporarily point your webhooks to this server (port 8199).
Payloads are saved to ./captured/ with timestamps.
"""

import json
import os
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="Webhook Capture Server")

# Create output directory
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "captured")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def save_payload(source: str, payload: dict):
    """Save payload to file with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{source}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✓ Saved: {filename}")
    return filename


@app.post("/hooks/jellyseerr")
async def capture_jellyseerr(request: Request):
    """Capture Jellyseerr webhook."""
    payload = await request.json()
    filename = save_payload("jellyseerr", payload)

    # Log key info
    notif_type = payload.get("notification_type", "unknown")
    subject = payload.get("subject", "unknown")
    print(f"  → Jellyseerr: {notif_type} - {subject}")

    return JSONResponse({"status": "captured", "file": filename})


@app.post("/hooks/radarr")
async def capture_radarr(request: Request):
    """Capture Radarr webhook."""
    payload = await request.json()
    filename = save_payload("radarr", payload)

    # Log key info
    event_type = payload.get("eventType", "unknown")
    movie_title = payload.get("movie", {}).get("title", "unknown")
    print(f"  → Radarr: {event_type} - {movie_title}")

    return JSONResponse({"status": "captured", "file": filename})


@app.post("/hooks/sonarr")
async def capture_sonarr(request: Request):
    """Capture Sonarr webhook."""
    payload = await request.json()
    filename = save_payload("sonarr", payload)

    # Log key info
    event_type = payload.get("eventType", "unknown")
    series_title = payload.get("series", {}).get("title", "unknown")
    episodes = payload.get("episodes", [])
    ep_info = f"{len(episodes)} episodes" if episodes else ""
    print(f"  → Sonarr: {event_type} - {series_title} ({ep_info})")

    return JSONResponse({"status": "captured", "file": filename})


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "captured_dir": OUTPUT_DIR}


if __name__ == "__main__":
    print("=" * 50)
    print("Webhook Capture Server")
    print("=" * 50)
    print(f"Output directory: {OUTPUT_DIR}")
    print()
    print("Endpoints:")
    print("  POST /hooks/jellyseerr")
    print("  POST /hooks/radarr")
    print("  POST /hooks/sonarr")
    print("  GET  /health")
    print()
    print("Temporarily point your webhooks to port 8199")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=8199)
