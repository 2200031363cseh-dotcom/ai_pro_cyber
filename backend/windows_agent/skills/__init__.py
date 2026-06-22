"""Skill registry for the Windows GHOST agent.

Each skill is just a Python function plus a `TOOL` schema describing it to
Claude. To add a new skill: write a function, add a TOOL dict, register both.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import subprocess
import sys
from pathlib import Path

# ---- safety helpers ----

def confirm(prompt: str) -> bool:
    """Ask the user [y/N] in the terminal. Used inside risky skills."""
    ans = ""
    try:
        ans = input(f"[CONFIRM] {prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in {"y", "yes"}


# ---- skills ----

def get_current_time() -> dict:
    now = _dt.datetime.now().astimezone()
    return {"local": now.isoformat(), "tz": str(now.tzinfo)}


def _evaluate_math_ast(expression: str):
    """Evaluate a math expression via AST whitelist. No Python eval/exec is used."""
    import ast, operator as op
    ops = {
        ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
        ast.Mod: op.mod, ast.Pow: op.pow, ast.FloorDiv: op.floordiv,
        ast.USub: op.neg, ast.UAdd: op.pos,
    }
    funcs = {k: getattr(math, k) for k in dir(math) if not k.startswith("_") and callable(getattr(math, k))}
    consts = {k: getattr(math, k) for k in ("pi", "e", "tau", "inf", "nan") if hasattr(math, k)}
    funcs.update({"abs": abs, "round": round, "min": min, "max": max})

    def _walk(node):
        if isinstance(node, ast.Expression):
            return _walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](_walk(node.left), _walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](_walk(node.operand))
        if isinstance(node, ast.Name):
            if node.id in consts:
                return consts[node.id]
            raise ValueError(f"unknown name: {node.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = funcs.get(node.func.id)
            if not fn:
                raise ValueError(f"unknown function: {node.func.id}")
            return fn(*[_walk(a) for a in node.args])
        raise ValueError(f"disallowed expression element: {type(node).__name__}")

    # ast.parse(mode='eval') selects grammar; it does NOT execute code.
    return _walk(ast.parse(expression, mode="eval"))


def calculate(expression: str) -> dict:
    try:
        return {"result": _evaluate_math_ast(expression)}
    except Exception as e:
        return {"error": str(e)}


def open_app(app_name: str) -> dict:
    """Open an app via Windows Start-Process (cross-platform fallback to subprocess)."""
    if sys.platform == "win32":
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process '{app_name}'"])
            return {"status": "launched", "app": app_name}
        except Exception as e:
            return {"error": str(e)}
    # non-Windows fallback (for dev/testing)
    try:
        subprocess.Popen([app_name])
        return {"status": "launched", "app": app_name, "note": "non-Windows fallback"}
    except FileNotFoundError:
        return {"error": f"app not found: {app_name}"}


def search_files(query: str, root: str | None = None, limit: int = 25) -> dict:
    base = Path(root or Path.home())
    if not base.exists():
        return {"error": f"root not found: {base}"}
    matches = []
    for p in base.rglob(f"*{query}*"):
        matches.append(str(p))
        if len(matches) >= limit:
            break
    return {"query": query, "root": str(base), "matches": matches}


def file_action(action: str, path: str, destination: str | None = None) -> dict:
    src = Path(path).expanduser()
    if action == "list":
        if not src.exists():
            return {"error": "not found"}
        return {"items": [str(p) for p in (src.iterdir() if src.is_dir() else [src])]}
    if action == "move":
        if not destination:
            return {"error": "destination required"}
        if not confirm(f"Move {src} -> {destination}?"):
            return {"status": "cancelled"}
        os.makedirs(Path(destination).parent, exist_ok=True)
        src.replace(destination)
        return {"status": "moved", "from": str(src), "to": destination}
    if action == "copy":
        import shutil
        if not destination:
            return {"error": "destination required"}
        shutil.copy2(src, destination)
        return {"status": "copied", "from": str(src), "to": destination}
    if action == "delete":
        if not confirm(f"DELETE {src}? this cannot be undone"):
            return {"status": "cancelled"}
        if src.is_dir():
            import shutil
            shutil.rmtree(src)
        else:
            src.unlink()
        return {"status": "deleted", "path": str(src)}
    return {"error": f"unknown action {action}"}


def screenshot(save_path: str | None = None) -> dict:
    try:
        import pyautogui
    except ImportError:
        return {"error": "pyautogui not installed"}
    target = Path(save_path or Path.home() / "Pictures" / f"ghost_{_dt.datetime.now():%Y%m%d_%H%M%S}.png")
    target.parent.mkdir(parents=True, exist_ok=True)
    pyautogui.screenshot(str(target))
    return {"saved": str(target)}


def run_powershell(command: str) -> dict:
    """Execute a PowerShell command. Confirmation always required."""
    if not confirm(f"Run PowerShell:\n  {command}\n"):
        return {"status": "cancelled"}
    if sys.platform != "win32":
        return {"error": "PowerShell only on Windows"}
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=30,
        )
        return {
            "stdout": out.stdout[-4000:],
            "stderr": out.stderr[-2000:],
            "returncode": out.returncode,
        }
    except Exception as e:
        return {"error": str(e)}


# ---- schemas ----

ALL_TOOLS = [
    {
        "name": "get_current_time",
        "description": "Get the current local time on this PC.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "calculate",
        "description": "Evaluate a math expression (supports math.* functions).",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
    {
        "name": "open_app",
        "description": "Open an application by name (e.g. 'notepad', 'chrome', 'Spotify').",
        "input_schema": {
            "type": "object",
            "properties": {"app_name": {"type": "string"}},
            "required": ["app_name"],
        },
    },
    {
        "name": "search_files",
        "description": "Find files matching a substring under a root folder (default: home).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "root": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "file_action",
        "description": "Move, copy, delete, or list files. Destructive actions are confirmed in the terminal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["move", "copy", "delete", "list"]},
                "path": {"type": "string"},
                "destination": {"type": "string"},
            },
            "required": ["action", "path"],
        },
    },
    {
        "name": "screenshot",
        "description": "Capture a screenshot and save it. Returns the saved path.",
        "input_schema": {
            "type": "object",
            "properties": {"save_path": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "run_powershell",
        "description": "Run a PowerShell command (always confirmed). Use for system queries Claude can't do otherwise.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
]

DISPATCH = {
    "get_current_time": get_current_time,
    "calculate": calculate,
    "open_app": open_app,
    "search_files": search_files,
    "file_action": file_action,
    "screenshot": screenshot,
    "run_powershell": run_powershell,
}
