# GHOST · Windows Desktop Agent (with AI Voice)

The companion to the GHOST web app — runs on **your** Windows PC and lets Claude
**actually drive your machine** with real voice in / voice out.

> If you can copy-paste, you can run this. Follow the steps in order. Each step
> is one or two commands.

---

## What you'll get

* 🎙 **Voice in** — type `v`, speak, it auto-stops on silence (Whisper STT)
* 🔊 **Voice out** — replies are spoken back (OpenAI TTS, 9 voices)
* 🧠 **Brain** — Claude Sonnet 4.5 with tool-use loop
* ✋ **Hands** — open apps, search/move/copy/delete files (confirmed),
  take screenshots, run guarded PowerShell, calculate, get the time
* 👁 **Eyes** (opt-in) — `computer_use.py` lets Claude see + click + type in any
  app. Sandbox VM only.

---

## STEP 1 · Install Python 3.11+

1. Go to **https://www.python.org/downloads/**
2. Download the latest Windows installer.
3. Run it. **TICK THE "Add python.exe to PATH" CHECKBOX** at the bottom of the
   first installer screen. *(This is the single most missed step.)*
4. Click **Install Now**. Wait ~1 min.

**Verify it worked.** Open a new **PowerShell** window (Win + X → "Windows
PowerShell") and run:

```powershell
python --version
```

Expected output: `Python 3.11.x` (or higher). If you get *"python is not
recognised"*, re-run the installer and tick "Add to PATH".

---

## STEP 2 · Get the agent

1. On the GHOST web app, click the **DOWNLOAD AGENT.ZIP** button (right panel).
2. Save it somewhere simple, e.g. your **Desktop**.
3. **Right-click the zip → Extract All…** → choose a folder, e.g.
   `C:\Users\YOU\Desktop\ghost-windows-agent\`. Click **Extract**.

You should now see a folder containing `setup.bat`, `voice_ghost.py`,
`ghost.py`, `run_voice.bat`, etc.

---

## STEP 3 · One-click install

**Just double-click `setup.bat`** inside the extracted folder.

It will automatically:

1. Create a Python virtualenv inside `.venv\`
2. Install all dependencies (anthropic, openai, sounddevice, pyautogui, …)
3. Copy `.env.example` → `.env`
4. Open `.env` in Notepad for you to review

> Installation takes ~2 minutes the first time. Leave the PowerShell window
> open until you see "IMPORTANT: open .env and replace placeholder keys".

### Manual alternative (if `setup.bat` won't run)

If your PC blocks .bat files, open PowerShell **in the agent folder** (Shift +
right-click in the folder → "Open PowerShell window here") and run these one at
a time:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
notepad .env
```

> If PowerShell complains about *"running scripts is disabled"*, run this once:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`,
> answer **Y**, then re-run the activate line.

---

## STEP 4 · Configure your `.env`

Notepad opens automatically with this file. **You have two options — pick ONE:**

### Option A · Easy mode (Emergent key — already filled in)

Leave the file exactly as it is. The `EMERGENT_LLM_KEY` is already set and
covers Claude + Whisper + TTS in one key. Save and close Notepad. **Done.**

### Option B · Your own keys

Comment out the Emergent line by putting a `#` in front, then fill in your own:

```env
# EMERGENT_LLM_KEY=sk-emergent-...
ANTHROPIC_API_KEY=sk-ant-YOUR-KEY-FROM-console.anthropic.com
OPENAI_API_KEY=sk-YOUR-KEY-FROM-platform.openai.com
```

* Anthropic key → https://console.anthropic.com (Billing → set a spending
  cap immediately).
* OpenAI key → https://platform.openai.com (needs ≥$5 credit for Whisper+TTS).

Save and close Notepad.

---

## STEP 5 · Start GHOST (voice mode)

Inside the agent folder, **double-click `run_voice.bat`**.

You should see the GHOST banner and:

