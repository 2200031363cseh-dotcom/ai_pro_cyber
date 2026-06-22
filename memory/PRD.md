# GHOST — Personal AI Assistant · PRD

## Original problem statement
Build a Personal AI Assistant for Windows in 5 phases (voice + conversational brain → file/app automation → screen control → memory → safety). The user asked for:
- **Both** a web app **and** a downloadable Windows Python starter.
- Best Claude model as default (we ship `claude-sonnet-4-5`).
- Hacker-ghost / haunted-terminal aesthetic, "user friendly".
- Voice in/out (we chose Whisper STT + OpenAI TTS via Emergent LLM key).

The user provided their own Anthropic API key but the key had a **zero credit balance** at the time of build. We fell back to the **Emergent Universal LLM key** for Claude (still routed to Anthropic) so the app works out of the box. Their personal key remains in `.env` for when they top it up.

## Architecture (mental model from the brief)
| Part | Web app | Windows agent |
|---|---|---|
| Ears | `MediaRecorder` → `/api/chat/voice` → Whisper | (extendable) |
| Brain | Claude Sonnet 4.5 via `emergentintegrations.LlmChat` with `with_tools` loop | Anthropic SDK with tool use loop |
| Mouth | OpenAI TTS (mp3, voices: nova/alloy/shimmer/echo/fable/onyx/sage/coral/ash) | (extendable) |
| Hands | 7 sandboxed/simulated skills | Real PC: open_app, file_action, screenshot, run_powershell |
| Eyes | — | `computer_use.py` (opt-in, sandboxed VM only) |
| Memory | MongoDB collections `conversations` + `memory_facts` | (local extension point) |

## User personas
- **Solo operator** who wants a voice-first Claude companion they can carry across browser sessions, with hooks to drive their own Windows machine when ready.

## Core requirements (static)
1. Web chat (text + push-to-talk mic) with Claude tool-use loop.
2. 7 skills out of the box: `get_current_time`, `calculate`, `web_search` (DuckDuckGo), `remember_fact`, `recall_facts`, `open_app` (simulated on web), `file_action` (simulated on web).
3. Persistent memory across sessions (Mongo).
4. Downloadable Windows agent zip with the same skill names + real implementations + computer-use Phase 3 opt-in.
5. Confirm-before-destructive on the Windows agent.
6. Logs of every action in `ghost.log` on the Windows side.
7. Hacker-ghost theme: phosphor cyan + bone-white on near-black, JetBrains Mono + Space Mono, glass panels, scanline grain.

## What's been implemented (2026-01-22)
- **Backend** (`/app/backend/server.py`, `skills.py`):
  - `GET /api/` health
  - `GET /api/skills`
  - `POST /api/chat` (text → tool loop → text)
  - `POST /api/chat/voice` (audio → Whisper → tool loop → TTS mp3)
  - `POST /api/chat/tts` (text → mp3 base64)
  - `GET/POST/DELETE /api/memory/facts`
  - `GET/DELETE /api/conversations/{id}`
  - `GET /api/agent/download` (streams the zipped Windows starter)
- **Frontend** (React 19 + Tailwind + Framer Motion + Phosphor icons):
  - Three-column layout: SkillsPanel + MemoryPanel (left) · ChatStream + VoiceVisualizer + ChatInput (center) · SettingsPanel + DownloadCard + Session info (right).
  - Push-to-talk mic, live status HUD (idle / listening / thinking / speaking) with pulse rings, rotating dashed ring, wave bars, blinking cursor.
  - Tool calls render inline as terminal-style tags inside the assistant message.
- **Windows desktop agent** (`/app/backend/windows_agent/`):
  - `voice_ghost.py` — full voice loop: mic in (sounddevice + silence VAD) → Whisper → Claude tool loop → OpenAI TTS → speaker out.
  - `ghost.py` — text-only fallback.
  - `skills/__init__.py` — real `open_app`, `search_files`, `file_action` (move/copy/delete confirmed), `screenshot`, `run_powershell` (confirmed).
  - `computer_use.py` — Phase 3 screen control (opt-in, sandboxed VM only).
  - One-click installers: `setup.bat`, `run_voice.bat`, `run_text.bat`.
  - Dual auth: EMERGENT_LLM_KEY OR (ANTHROPIC_API_KEY + OPENAI_API_KEY).
- **Tests**: 17/17 backend pytest cases passing (iteration_1).

## Prioritized backlog
- **P1**
  - Streaming Claude responses (SSE) so long replies don't appear all at once.
  - Wake-word ("Hey GHOST") via Porcupine in the browser.
- **P2**
  - Phase 4 vector memory (Chroma) for semantic recall once facts grow.
  - Per-session sandboxed skills (e.g., browse-allowlist for `web_search`).
  - Cost/usage meter in the Session panel.
- **P3**
  - Windows agent installer / .msi packaging.
  - Computer-use docker sandbox preset.

## Next tasks (after user review)
1. Verify the user can download the Windows agent zip and run `python ghost.py` on their PC.
2. Top up the user's own Anthropic key (so we can flip back from Emergent key with one env edit) — *optional*.
3. Add SSE streaming if the user wants snappier perceived latency.
