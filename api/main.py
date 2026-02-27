"""FastAPI backend for the RFS scenario generator.

Endpoints:
  POST /api/chat                      Create a new chat session
  POST /api/chat/{session_id}/message Send a message, get SSE stream back
  GET  /api/chat/{session_id}         Get session message history
  GET  /api/file/{filename}           Serve generated .xosc / .mp4 / .jpg
  GET  /api/health                    Health check
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from api.pipeline import GENERATED_DIR

app = FastAPI(title="RFS Scenario Generator API")

_allowed_origins = [
    "http://localhost:5173",
    "http://localhost:4173",
]
if _extra := os.environ.get("ALLOWED_ORIGIN", ""):
    _allowed_origins.append(_extra)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class MessageRequest(BaseModel):
    content: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def create_chat():
    """Create a new chat session. Returns a session_id."""
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}


@app.post("/api/chat/{session_id}/message")
async def send_message(session_id: str, req: MessageRequest):
    """Send a user message. Returns an SSE stream of agent events."""
    if not req.content.strip():
        raise HTTPException(status_code=422, detail="Message content cannot be empty")

    from api.chat_graph import stream_chat

    return StreamingResponse(
        stream_chat(session_id, req.content.strip()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/chat/{session_id}")
async def get_chat(session_id: str):
    """Get the message history for a session."""
    from api.chat_graph import get_chat_history

    messages = get_chat_history(session_id)
    return {"session_id": session_id, "messages": messages}


@app.get("/api/file/{filename}")
async def serve_file(filename: str):
    """Serve a generated file (.xosc, .mp4, .jpg)."""
    # Prevent path traversal
    path = GENERATED_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_types = {
        ".mp4": "video/mp4",
        ".jpg": "image/jpeg",
        ".xosc": "application/xml",
        ".json": "application/json",
    }
    media_type = media_types.get(path.suffix, "application/octet-stream")
    return FileResponse(str(path), media_type=media_type)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Deploy webhook ────────────────────────────────────────────────────────────

DEPLOY_SCRIPT = Path(__file__).resolve().parent.parent / "deploy.sh"


@app.post("/api/deploy")
async def deploy_webhook(request: Request):
    """GitHub push webhook — validates signature, then runs deploy.sh detached."""
    secret = os.environ.get("DEPLOY_SECRET", "")
    if not secret:
        raise HTTPException(403, "Deploy webhook not configured")

    body = await request.body()

    # Verify HMAC-SHA256 signature from GitHub
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Invalid signature")

    payload = json.loads(body)
    if payload.get("ref") != "refs/heads/main":
        return {"status": "skipped", "reason": "not main branch"}

    # Run deploy script detached so it survives the service restart
    subprocess.Popen(
        ["bash", str(DEPLOY_SCRIPT)],
        stdout=open("/tmp/rfs-deploy.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    logger.info("Deploy triggered for %s", payload.get("after", "unknown")[:8])
    return {"status": "deploying"}
