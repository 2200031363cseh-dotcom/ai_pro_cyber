# GHOST · Windows Desktop Agent (with AI Voice)

The companion to the GHOST web app — runs on **your** Windows PC and lets Claude
**actually drive your machine** with real voice in / voice out.

Capabilities:
- 🎙 **Voice in**: push-to-talk (type `v`), auto-stops on silence, transcribed by Whisper
- 🔊 **Voice out**: replies are spoken back via OpenAI TTS (9 voices)
- 🧠 **Brain**: Claude Sonnet 4.5 with tool-use loop
- ✋ **Hands**: `open_app`, `search_files`, `file_action` (move/copy/delete — confirmed),
  `screenshot`, `run_powershell` (confirmed), `calculate`, `get_current_time`
- 👁 **Eyes** (opt-in, Phase 3): `computer_use.py` — see + click + type in any app

---

## ⚠️ Read this first (safety)

* Run GHOST under a **non-admin Windows user account** — not your daily-driver
  admin login. Contains the blast radius if something goes wrong.
* Anything irreversible (delete, send, spend) is gated behind a `[y/N]` prompt
  in the terminal. **Do not remove these prompts.**
* Every action is logged to `ghost.log` next to the script.
* The `computer_use.py` (screen-control) script is **off by default**. Only run
  it inside a sandboxed VM.

---

## ⚡ 60-second setup (the easy path)

1. **Install Python 3.11+** from [python.org](https://python.org). On the
   installer, **tick "Add Python to PATH"**.

2. **Unzip** this folder anywhere (e.g. `C:\Users\You\ghost-windows-agent\`).

3. **Double-click `setup.bat`**. It will:
   * create a `.venv` virtualenv
   * install all deps (Anthropic, OpenAI, sounddevice, etc.)
   * copy `.env.example` → `.env` and open Notepad so you can paste your keys

4. **Edit `.env`** (Notepad opens automatically). Pick ONE of these:

   **Option A — easy mode (use the Emergent key, no signup):**
   ```
   EMERGENT_LLM_KEY=sk-emergent-dF8F9B681A4AfE5069
   ```
   (this single key covers Claude + Whisper + TTS)

   **Option B — your own keys (more control, you pay direct):**
   ```
   ANTHROPIC_API_KEY=sk-ant-...  (from console.anthropic.com)
   OPENAI_API_KEY=sk-...         (from platform.openai.com — for Whisper + TTS)
   ```
   Set a **spending limit in the Anthropic console immediately** — pay-per-token
   means a bug in a loop could spend real money.

5. Save Notepad, close it, then **double-click `run_voice.bat`** to start the
   voice agent. (Or `run_text.bat` for keyboard-only mode.)

---

## Using GHOST

When you see the `>` prompt:

| You type | What happens |
|---|---|
| `v` then Enter | Mic opens. Speak. It auto-stops ~1.5 s after you go silent. Whisper transcribes, Claude responds, the reply is spoken back. |
| anything else | Sent as text to Claude (no voice). |
| `exit` | Quit. |

Examples to try:
* `v` → "what time is it?"
* `v` → "open notepad"
* `v` → "find all PDFs in my Downloads folder"
* `v` → "take a screenshot"
* "move all .png files from Desktop into Pictures\Screenshots"

Anything destructive (delete, overwrite, `run_powershell`) pauses for a `[y/N]`
confirmation — keep the terminal visible.

---

## Voice customisation

Edit `.env`:
```
TTS_VOICE=nova   # nova | alloy | shimmer | echo | fable | onyx | sage | coral | ash
```

---

## Add your own skills

Skills are plain Python functions in `skills/__init__.py`. Each one has a
schema Claude reads to decide when to call it.

1. Write `def my_skill(arg1: str) -> dict:` in `skills/__init__.py`.
2. Add a `TOOL` dict describing it (name, description, input_schema).
3. Add it to `ALL_TOOLS` and `DISPATCH`.

Claude picks it up automatically on next run.

---

## Phase 3 — Computer Use (screen control, BETA)

`computer_use.py` lets Claude see your screen and click around. Only run it
inside a **sandboxed VM** — see comments in that file.

```powershell
python computer_use.py "open notepad and write hello world"
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Python is not installed or not in PATH` | Re-run the Python installer and tick "Add to PATH". |
| Microphone records nothing | Windows Settings → Privacy → Microphone → allow apps. Check `python -c "import sounddevice; print(sounddevice.query_devices())"` shows an input device. |
| `credit balance is too low` | Your `ANTHROPIC_API_KEY` is out of credit. Top up at console.anthropic.com, OR switch to `EMERGENT_LLM_KEY` in `.env`. |
| Audio plays through wrong speaker | Windows sound settings → set default output. |
| Wants admin password | Don't give it. Run from a non-admin account. |

---

Built with ❤ by GHOST. Logs at `ghost.log`. PRs welcome.
