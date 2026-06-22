import { useEffect, useRef, useState } from 'react';
import { Microphone, MicrophoneSlash, PaperPlaneRight, Stop } from '@phosphor-icons/react';
import { motion } from 'framer-motion';

export default function ChatInput({ onSend, onVoice, disabled }) {
  const [value, setValue] = useState('');
  const [recording, setRecording] = useState(false);
  const mediaRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);

  const submit = () => {
    const v = value.trim();
    if (!v || disabled) return;
    onSend(v);
    setValue('');
  };

  const startRec = async () => {
    if (disabled) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach(t => t.stop());
        if (blob.size > 800) await onVoice(blob);
      };
      mr.start();
      mediaRef.current = mr;
      setRecording(true);
    } catch (e) {
      alert('Microphone access denied or unavailable.');
    }
  };

  const stopRec = () => {
    if (mediaRef.current && mediaRef.current.state !== 'inactive') {
      mediaRef.current.stop();
    }
    setRecording(false);
  };

  useEffect(() => () => streamRef.current?.getTracks().forEach(t => t.stop()), []);

  return (
    <div className="px-6 md:px-10 py-4 border-t border-white/5">
      <div className="flex items-end gap-3">
        <div className="flex-1 ghost-panel !rounded-2xl px-4 py-3 flex items-center gap-2">
          <span className="text-cyan font-display text-sm select-none">{'>'}</span>
          <textarea
            data-testid="chat-input-textarea"
            value={value}
            disabled={disabled}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
            }}
            placeholder={recording ? 'listening…' : 'speak, or type a command — shift+enter for newline'}
            rows={1}
            className="flex-1 bg-transparent outline-none text-bone text-[13.5px] font-mono resize-none placeholder:text-white/25 max-h-32"
          />
          <span className="kbd hidden md:inline">↵</span>
        </div>

        <motion.button
          whileTap={{ scale: 0.92 }}
          onClick={recording ? stopRec : startRec}
          disabled={disabled}
          data-testid="mic-toggle-btn"
          className={`w-12 h-12 rounded-2xl flex items-center justify-center border transition ${
            recording
              ? 'border-[#8BE9FD]/60 bg-[#8BE9FD]/10 glow-cyan'
              : 'border-white/10 bg-white/[0.03] hover:border-white/20'
          }`}
          title={recording ? 'Stop & send' : 'Hold to talk'}
        >
          {recording
            ? <Stop size={18} weight="fill" className="text-cyan" />
            : <Microphone size={18} weight="duotone" className="text-bone" />}
        </motion.button>

        <motion.button
          whileTap={{ scale: 0.92 }}
          onClick={submit}
          disabled={disabled || !value.trim()}
          data-testid="send-message-btn"
          className="w-12 h-12 rounded-2xl flex items-center justify-center border border-[#8BE9FD]/40 bg-[#8BE9FD]/10 hover:bg-[#8BE9FD]/15 transition disabled:opacity-30 disabled:cursor-not-allowed glow-soft"
        >
          <PaperPlaneRight size={18} weight="fill" className="text-cyan" />
        </motion.button>
      </div>
      <p className="text-[10px] mt-2 text-white/30 font-display tracking-widest">
        AUDIO IS STREAMED TO WHISPER · TEXT TO CLAUDE · NEVER STORED RAW
      </p>
    </div>
  );
}
