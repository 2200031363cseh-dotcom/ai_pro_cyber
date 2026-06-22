"""GHOST — voice-enabled local Windows agent.

Push-to-talk loop:
  • Type `v` + Enter → speak → it auto-stops on ~1.5s silence (or 15s max).
  • Or just type your message and press Enter for text mode.
  • Type `exit` to quit.

Everything else (Claude + real PC skills) is identical to ghost.py.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv

from skills import ALL_TOOLS, DISPATCH

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    filename=ROOT / "ghost.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("ghost")

# ---- API setup ----------------------------------------------------------
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
VOICE = os.environ.get("TTS_VOICE", "nova")

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()

USE_EMERGENT = bool(EMERGENT_KEY) and not (
    ANTHROPIC_KEY and OPENAI_KEY and not ANTHROPIC_KEY.startswith("sk-ant-replace")
)

if USE_EMERGENT:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from emergentintegrations.llm.openai.speech_to_text import OpenAISpeechToText
    from emergentintegrations.llm.openai.text_to_speech import OpenAITextToSpeech
    stt_client = OpenAISpeechToText(api_key=EMERGENT_KEY)
    tts_client = OpenAITextToSpeech(api_key=EMERGENT_KEY)
    anthropic_client = None
    openai_client = None
else:
    from anthropic import Anthropic
    from openai import OpenAI
    if not ANTHROPIC_KEY or ANTHROPIC_KEY.startswith("sk-ant-replace"):
        print("ERROR: set ANTHROPIC_API_KEY (or EMERGENT_LLM_KEY) in .env")
        sys.exit(1)
    if not OPENAI_KEY:
        print("ERROR: set OPENAI_API_KEY (or EMERGENT_LLM_KEY) in .env for voice")
        sys.exit(1)
    anthropic_client = Anthropic(api_key=ANTHROPIC_KEY)
    openai_client = OpenAI(api_key=OPENAI_KEY)

SYSTEM = (
    "You are GHOST, a personal AI assistant running on the user's Windows PC. "
    "You have real hands: open apps, manipulate files, take screenshots, run "
    "guarded PowerShell. Always state your plan in ONE short sentence before "
    "calling a tool. Always confirm before irreversible actions. Keep spoken "
    "replies short — one or two sentences."
)

BANNER = r"""
   ▄████  ██░ ██  ▒█████    ██████ ▄▄▄█████▓
  ██▒ ▀█▒▓██░ ██▒▒██▒  ██▒▒██    ▒ ▓  ██▒ ▓▒
 ▒██░▄▄▄░▒██▀▀██░▒██░  ██▒░ ▓██▄   ▒ ▓██░ ▒░
 ░▓█  ██▓░▓█ ░██ ▒██   ██░  ▒   ██▒░ ▓██▓ ░
 ░▒▓███▀▒░▓█▒░██▓░ ████▓▒░▒██████▒▒  ▒██▒ ░
