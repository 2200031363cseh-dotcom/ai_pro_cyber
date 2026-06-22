import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import { Ghost } from '@phosphor-icons/react';

import VoiceVisualizer from '@/components/VoiceVisualizer';
import ChatStream from '@/components/ChatStream';
import ChatInput from '@/components/ChatInput';
import SkillsPanel from '@/components/SkillsPanel';
import MemoryPanel from '@/components/MemoryPanel';
import DownloadCard from '@/components/DownloadCard';
import SettingsPanel from '@/components/SettingsPanel';

import '@/App.css';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function loadSessionId() {
  const k = 'ghost.session_id';
  let id = localStorage.getItem(k);
  if (!id) {
    id = 'gh_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(k, id);
  }
  return id;
}

export default function App() {
  const [sessionId, setSessionId] = useState(loadSessionId);
  const [skills, setSkills] = useState([]);
  const [enabledSkills, setEnabledSkills] = useState(new Set());
  const [facts, setFacts] = useState([]);
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState('idle'); // idle | listening | thinking | speaking
  const [voice, setVoice] = useState('nova');
  const [speakReplies, setSpeakReplies] = useState(true);
  const audioRef = useRef(null);

  const enabledList = useMemo(() => Array.from(enabledSkills), [enabledSkills]);

  // ---- initial load ----
  useEffect(() => {
    (async () => {
      try {
        const s = await axios.get(`${API}/skills`);
        const list = s.data.skills || [];
        setSkills(list);
        setEnabledSkills(new Set(list.map((x) => x.name)));
      } catch (e) { /* ignore */ }
      await refreshFacts();
      await loadHistory(sessionId);
    })();
  }, []);

  const refreshFacts = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/memory/facts`);
      setFacts(r.data.facts || []);
    } catch (e) { /* ignore */ }
  }, []);

  const loadHistory = useCallback(async (sid) => {
    try {
      const r = await axios.get(`${API}/conversations/${sid}`);
      // Merge consecutive assistant tool-call frames with the next text frame.
      const raw = r.data.messages || [];
      const merged = [];
      let pendingCalls = [];
      for (const m of raw) {
        if (m.role === 'assistant' && (m.tool_calls?.length || 0) > 0 && !m.text) {
          pendingCalls.push(...(m.tool_calls || []));
          continue;
        }
        if (m.role === 'assistant') {
          merged.push({ role: 'assistant', text: m.text, tool_calls: [...pendingCalls, ...(m.tool_calls || [])] });
          pendingCalls = [];
          continue;
        }
        if (m.role === 'user' && m.text) {
          merged.push({ role: 'user', text: m.text });
        }
      }
      setMessages(merged);
    } catch (e) { setMessages([]); }
  }, []);

  // ---- handlers ----
  const playAudio = useCallback(async (b64, mime = 'audio/mpeg') => {
    if (!b64) return;
    setStatus('speaking');
    try {
      audioRef.current?.pause();
      const audio = new Audio(`data:${mime};base64,${b64}`);
      audioRef.current = audio;
      audio.onended = () => setStatus('idle');
      await audio.play();
    } catch (e) { setStatus('idle'); }
  }, []);

  const sendText = useCallback(async (text) => {
    setMessages((prev) => [...prev, { role: 'user', text }]);
    setStatus('thinking');
    try {
      const r = await axios.post(`${API}/chat`, {
        session_id: sessionId,
        message: text,
        enabled_tools: enabledList,
      });
      const { assistant_text, tool_calls } = r.data;
      setMessages((prev) => [...prev, { role: 'assistant', text: assistant_text, tool_calls }]);
      await refreshFacts();
      if (speakReplies && assistant_text) {
        const tts = await axios.post(`${API}/chat/tts`, { text: assistant_text, voice });
        await playAudio(tts.data.audio_base64, tts.data.audio_mime);
      } else {
        setStatus('idle');
      }
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message;
      setMessages((prev) => [...prev, { role: 'assistant', text: `⚠ ${msg}`, tool_calls: [] }]);
      setStatus('idle');
    }
  }, [sessionId, enabledList, speakReplies, voice, refreshFacts, playAudio]);

  const sendVoice = useCallback(async (blob) => {
    setStatus('thinking');
    const fd = new FormData();
    fd.append('audio', blob, 'recording.webm');
    fd.append('session_id', sessionId);
    fd.append('voice', voice);
    if (enabledList.length) fd.append('enabled_tools', enabledList.join(','));
    try {
      const r = await axios.post(`${API}/chat/voice`, fd);
      const { user_text, assistant_text, tool_calls, audio_base64, audio_mime } = r.data;
      setMessages((prev) => [
        ...prev,
        { role: 'user', text: user_text },
        { role: 'assistant', text: assistant_text, tool_calls },
      ]);
      await refreshFacts();
      if (speakReplies) {
        await playAudio(audio_base64, audio_mime);
      } else {
        setStatus('idle');
      }
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message;
      setMessages((prev) => [...prev, { role: 'assistant', text: `⚠ ${msg}`, tool_calls: [] }]);
      setStatus('idle');
    }
  }, [sessionId, voice, enabledList, speakReplies, refreshFacts, playAudio]);

  const toggleSkill = (name) => {
    setEnabledSkills((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  const addFact = async (fact) => {
    await axios.post(`${API}/memory/facts`, { fact });
    refreshFacts();
  };
  const clearFacts = async () => {
    await axios.delete(`${API}/memory/facts`);
    refreshFacts();
  };

  const newSession = async () => {
    audioRef.current?.pause();
    const id = 'gh_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem('ghost.session_id', id);
    setSessionId(id);
    setMessages([]);
    setStatus('idle');
  };

  // when the audio is talking, listening state pre-empts thinking visually
  const visualStatus = status;

  return (
    <div className="h-screen w-full overflow-hidden flex flex-col md:flex-row bg-[#050508] text-bone p-3 md:p-5 gap-4 relative z-10">
      {/* LEFT SIDEBAR */}
      <motion.aside
        initial={{ opacity: 0, x: -16 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full md:w-72 lg:w-80 flex-shrink-0 flex flex-col gap-4 md:overflow-y-auto ghost-scroll"
      >
        <div className="ghost-panel p-5 flex items-center gap-3" data-testid="ghost-logo-block">
          <div className="relative w-10 h-10 rounded-xl bg-[#8BE9FD]/10 border border-[#8BE9FD]/30 flex items-center justify-center glow-soft">
            <Ghost size={22} weight="duotone" className="text-cyan" />
          </div>
          <div className="flex flex-col leading-none">
            <span className="font-display text-2xl tracking-tighter text-bone">GHOST</span>
            <span className="font-display text-[10px] tracking-[0.3em] text-white/40 mt-1">
              PERSONAL · AI · ASSISTANT
            </span>
          </div>
        </div>

        <SkillsPanel
          skills={skills}
          enabled={enabledSkills}
          onToggle={toggleSkill}
        />

        <MemoryPanel facts={facts} onAdd={addFact} onClear={clearFacts} />
      </motion.aside>

      {/* MAIN CHAT */}
      <motion.main
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.1 }}
        className="flex-1 flex flex-col min-w-0 ghost-panel relative overflow-hidden"
      >
        <VoiceVisualizer status={visualStatus} />
        <ChatStream messages={messages} isThinking={status === 'thinking'} />
        <ChatInput onSend={sendText} onVoice={sendVoice} disabled={status === 'thinking'} />
      </motion.main>

      {/* RIGHT PANEL */}
      <motion.aside
        initial={{ opacity: 0, x: 16 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, delay: 0.2 }}
        className="w-full md:w-80 lg:w-96 flex-shrink-0 flex flex-col gap-4 md:overflow-y-auto ghost-scroll"
      >
        <SettingsPanel
          voice={voice}
          setVoice={setVoice}
          speakReplies={speakReplies}
          setSpeakReplies={setSpeakReplies}
          onNewSession={newSession}
        />
        <DownloadCard apiBase={API} />

        <div className="ghost-panel p-5" data-testid="session-info-panel">
          <h3 className="font-display text-[11px] tracking-[0.3em] text-cyan mb-2">/ SESSION</h3>
          <p className="text-[10.5px] text-white/40 font-mono break-all leading-relaxed">
            {sessionId}
          </p>
          <p className="text-[10px] text-white/30 font-display tracking-widest mt-3">
            CLAUDE SONNET 4.5 · WHISPER · OPENAI TTS
          </p>
        </div>
      </motion.aside>
    </div>
  );
}
