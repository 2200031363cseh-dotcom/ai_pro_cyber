"""GHOST — local Windows agent. Run with `python ghost.py`.

Conversational loop: read stdin -> Claude (with tool use) -> execute tool ->
feed result back -> print final answer. Everything is logged to ghost.log.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from skills import ALL_TOOLS, DISPATCH, confirm

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    filename=ROOT / "ghost.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("ghost")

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY or API_KEY.startswith("sk-ant-replace"):
    print("ERROR: set ANTHROPIC_API_KEY in .env")
    sys.exit(1)

client = Anthropic(api_key=API_KEY)

SYSTEM = (
    "You are GHOST, a personal AI assistant running on the user's Windows PC. "
    "You have real hands: you can open applications, manipulate files, take "
    "screenshots, and run guarded PowerShell. "
    "ALWAYS state your plan in one sentence before calling a tool. "
    "ALWAYS confirm before irreversible actions (delete, overwrite, send). "
    "Be concise. The user is at a terminal."
)

BANNER = r"""
   ▄████  ██░ ██  ▒█████    ██████ ▄▄▄█████▓
  ██▒ ▀█▒▓██░ ██▒▒██▒  ██▒▒██    ▒ ▓  ██▒ ▓▒
 ▒██░▄▄▄░▒██▀▀██░▒██░  ██▒░ ▓██▄   ▒ ▓██░ ▒░
 ░▓█  ██▓░▓█ ░██ ▒██   ██░  ▒   ██▒░ ▓██▓ ░ 
 ░▒▓███▀▒░▓█▒░██▓░ ████▓▒░▒██████▒▒  ▒██▒ ░ 
"""


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


def chat_loop() -> None:
    print(BANNER)
    print(f"GHOST online. Model: {MODEL}\nType 'exit' to quit.\n")
    messages: list[dict] = []
    while True:
        try:
            user = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return
        if not user:
            continue
        if user.lower() in {"exit", "quit", ":q"}:
            return
        messages.append({"role": "user", "content": user})
        log.info("user: %s", user)

        for _ in range(10):
            resp = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM,
                tools=ALL_TOOLS,
                messages=messages,
            )
            blocks = []
            for b in resp.content:
                if b.type == "text":
                    blocks.append({"type": "text", "text": b.text})
                elif b.type == "tool_use":
                    blocks.append({
                        "type": "tool_use",
                        "id": b.id,
                        "name": b.name,
                        "input": b.input,
                    })
            messages.append({"role": "assistant", "content": blocks})

            if resp.stop_reason == "tool_use":
                results = []
                for b in resp.content:
                    if b.type == "tool_use":
                        print(f"  ↳ {b.name}({json.dumps(b.input)})")
                        out = run_tool(b.name, b.input or {})
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": b.id,
                            "content": out,
                        })
                messages.append({"role": "user", "content": results})
                continue

            text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
            if text:
                print(f"\nGHOST: {text}\n")
                log.info("assistant: %s", text)
            break


if __name__ == "__main__":
    chat_loop()
