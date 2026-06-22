import { SpeakerHigh, SpeakerSlash, Gear, ArrowsClockwise } from '@phosphor-icons/react';

const VOICES = ['nova', 'alloy', 'shimmer', 'echo', 'fable', 'onyx', 'sage', 'coral', 'ash'];

export default function SettingsPanel({
  voice,
  setVoice,
  speakReplies,
  setSpeakReplies,
  onNewSession,
}) {
  return (
    <div data-testid="settings-configuration-panel" className="ghost-panel p-5 flex flex-col gap-3">
      <h3 className="font-display text-[11px] tracking-[0.3em] text-cyan flex items-center gap-2">
        <Gear size={14} weight="duotone" /> SETTINGS
      </h3>

      <div className="flex items-center justify-between">
        <span className="text-[11px] text-white/65 font-mono">Speak replies</span>
        <button
          data-testid="speak-replies-toggle"
          onClick={() => setSpeakReplies(!speakReplies)}
          className={`w-9 h-4 rounded-full p-0.5 flex transition ${
            speakReplies ? 'bg-[#8BE9FD]/70 justify-end' : 'bg-white/10 justify-start'
          }`}
        >
          <span className={`w-3 h-3 rounded-full ${speakReplies ? 'bg-black' : 'bg-white/60'}`} />
        </button>
      </div>

      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-white/65 font-mono flex items-center gap-1.5">
          {speakReplies ? <SpeakerHigh size={12} /> : <SpeakerSlash size={12} />}
          Voice
        </span>
        <select
          data-testid="voice-select"
          value={voice}
          onChange={(e) => setVoice(e.target.value)}
          className="bg-white/[0.03] border border-white/10 rounded-md px-2 py-1 text-[11px] font-mono text-bone outline-none focus:border-[#8BE9FD]/40"
        >
          {VOICES.map((v) => (
            <option key={v} value={v} className="bg-[#0B0C10]">{v}</option>
          ))}
        </select>
      </div>

      <button
        data-testid="new-session-btn"
        onClick={onNewSession}
        className="mt-1 px-3 py-2 text-[11px] font-display tracking-widest border border-white/10 rounded-lg hover:border-white/30 text-white/70 hover:text-bone transition flex items-center justify-center gap-2"
      >
        <ArrowsClockwise size={12} /> NEW SESSION
      </button>
    </div>
  );
}
