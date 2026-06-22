"""GHOST web-runtime skills.

These run on the web server (sandboxed). They are SAFE simulations of what the
Windows agent (downloadable) would do on the user's actual machine.
"""
from __future__ import annotations
from datetime import datetime, timezone
import math
import urllib.parse
import urllib.request
import json
import re


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_current_time(timezone_name: str | None = None) -> dict:
    return {
        "utc": _now_iso(),
        "requested_timezone": timezone_name or "UTC",
        "note": "Server clock is UTC. Local PC time available via the Windows agent.",
    }


def calculate(expression: str) -> dict:
    allowed = re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s\,a-zA-Z_]+", expression or "")
    if not allowed:
        return {"error": "Expression contains disallowed characters."}
    safe_env = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    safe_env.update({"abs": abs, "round": round, "min": min, "max": max})
    try:
        value = eval(expression, {"__builtins__": {}}, safe_env)
        return {"expression": expression, "result": value}
    except Exception as e:
        return {"error": f"Could not evaluate: {e}"}


def web_search(query: str, max_results: int = 5) -> dict:
    """Lightweight web search using DuckDuckGo Instant Answer (no key required)."""
    try:
        url = "https://duckduckgo.com/?" + urllib.parse.urlencode(
            {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        )
        req = urllib.request.Request(url, headers={"User-Agent": "GhostAI/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        results = []
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
            })
        for topic in (data.get("RelatedTopics") or [])[: max_results - len(results)]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                })
        return {"query": query, "results": results[:max_results]}
    except Exception as e:
        return {"query": query, "results": [], "error": str(e)}


def simulate_open_app(app_name: str) -> dict:
    return {
        "status": "simulated",
        "message": (
            f"On the web, GHOST cannot launch '{app_name}'. The downloadable "
            f"Windows agent will execute this via PowerShell/Start-Process."
        ),
        "agent_command_preview": f"Start-Process '{app_name}'",
    }


def simulate_file_action(action: str, path: str, destination: str | None = None) -> dict:
    return {
        "status": "simulated",
        "action": action,
        "path": path,
        "destination": destination,
        "message": "File action staged. Confirm + run from the Windows agent to execute.",
    }


# --- Tool definitions for Claude ---
TOOL_DEFINITIONS = [
    {
        "name": "get_current_time",
        "description": "Get the current server time in UTC. Use whenever the user asks about the current time, date, or 'now'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timezone_name": {"type": "string", "description": "Optional IANA tz like 'America/New_York'."}
            },
            "required": [],
        },
    },
    {
        "name": "calculate",
        "description": "Evaluate a math expression. Supports +,-,*,/,parens, and math functions (sin, cos, sqrt, log, pi, e).",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web (DuckDuckGo) for a topic and return a short list of result snippets with URLs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "remember_fact",
        "description": "Store a small fact about the user for future recall (preferences, name, recurring info).",
        "input_schema": {
            "type": "object",
            "properties": {"fact": {"type": "string"}},
            "required": ["fact"],
        },
    },
    {
        "name": "recall_facts",
        "description": "Retrieve previously stored facts about the user. Use when relevant to answer.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "open_app",
        "description": "Open an application on the user's PC. NOTE: in the web sandbox this is simulated. The downloadable Windows agent executes it for real.",
        "input_schema": {
            "type": "object",
            "properties": {"app_name": {"type": "string", "description": "e.g. 'notepad', 'chrome', 'Spotify'"}},
            "required": ["app_name"],
        },
    },
    {
        "name": "file_action",
        "description": "Perform a file operation. Simulated on web; real on Windows agent. Actions: 'move','copy','delete','list','search'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["move", "copy", "delete", "list", "search"]},
                "path": {"type": "string"},
                "destination": {"type": "string"},
            },
            "required": ["action", "path"],
        },
    },
]


def execute_tool(name: str, tool_input: dict, *, memory_store) -> str:
    """Dispatch a Claude tool_use call. memory_store is an async-compatible dict-like object."""
    try:
        if name == "get_current_time":
            return json.dumps(get_current_time(tool_input.get("timezone_name")))
        if name == "calculate":
            return json.dumps(calculate(tool_input.get("expression", "")))
        if name == "web_search":
            return json.dumps(web_search(
                tool_input.get("query", ""),
                int(tool_input.get("max_results", 5)),
            ))
        if name == "remember_fact":
            fact = (tool_input.get("fact") or "").strip()
            if not fact:
                return json.dumps({"error": "empty fact"})
            memory_store.append(fact)
            return json.dumps({"stored": fact, "total_facts": len(memory_store)})
        if name == "recall_facts":
            return json.dumps({"facts": list(memory_store)})
        if name == "open_app":
            return json.dumps(simulate_open_app(tool_input.get("app_name", "")))
        if name == "file_action":
            return json.dumps(simulate_file_action(
                tool_input.get("action", ""),
                tool_input.get("path", ""),
                tool_input.get("destination"),
            ))
        return json.dumps({"error": f"unknown tool {name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})