```
GHOST voice agent online · model: claude-sonnet-4-5 · voice: nova
Backend: Emergent LLM key

Type your message, or `v` to speak. `exit` to quit.

>
```

### Talk to it

At the `>` prompt:

| You type | What happens |
|---|---|
| `v` then Enter | Mic opens. **Speak.** It auto-stops ~1.5s after silence. Whisper transcribes → Claude responds → reply is spoken back. |
| Any other text | Sent as a text message to Claude (no voice in). Reply is still spoken. |
| `exit` | Quit. |

### Try these first

```
v   →  "what time is it?"
v   →  "open notepad"
v   →  "take a screenshot"
v   →  "find all PDFs in my Downloads folder"
v   →  "calculate 1248 divided by 32"
```

Anything destructive (delete file, run PowerShell) **pauses for `[y/N]`** in
the same window — keep the terminal visible.

---

## STEP 6 · Text-only mode (no mic)

Double-click `run_text.bat` instead. Same skills, keyboard only.

---

## Change the voice

Edit `.env`:

```env
TTS_VOICE=nova
```

Options: `nova | alloy | shimmer | echo | fable | onyx | sage | coral | ash`.
Save and restart `run_voice.bat`.

---

## Add your own skills (advanced)

Skills live in `skills/__init__.py`. Each is a Python function + a `TOOL` dict
that Claude reads to decide when to call it.

1. Write a function: `def my_skill(arg1: str) -> dict: ...`
2. Append a schema to `ALL_TOOLS`.
3. Append the function to `DISPATCH`.

Restart and Claude will discover it.

---

## Phase 3 · Computer Use (screen control, BETA — sandbox only)

`computer_use.py` lets Claude see your screen and click around. **Do not run
this on your real Windows session** — only inside a sandboxed VM.

```powershell
.\.venv\Scripts\Activate.ps1
python computer_use.py "open notepad and write hello world"
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python : not recognised` | Re-run the Python installer with **"Add to PATH"** ticked. |
| `setup.bat` window opens then closes instantly | Open PowerShell first, `cd` to the folder, run `setup.bat`. The error will stay visible. |
| `running scripts is disabled` (PowerShell) | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer **Y**. |
| Mic records nothing | Windows Settings → Privacy & Security → **Microphone** → allow apps. Then test with: `python -c "import sounddevice; print(sounddevice.query_devices())"` — you should see your mic. |
| `credit balance is too low` | Your `ANTHROPIC_API_KEY` is empty. Either top up at console.anthropic.com, or switch back to `EMERGENT_LLM_KEY` in `.env`. |
| Audio plays through wrong speaker | Windows sound settings → set default output device. |
| `ModuleNotFoundError: sounddevice` | The venv wasn't activated. Re-run `setup.bat`, or manually `.\.venv\Scripts\Activate.ps1` before `python voice_ghost.py`. |
| It asks for admin password | Don't give it. Run the whole thing from a non-admin Windows account. |

---

## Safety (do not skip)

* Run under a **non-admin Windows user account** — not your daily-driver admin
  login. Contains the blast radius if Claude misreads something.
* Destructive ops (`delete`, `run_powershell`) **always** prompt for `[y/N]`.
  Do not remove these prompts.
* Every action is logged to `ghost.log` next to the script — review it if
  anything looks off.
* `computer_use.py` is **off by default**. Only run it inside a sandboxed VM.
* Never give it access to saved passwords or sensitive accounts without a
  confirmation step in front.

---

## Quick command cheat sheet

```powershell
# first time only
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
notepad .env       # edit if you want your own keys

# every time
.\.venv\Scripts\Activate.ps1
python voice_ghost.py     # voice + text mode
# OR
python ghost.py           # text-only mode
```

Or just double-click `run_voice.bat` / `run_text.bat` after the first setup.

---

Built with ❤ by GHOST. Logs at `ghost.log` next to the script. Enjoy.
