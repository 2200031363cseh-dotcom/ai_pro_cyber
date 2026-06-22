"""GHOST — text-only local Windows agent (no private deps).

Routes Claude through either:
  • EMERGENT_LLM_KEY (free, OpenAI-compatible proxy), OR
  • ANTHROPIC_API_KEY (your own).

Run with `python ghost.py`. Logs to ghost.log.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

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

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
EMERGENT_PROXY = "https://integrations.emergentagent.com/llm"

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

if EMERGENT_KEY and not EMERGENT_KEY.startswith("sk-emergent-replace"):
    BACKEND = "emergent"
    from openai import OpenAI
    chat_client = OpenAI(api_key=EMERGENT_KEY, base_url=EMERGENT_PROXY)
    anthropic_client = None
elif ANTHROPIC_KEY and not ANTHROPIC_KEY.startswith("sk-ant-replace"):
    BACKEND = "direct"
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=ANTHROPIC_KEY)
    chat_client = None
else:
    print("ERROR: set EMERGENT_LLM_KEY or ANTHROPIC_API_KEY in .env")
    sys.exit(1)

SYSTEM = (
    "You are GHOST, a personal AI assistant running on the user's Windows PC. "
    "You have real hands: open apps, manipulate files, take screenshots, run "
    "guarded PowerShell. State your plan in one sentence before calling a tool. "
    "Confirm before irreversible actions. Be concise."
)

BANNER = r"""
   ▄████  ██░ ██  ▒█████    ██████ ▄▄▄█████▓
  ██▒ ▀█▒▓██░ ██▒▒██▒  ██▒▒██    ▒ ▓  ██▒ ▓▒
 ▒██░▄▄▄░▒██▀▀██░▒██░  ██▒░ ▓██▄   ▒ ▓██░ ▒░
"""


def _openai_tools() -> list:
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"], "parameters": t["input_schema"]
    }} for t in ALL_TOOLS]


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


def _hop_openai(history: list) -> str:
    msgs = [{"role": "system", "content": SYSTEM}] + history
    for _ in range(10):
        r = chat_client.chat.completions.create(
            model=MODEL, messages=msgs, tools=_openai_tools(), max_tokens=1024,
        )
        msg = r.choices[0].message
        entry = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        msgs.append(entry)
        if not msg.tool_calls:
            history[:] = [m for m in msgs if m["role"] != "system"]
            return msg.content or ""
        for tc in msg.tool_calls:
            try: args = json.loads(tc.function.arguments or "{}")
            except Exception: args = {}
            print(f"  ↳ {tc.function.name}({json.dumps(args)})")
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": run_tool(tc.function.name, args)})
    return ""


def _hop_anthropic(history: list) -> str:
    msgs = list(history)
    for _ in range(10):
        r = anthropic_client.messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM, tools=ALL_TOOLS, messages=msgs,
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
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": run_tool(b.name, b.input or {})})
            msgs.append({"role": "user", "content": results})
            continue
        history[:] = msgs
        return "\n".join(b.text for b in r.content if b.type == "text").strip()
    return ""


def main() -> None:
    print(BANNER)
    print(f"GHOST online. Model: {MODEL} · Backend: {BACKEND}")
    print("Type 'exit' to quit.\n")
    history: list = []
    while True:
        try:
            user = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye."); return
        if not user: continue
        if user.lower() in {"exit", "quit", ":q"}: return
        history.append({"role": "user", "content": user})
        log.info("user: %s", user)
        try:
            reply = _hop_openai(history) if BACKEND == "emergent" else _hop_anthropic(history)
        except Exception as e:
            log.exception("LLM error")
            print(f"⚠ {e}\n"); continue
        if reply:
            print(f"\nGHOST: {reply}\n")
            log.info("assistant: %s", reply)


if __name__ == "__main__":
    main()