"""

# ---- Audio I/O ----------------------------------------------------------
SAMPLE_RATE = 16000  # Whisper happy at 16k

def record_until_silence(max_seconds: float = 15.0, silence_seconds: float = 1.5,
                         silence_rms: float = 0.012) -> str:
    """Record from default mic until ~silence_seconds of quiet (or max). Returns wav path."""
    print("🎙  listening… (auto-stops on silence)")
    block = 1024
    silence_blocks_needed = int(silence_seconds * SAMPLE_RATE / block)
    max_blocks = int(max_seconds * SAMPLE_RATE / block)
    audio_chunks: list[np.ndarray] = []
    silent_count = 0
    spoken = False

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=block) as stream:
        for _ in range(max_blocks):
            data, _ = stream.read(block)
            audio_chunks.append(data.copy())
            rms = float(np.sqrt(np.mean(data ** 2)))
            if rms > silence_rms:
                spoken = True
                silent_count = 0
            elif spoken:
                silent_count += 1
                if silent_count >= silence_blocks_needed:
                    break

    audio = np.concatenate(audio_chunks, axis=0)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    sf.write(tmp.name, audio, SAMPLE_RATE, subtype="PCM_16")
    tmp.close()
    return tmp.name


def play_audio_bytes(data: bytes) -> None:
    """Play mp3 (or wav) bytes via sounddevice. Decodes via soundfile."""
    buf = io.BytesIO(data)
    try:
        audio, sr = sf.read(buf, dtype="float32")
    except Exception:
        # If soundfile can't decode mp3 (no libsndfile mp3 support), write to temp and use winsound
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(data)
            path = f.name
        if sys.platform == "win32":
            os.startfile(path)  # opens in default media player
        else:
            print(f"(audio saved to {path})")
        return
    sd.play(audio, sr)
    sd.wait()


# ---- LLM + voice calls --------------------------------------------------
async def speech_to_text(wav_path: str) -> str:
    if USE_EMERGENT:
        r = await stt_client.transcribe(file=wav_path, model="whisper-1", response_format="json")
        return (getattr(r, "text", None) or (r.get("text") if isinstance(r, dict) else "") or "").strip()
    with open(wav_path, "rb") as f:
        r = openai_client.audio.transcriptions.create(model="whisper-1", file=f)
    return (r.text or "").strip()


async def text_to_speech(text: str) -> bytes:
    if USE_EMERGENT:
        return await tts_client.generate_speech(
            text=text[:4000], model="tts-1", voice=VOICE, response_format="mp3",
        )
    r = openai_client.audio.speech.create(model="tts-1", voice=VOICE, input=text[:4000])
    return r.content


# ---- Tool execution -----------------------------------------------------
def run_tool(name: str, args: dict) -> str:
    fn = DISPATCH.get(name)
    if not fn:
        return json.dumps({"error": f"unknown tool {name}"})
    log.info("tool=%s args=%s", name, args)
    try:
        result = fn(**(args or {}))
    except Exception as e:
        log.exception("tool error")
        result = {"error": str(e)}
    log.info("tool=%s result=%s", name, result)
    return json.dumps(result, default=str)


# ---- Claude tool-use loop (handles both code paths) ---------------------
def _anthropic_tools():
    return ALL_TOOLS  # already in Anthropic format


def _openai_tools():
    return [
        {"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"]
        }} for t in ALL_TOOLS
    ]


async def think_and_act(user_text: str, history: list) -> str:
    history.append({"role": "user", "content": user_text})

    if USE_EMERGENT:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id="ghost-desktop",
            system_message=SYSTEM,
            initial_messages=history[:-1] or None,
        ).with_model("anthropic", MODEL).with_tools(_openai_tools())
        resp = await chat.send_message_with_tools(UserMessage(text=user_text))
        for _ in range(8):
            if not resp.tool_calls:
                break
            for tc in resp.tool_calls:
                args = tc.arguments
                if isinstance(args, str):
                    try: args = json.loads(args)
                    except Exception: args = {}
                print(f"  ↳ {tc.name}({json.dumps(args)})")
                out = run_tool(tc.name, args or {})
                chat.add_tool_result(tc.id, out)
            resp = await chat.send_message_with_tools()
        text = resp.content or ""
        # rebuild history from chat
        history.clear()
        history.extend(await chat.get_messages())
        # strip system from history we keep locally
        history[:] = [m for m in history if m.get("role") != "system"]
        return text

    # Direct Anthropic path
    msgs = list(history)
    for _ in range(8):
        r = anthropic_client.messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM,
            tools=_anthropic_tools(), messages=msgs,
        )
        blocks = []
        for b in r.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        msgs.append({"role": "assistant", "content": blocks})
        if r.stop_reason == "tool_use":
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    print(f"  ↳ {b.name}({json.dumps(b.input)})")
                    out = run_tool(b.name, b.input or {})
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            msgs.append({"role": "user", "content": results})
            continue
        text = "\n".join(b.text for b in r.content if b.type == "text").strip()
        history.clear(); history.extend(msgs)
        return text
    return ""


# ---- Main loop ----------------------------------------------------------
async def main() -> None:
    print(BANNER)
    print(f"GHOST voice agent online · model: {MODEL} · voice: {VOICE}")
    print(f"Backend: {'Emergent LLM key' if USE_EMERGENT else 'direct Anthropic + OpenAI'}\n")
    print("Type your message, or `v` to speak. `exit` to quit.\n")
    history: list = []

    while True:
        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye."); return
        if not cmd:
            continue
        if cmd.lower() in {"exit", "quit", ":q"}:
            return

        if cmd.lower() == "v":
            wav = record_until_silence()
            try:
                user_text = await speech_to_text(wav)
            finally:
                try: os.remove(wav)
                except OSError: pass
            if not user_text:
                print("(nothing heard)\n"); continue
            print(f"you (heard): {user_text}")
        else:
            user_text = cmd

        log.info("user: %s", user_text)
        try:
            reply = await think_and_act(user_text, history)
        except Exception as e:
            log.exception("LLM error")
            print(f"⚠ {e}\n"); continue

        if reply:
            print(f"\nGHOST: {reply}\n")
            log.info("assistant: %s", reply)
            try:
                audio = await text_to_speech(reply)
                play_audio_bytes(audio)
            except Exception as e:
                log.warning("TTS failed: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
