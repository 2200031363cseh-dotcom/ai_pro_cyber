"""GHOST backend API regression tests.

Covers: service info, skills listing, chat tool-use loop (time, calculate,
remember_fact + recall_facts cross-turn), conversation persistence + flatten,
memory CRUD, TTS, Windows agent zip download, and per-call tool filtering.
"""
from __future__ import annotations

import io
import os
import uuid
import zipfile
import base64
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://personal-ai-pilot.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Generous LLM timeout because Claude tool-loop can run multiple round-trips.
LLM_TIMEOUT = 120


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def shared_session_id():
    """Single session reused across chat tests so memory + history can be verified end-to-end."""
    return f"test-sess-{uuid.uuid4().hex[:10]}"


# ---------- Basic service ----------
def test_root_service_info(client):
    r = client.get(f"{API}/", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("service") == "ghost-api"
    assert data.get("model") == "claude-sonnet-4-5"
    assert data.get("status") == "online"


def test_skills_list(client):
    r = client.get(f"{API}/skills", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    names = {s["name"] for s in data.get("skills", [])}
    expected = {
        "get_current_time", "calculate", "web_search",
        "remember_fact", "recall_facts", "open_app", "file_action",
    }
    assert expected.issubset(names), f"Missing skills: {expected - names}"


# ---------- Memory pre-clean ----------
def test_clear_facts_before_chat(client):
    r = client.delete(f"{API}/memory/facts", timeout=30)
    assert r.status_code == 200
    assert r.json().get("cleared") == True


# ---------- Chat: simple greeting ----------
def test_chat_simple_greeting(client, shared_session_id):
    payload = {"session_id": shared_session_id, "message": "Hello GHOST, say hi back briefly."}
    r = client.post(f"{API}/chat", json=payload, timeout=LLM_TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"] == shared_session_id
    assert data["user_text"] == payload["message"]
    assert isinstance(data["assistant_text"], str) and len(data["assistant_text"]) > 0


# ---------- Chat: get_current_time tool ----------
def test_chat_invokes_get_current_time(client, shared_session_id):
    payload = {"session_id": shared_session_id, "message": "what time is it right now?"}
    r = client.post(f"{API}/chat", json=payload, timeout=LLM_TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    names = [tc["name"] for tc in data.get("tool_calls", [])]
    assert "get_current_time" in names, f"Expected get_current_time tool call, got {names}"


# ---------- Chat: calculate tool ----------
def test_chat_invokes_calculate(client, shared_session_id):
    payload = {"session_id": shared_session_id, "message": "what is 17 times 23? use the calculator."}
    r = client.post(f"{API}/chat", json=payload, timeout=LLM_TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    tcs = data.get("tool_calls", [])
    calc = [tc for tc in tcs if tc["name"] == "calculate"]
    assert calc, f"Expected calculate tool call, got {[tc['name'] for tc in tcs]}"
    # Tool result should yield 391 (string-encoded JSON)
    assert "391" in str(calc[0].get("result", "")), f"Result missing 391: {calc[0]}"
    # Assistant text should also mention 391
    assert "391" in data["assistant_text"]


# ---------- Chat: remember_fact ----------
def test_chat_remember_fact(client, shared_session_id):
    payload = {"session_id": shared_session_id, "message": "Please remember that I love astronomy."}
    r = client.post(f"{API}/chat", json=payload, timeout=LLM_TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    names = [tc["name"] for tc in data.get("tool_calls", [])]
    assert "remember_fact" in names, f"Expected remember_fact call, got {names}"

    # Verify fact persisted
    time.sleep(0.5)
    fr = client.get(f"{API}/memory/facts", timeout=30)
    assert fr.status_code == 200
    facts = fr.json().get("facts", [])
    assert any("astronom" in f.lower() for f in facts), f"Astronomy fact not stored: {facts}"


# ---------- Chat: recall fact (same session) ----------
def test_chat_recall_fact_same_session(client, shared_session_id):
    payload = {"session_id": shared_session_id, "message": "What do I love? Check your memory."}
    r = client.post(f"{API}/chat", json=payload, timeout=LLM_TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    # The model may call recall_facts OR just remember from session history; accept either,
    # but the assistant text MUST mention astronomy.
    assert "astronom" in data["assistant_text"].lower(), (
        f"Assistant did not recall astronomy. Text: {data['assistant_text']!r}, "
        f"tool_calls: {data.get('tool_calls')}"
    )


# ---------- Conversation persistence and flattening ----------
def test_get_conversation_flattened(client, shared_session_id):
    r = client.get(f"{API}/conversations/{shared_session_id}", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"] == shared_session_id
    msgs = data.get("messages", [])
    assert len(msgs) > 0, "Conversation should have flattened messages"
    user_msgs = [m for m in msgs if m["role"] == "user"]
    assert user_msgs, "No user messages in flattened history"
    # No empty user.text frames
    for m in user_msgs:
        assert m["text"].strip(), f"Empty user message frame found: {m}"


# ---------- Memory CRUD ----------
def test_add_fact_manual(client):
    payload = {"fact": "TEST_FACT_manual_pizza_lover"}
    r = client.post(f"{API}/memory/facts", json=payload, timeout=30)
    assert r.status_code == 200
    assert r.json().get("stored") == payload["fact"]

    g = client.get(f"{API}/memory/facts", timeout=30)
    assert g.status_code == 200
    assert payload["fact"] in g.json().get("facts", [])


def test_add_fact_empty_rejected(client):
    r = client.post(f"{API}/memory/facts", json={"fact": "   "}, timeout=30)
    assert r.status_code == 400


def test_clear_all_facts(client):
    r = client.delete(f"{API}/memory/facts", timeout=30)
    assert r.status_code == 200
    assert r.json().get("cleared") == True
    g = client.get(f"{API}/memory/facts", timeout=30)
    assert g.json().get("facts") == []


# ---------- Conversation delete ----------
def test_delete_conversation(client, shared_session_id):
    r = client.delete(f"{API}/conversations/{shared_session_id}", timeout=30)
    assert r.status_code == 200
    assert r.json().get("cleared") == True
    # Subsequent get should return empty
    g = client.get(f"{API}/conversations/{shared_session_id}", timeout=30)
    assert g.status_code == 200
    assert g.json().get("messages") == []


# ---------- TTS ----------
def test_chat_tts(client):
    r = client.post(f"{API}/chat/tts", json={"text": "hello there", "voice": "nova"}, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("audio_mime") == "audio/mpeg"
    audio_b64 = data.get("audio_base64", "")
    assert audio_b64, "Empty audio_base64"
    decoded = base64.b64decode(audio_b64)
    assert len(decoded) > 500, f"Audio bytes too small: {len(decoded)}"


def test_chat_tts_empty_text_rejected(client):
    r = client.post(f"{API}/chat/tts", json={"text": "  ", "voice": "nova"}, timeout=30)
    assert r.status_code == 400


# ---------- Windows agent zip ----------
def test_agent_download_zip(client):
    r = client.get(f"{API}/agent/download", timeout=60)
    assert r.status_code == 200
    ctype = r.headers.get("content-type", "")
    assert "application/zip" in ctype, f"Unexpected content-type: {ctype}"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    required = [
        "windows_agent/ghost.py",
        "windows_agent/skills/__init__.py",
        "windows_agent/requirements.txt",
    ]
    for required_path in required:
        assert required_path in names, f"Missing {required_path} in zip; got {names}"


# ---------- Per-call tool filtering ----------
def test_chat_enabled_tools_filter(client):
    """When only 'calculate' is enabled, Claude must still respond. We can't
    strictly assert that the model declines to use other tools, but at minimum
    the response must succeed and any tool_calls invoked must be 'calculate'.
    """
    sid = f"test-filter-{uuid.uuid4().hex[:8]}"
    payload = {
        "session_id": sid,
        "message": "Quickly: what is 2+2? Then tell me what time it is.",
        "enabled_tools": ["calculate"],
    }
    r = client.post(f"{API}/chat", json=payload, timeout=LLM_TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data["assistant_text"], str) and data["assistant_text"]
    for tc in data.get("tool_calls", []):
        assert tc["name"] == "calculate", f"Unexpected tool used while filtered: {tc['name']}"
    # cleanup
    client.delete(f"{API}/conversations/{sid}", timeout=30)
