"""GHOST — voice-enabled local Windows agent (no private deps).

Uses the standard `openai` Python SDK against ANY OpenAI-compatible endpoint:
  • Emergent proxy (free with EMERGENT_LLM_KEY)   → covers Claude + Whisper + TTS
  • OR direct OpenAI                              → if user sets OPENAI_API_KEY
  • For direct Claude, the `anthropic` SDK is used with ANTHROPIC_API_KEY

Push-to-talk loop:
  • Type `v` + Enter → speak → auto-stops on ~1.5s silence (or 15s max).
  • Or just type your message and press Enter for text mode.
  • Type `exit` to quit.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv
from openai import OpenAI

from skills import ALL_TOOLS, DISPATCH

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    filename=ROOT / "ghost.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("ghost")

# ---- Config -------------------------------------------------------------
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
VOICE = os.environ.get("TTS_VOICE", "nova")
EMERGENT_PROXY = "https://integrations.emergentagent.com/llm"

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

# Decide routing
if EMERGENT_KEY and not EMERGENT_KEY.startswith("sk-emergent-replace"):
    BACKEND = "emergent"
    chat_client = OpenAI(api_key=EMERGENT_KEY, base_url=EMERGENT_PROXY)
    audio_client = chat_client
    anthropic_client = None
elif ANTHROPIC_KEY and OPENAI_KEY and not ANTHROPIC_KEY.startswith("sk-ant-replace"):
    BACKEND = "direct"
    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)
    anthropic_client = Anthropic(api_key=ANTHROPIC_KEY)
    chat_client = None
    audio_client = OpenAI(api_key=OPENAI_KEY)
else:
    print("ERROR: configure .env with either EMERGENT_LLM_KEY, OR both ANTHROPIC_API_KEY + OPENAI_API_KEY.")
    sys.exit(1)

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
SAMPLE_RATE = 16000

def record_until_silence(max_seconds: float = 15.0, silence_seconds: float = 1.5,
                         silence_rms: float = 0.012) -> str:
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
    """Play mp3/wav bytes. Tries soundfile decode; falls back to default media player."""
    buf = io.BytesIO(data)
    try:
        audio, sr = sf.read(buf, dtype="float32")
        sd.play(audio, sr)
        sd.wait()
        return
    except Exception:
        pass
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        f.write(data)
        path = f.name
    if sys.platform == "win32":
        os.startfile(path)
    else:
        print(f"(audio saved to {path})")


# ---- Voice (Whisper STT + OpenAI TTS) ----------------------------------
def speech_to_text(wav_path: str) -> str:
    with open(wav_path, "rb") as f:
        r = audio_client.audio.transcriptions.create(model="whisper-1", file=f)
    return (r.text or "").strip()


def text_to_speech(text: str) -> bytes:
    r = audio_client.audio.speech.create(model="tts-1", voice=VOICE, input=text[:4000])
    return r.content


# ---- Tools --------------------------------------------------------------
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


def _openai_tools() -> list:
    return [
        {"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"]
        }} for t in ALL_TOOLS
    ]


# ---- Claude tool-use loop ----------------------------------------------
def think_and_act(user_text: str, history: list) -> str:
    history.append({"role": "user", "content": user_text})

    if BACKEND == "emergent":
        return _loop_openai_compatible(history)
    return _loop_anthropic_native(history)


def _loop_openai_compatible(history: list) -> str:
    msgs = [{"role": "system", "content": SYSTEM}] + history
    for _ in range(8):
        r = chat_client.chat.completions.create(
            model=MODEL,
            messages=msgs,
            tools=_openai_tools(),
            max_tokens=1024,
        )
        msg = r.choices[0].message
        assistant_entry = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        msgs.append(assistant_entry)

        if not msg.tool_calls:
            text = msg.content or ""
            history[:] = [m for m in msgs if m.get("role") != "system"]
            return text

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            print(f"  ↳ {tc.function.name}({json.dumps(args)})")
            out = run_tool(tc.function.name, args)
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": out})
    history[:] = [m for m in msgs if m.get("role") != "system"]
    return ""


def _loop_anthropic_native(history: list) -> str:
    msgs = list(history)
    for _ in range(8):
        r = anthropic_client.messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM,
            tools=ALL_TOOLS, messages=msgs,
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
        history[:] = msgs
        return text
    return ""


# ---- Main loop ----------------------------------------------------------
def main() -> None:
    print(BANNER)
    print(f"GHOST voice agent online · model: {MODEL} · voice: {VOICE}")
    print(f"Backend: {BACKEND}\n")
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
                user_text = speech_to_text(wav)
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
            reply = think_and_act(user_text, history)
        except Exception as e:
            log.exception("LLM error")
            print(f"⚠ {e}\n"); continue

        if reply:
            print(f"\nGHOST: {reply}\n")
            log.info("assistant: %s", reply)
            try:
                audio = text_to_speech(reply)
                play_audio_bytes(audio)
            except Exception as e:
                log.warning("TTS failed: %s", e)


if __name__ == "__main__":
    main()
