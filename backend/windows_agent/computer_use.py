"""GHOST Phase 3 — Computer Use (BETA, sandboxed VM only).

This is a separate opt-in entry point that uses Anthropic's `computer-use` tool
to let Claude see your screen and click/type. Do NOT run this on your main
Windows session; spin up a sandbox VM first.

Quickstart:
    pip install anthropic pyautogui Pillow
    python computer_use.py "open notepad and write hello"

Required envs (in .env):
    ANTHROPIC_API_KEY=...
    CLAUDE_MODEL=claude-sonnet-4-5   # or current computer-use-capable model
"""
from __future__ import annotations
import base64
import io
import os
import sys
import time
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

try:
    import pyautogui
    from PIL import Image
except ImportError:
    print("Install pyautogui + Pillow first.")
    sys.exit(1)

load_dotenv(Path(__file__).with_name(".env"))
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")

SCREEN_W, SCREEN_H = pyautogui.size()

TOOLS = [{
    "type": "computer_20250124",
    "name": "computer",
    "display_width_px": SCREEN_W,
    "display_height_px": SCREEN_H,
    "display_number": 1,
}]


def take_screenshot_b64() -> str:
    buf = io.BytesIO()
    pyautogui.screenshot().save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def execute_action(action: str, **kwargs) -> str:
    if action == "screenshot":
        return "screenshot taken"
    if action == "mouse_move":
        x, y = kwargs["coordinate"]
        pyautogui.moveTo(x, y, duration=0.2)
        return "moved"
    if action == "left_click":
        if "coordinate" in kwargs:
            x, y = kwargs["coordinate"]
            pyautogui.click(x, y)
        else:
            pyautogui.click()
        return "clicked"
    if action == "type":
        pyautogui.typewrite(kwargs.get("text", ""), interval=0.02)
        return "typed"
    if action == "key":
        pyautogui.press(kwargs.get("text", ""))
        return "key pressed"
    if action == "scroll":
        pyautogui.scroll(kwargs.get("amount", -3))
        return "scrolled"
    return f"unknown action: {action}"


def run(task: str) -> None:
    messages = [{
        "role": "user",
        "content": [{"type": "text", "text": task}],
    }]
    for hop in range(20):
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
            betas=["computer-use-2025-01-24"],
        )
        # echo any assistant text
        for b in resp.content:
            if getattr(b, "type", None) == "text":
                print(f"GHOST: {b.text}")
        messages.append({"role": "assistant", "content": [
            (b.model_dump() if hasattr(b, "model_dump") else b) for b in resp.content
        ]})
        if resp.stop_reason != "tool_use":
            return
        results = []
        for b in resp.content:
            if getattr(b, "type", None) == "tool_use" and b.name == "computer":
                act = b.input.get("action")
                input("press ENTER to allow next action: ")
                summary = execute_action(act, **{k: v for k, v in b.input.items() if k != "action"})
                time.sleep(0.4)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": [
                        {"type": "text", "text": summary},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": take_screenshot_b64()}},
                    ],
                })
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python computer_use.py <task>")
        sys.exit(1)
    run(" ".join(sys.argv[1:]))
