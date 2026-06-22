"""GHOST — Personal AI Assistant backend.

FastAPI + Claude (via emergentintegrations w/ tool use) + OpenAI Whisper STT +
OpenAI TTS. Mongo stores conversations and memory facts. The Windows agent zip
is served from /api/agent/download for users who want real PC control.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai.speech_to_text import OpenAISpeechToText
from emergentintegrations.llm.openai.text_to_speech import OpenAITextToSpeech
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from skills import TOOL_DEFINITIONS, execute_tool

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ghost")

# ---- Clients ----
mongo_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = mongo_client[os.environ["DB_NAME"]]

EMERGENT_KEY = os.environ["EMERGENT_LLM_KEY"]
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
LLM_PROVIDER = "anthropic"

stt_client = OpenAISpeechToText(api_key=EMERGENT_KEY)
tts_client = OpenAITextToSpeech(api_key=EMERGENT_KEY)

SYSTEM_PROMPT = (
    "You are GHOST, a sleek, soft-spoken personal AI assistant with a slightly "
    "haunted-terminal vibe. You help the user with reasoning, lookups, math, "
    "and lightweight PC tasks (file ops, opening apps) — but currently you run "
    "inside the web sandbox, so any PC action is SIMULATED unless the user runs "
    "the downloadable Windows agent. Be concise, warm, and a little witty. "
    "Use tools decisively when helpful — don't over-explain. Keep voice replies short. "
    "Always confirm before irreversible actions (delete, send, spend)."
)

app = FastAPI(title="GHOST API")
api = APIRouter(prefix="/api")


# ---- Models ----
class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Stable id for this conversation.")
    message: str
    enabled_tools: Optional[List[str]] = None


class ChatResponse(BaseModel):
    session_id: str
    user_text: str
    assistant_text: str
    tool_calls: List[dict] = []


class FactIn(BaseModel):
    fact: str


class TTSIn(BaseModel):
    text: str
    voice: Optional[str] = "nova"


# ---- Tool format conversion (Anthropic-style -> OpenAI/litellm-style) ----
def _to_openai_tools(defs: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d["description"],
                "parameters": d["input_schema"],
            },
        }
        for d in defs
    ]


# ---- DB helpers ----
async def _load_history(session_id: str) -> List[dict]:
    doc = await db.conversations.find_one({"session_id": session_id}, {"_id": 0})
    return (doc or {}).get("messages", [])


async def _save_history(session_id: str, messages: List[dict]) -> None:
    await db.conversations.update_one(
        {"session_id": session_id},
        {"$set": {
            "session_id": session_id,
            "messages": messages,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )


async def _load_facts() -> List[str]:
    cursor = db.memory_facts.find({}, {"_id": 0, "fact": 1}).sort("created_at", -1)
    return [d["fact"] async for d in cursor]


async def _save_fact(fact: str) -> None:
    await db.memory_facts.insert_one({
        "id": str(uuid.uuid4()),
        "fact": fact,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


class _MemoryProxy:
    def __init__(self, initial: List[str]):
        self._data = list(initial)
        self.pending: List[str] = []

    def append(self, fact: str) -> None:
        self._data.append(fact)
        self.pending.append(fact)

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


def _filter_tools(enabled: Optional[List[str]]) -> list[dict]:
    if not enabled:
        return TOOL_DEFINITIONS
    return [t for t in TOOL_DEFINITIONS if t["name"] in set(enabled)]


async def _chat_with_tools(
    session_id: str, user_text: str, enabled: Optional[List[str]], memory: _MemoryProxy,
    prior_messages: List[dict]
) -> tuple[str, list[dict], list[dict]]:
    """Run a Claude tool-use loop. Returns (final_text, tool_call_log, new_messages_to_persist)."""
    tools = _to_openai_tools(_filter_tools(enabled))

    chat = LlmChat(
        api_key=EMERGENT_KEY,
        session_id=session_id,
        system_message=SYSTEM_PROMPT,
        initial_messages=prior_messages or None,
    ).with_model(LLM_PROVIDER, CLAUDE_MODEL).with_tools(tools)

    response = await chat.send_message_with_tools(UserMessage(text=user_text))
    tool_calls_log: list[dict] = []
    final_text: str = ""

    for _ in range(8):
        if not response.tool_calls:
            break
        for tc in response.tool_calls:
            args = tc.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception as parse_err:
                    logger.warning("tool args parse failed: %s", parse_err)
                    args = {}
            result_str = execute_tool(tc.name, args or {}, memory_store=memory)
            tool_calls_log.append({"name": tc.name, "input": args, "result": result_str})
            chat.add_tool_result(tc.id, result_str)
        response = await chat.send_message_with_tools()

    final_text = response.content or ""
    new_history = await chat.get_messages()
    return final_text, tool_calls_log, new_history


# ---- Routes ----
@api.get("/")
async def root():
    return {"service": "ghost-api", "model": CLAUDE_MODEL, "provider": LLM_PROVIDER, "status": "online"}


@api.get("/skills")
async def list_skills():
    return {
        "skills": [
            {"name": t["name"], "description": t["description"]}
            for t in TOOL_DEFINITIONS
        ]
    }


@api.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    prior = await _load_history(req.session_id)
    facts = await _load_facts()
    memory = _MemoryProxy(facts)

    final_text: str = ""
    tool_calls: list[dict] = []
    new_history: list[dict] = []
    try:
        final_text, tool_calls, new_history = await _chat_with_tools(
            req.session_id, req.message, req.enabled_tools, memory, prior
        )
    except Exception as e:
        logger.exception("Claude loop failed")
        raise HTTPException(status_code=500, detail=f"Claude error: {e}")

    for fact in memory.pending:
        await _save_fact(fact)
    await _save_history(req.session_id, new_history)

    return ChatResponse(
        session_id=req.session_id,
        user_text=req.message,
        assistant_text=final_text,
        tool_calls=tool_calls,
    )


@api.post("/chat/voice")
async def chat_voice(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
    enabled_tools: Optional[str] = Form(None),
    voice: str = Form("nova"),
):
    enabled_list = [s for s in (enabled_tools or "").split(",") if s] or None
    incoming_ext = Path(audio.filename or "audio.webm").suffix or ".webm"
    raw = await audio.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=incoming_ext) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    user_text: str = ""
    try:
        stt = await stt_client.transcribe(file=tmp_path, model="whisper-1", response_format="json")
        user_text = (getattr(stt, "text", None) or (stt.get("text") if isinstance(stt, dict) else "") or "").strip()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if not user_text:
        raise HTTPException(status_code=400, detail="Empty transcription")

    prior = await _load_history(session_id)
    facts = await _load_facts()
    memory = _MemoryProxy(facts)
    final_text, tool_calls, new_history = await _chat_with_tools(
        session_id, user_text, enabled_list, memory, prior
    )
    for fact in memory.pending:
        await _save_fact(fact)
    await _save_history(session_id, new_history)

    audio_bytes = await tts_client.generate_speech(
        text=(final_text or "I have nothing to say.")[:4000],
        model="tts-1", voice=voice, response_format="mp3",
    )

    return {
        "session_id": session_id,
        "user_text": user_text,
        "assistant_text": final_text,
        "tool_calls": tool_calls,
        "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
        "audio_mime": "audio/mpeg",
    }


@api.post("/chat/tts")
async def synthesize_speech(payload: TTSIn):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")
    audio_bytes = await tts_client.generate_speech(
        text=text[:4000], model="tts-1", voice=payload.voice or "nova", response_format="mp3"
    )
    return {"audio_base64": base64.b64encode(audio_bytes).decode("utf-8"), "audio_mime": "audio/mpeg"}


@api.get("/conversations/{session_id}")
async def get_conversation(session_id: str):
    history = await _load_history(session_id)
    flat: List[dict] = []
    for m in history:
        role = m.get("role")
        if role == "system" or role == "tool":
            continue
        content = m.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            text = ""
        tc_norm = []
        for tc in (m.get("tool_calls") or []):
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = fn.get("arguments")
            tc_norm.append({"name": fn.get("name"), "input": args})
        # skip totally empty assistant frames (pure tool call frames merge with next)
        if not text and not tc_norm and role == "assistant":
            continue
        flat.append({"role": role, "text": text, "tool_calls": tc_norm})
    return {"session_id": session_id, "messages": flat}


@api.delete("/conversations/{session_id}")
async def clear_conversation(session_id: str):
    await db.conversations.delete_one({"session_id": session_id})
    return {"cleared": True, "session_id": session_id}


@api.get("/memory/facts")
async def list_facts():
    return {"facts": await _load_facts()}


@api.post("/memory/facts")
async def add_fact(payload: FactIn):
    fact = (payload.fact or "").strip()
    if not fact:
        raise HTTPException(status_code=400, detail="Empty fact")
    await _save_fact(fact)
    return {"stored": fact}


@api.delete("/memory/facts")
async def clear_facts():
    await db.memory_facts.delete_many({})
    return {"cleared": True}


@api.get("/agent/download")
async def download_agent():
    buf = io.BytesIO()
    agent_dir = ROOT_DIR / "windows_agent"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in agent_dir.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                zf.write(p, arcname=p.relative_to(agent_dir.parent))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="ghost-windows-agent.zip"'},
    )


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def _shutdown():
    mongo_client.close()
