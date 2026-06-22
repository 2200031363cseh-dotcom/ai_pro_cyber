# GHOST — Windows Agent (Local PC Control)

This is the **downloadable companion** to the GHOST web app. It runs on **your**
Windows machine and gives Claude real "hands" to:

* open applications (`open_app`)
* search / move / copy / delete files (`file_action`)
* take screenshots (`screenshot`)
* run guarded PowerShell commands (`run_powershell`)
* tell the time, do math, search the web, etc. (same shared skills as the web app)

It is intentionally a **starter kit** — small, readable, and easy to extend with
your own skills.

---

## ⚠️ Read this first (safety)

* Run GHOST under a **non-admin Windows user account** — not your daily-driver
  admin login. This contains the blast radius if something goes wrong.
* Anything irreversible (delete, send, spend) is gated behind a `[y/N]`
  confirmation in the terminal. **Do not remove these prompts.**
* Every action GHOST takes is appended to `ghost.log` next to the script.
* Computer-use / vision-driven control (Phase 3 in the brief) is **opt-in** and
  off by default.

---

## 1. Install

Requires **Python 3.11+** and Windows 10/11.

```powershell
git clone <or unzip this folder>
cd ghost-windows-agent
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure

Copy `.env.example` to `.env` and fill in your Anthropic key:

```env
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-5
```

## 3. Run

```powershell
python ghost.py
```

You'll see:

```
   ▄████  ██░ ██  ▒█████    ██████ ▄▄▄█████▓
  ██▒ ▀█▒▓██░ ██▒▒██▒  ██▒▒██    ▒ ▓  ██▒ ▓▒
 ▒██░▄▄▄░▒██▀▀██░▒██░  ██▒░ ▓██▄   ▒ ▓██░ ▒░
GHOST online. Model: claude-sonnet-4-5
> _
```

Type naturally. Examples:

* `what time is it?`
* `open notepad`
* `find all PDFs in Downloads`
* `move every screenshot from Desktop into Pictures\Screenshots`
* `take a screenshot`

## 4. Add your own skills

Skills are plain Python functions registered in `skills/__init__.py`. Each one
has a **schema** that Claude reads to decide when to call it. To add a new one:

1. Write a function in `skills/my_skill.py`.
2. Add a `TOOL` dict describing it.
3. Import it in `skills/__init__.py` and append it to `ALL_TOOLS` + `DISPATCH`.

That's it. Claude will discover and call it automatically.

## Phase 3 (computer use / screen control)

Computer-use is included as a separate opt-in script (`computer_use.py`) and
should only be run inside a sandboxed VM. See comments in that file.

---

Built with ❤ by GHOST.
