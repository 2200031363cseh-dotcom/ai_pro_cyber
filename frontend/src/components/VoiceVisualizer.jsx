import { motion } from 'framer-motion';

/**
 * GHOST status HUD.
 * status: 'idle' | 'listening' | 'thinking' | 'speaking'
 */
export default function VoiceVisualizer({ status = 'idle' }) {
  const label = {
    idle: 'ONLINE',
    listening: 'LISTENING',
    thinking: 'THINKING',
    speaking: 'SPEAKING',
  }[status];

  const color = {
    idle: '#44475A',
    listening: '#8BE9FD',
    thinking: '#B388FF',
    speaking: '#8BE9FD',
  }[status];

  return (
    <div
      data-testid="voice-visualizer-hud"
      className="flex items-center gap-4 px-5 py-3 border-b border-white/5"
    >
      <div className="relative w-9 h-9 flex items-center justify-center">
        {status === 'listening' && (
          <>
            <span className="ghost-pulse-ring" />
            <span className="ghost-pulse-ring" style={{ animationDelay: '0.5s' }} />
          </>
        )}
        {status === 'thinking' && (
          <div className="ghost-rotate absolute inset-0 rounded-full border border-dashed" style={{ borderColor: color }} />
        )}
        <motion.div
          animate={{ scale: status === 'idle' ? [1, 1.05, 1] : 1 }}
          transition={{ repeat: Infinity, duration: 2.2 }}
          className="w-3 h-3 rounded-full"
          style={{ background: color, boxShadow: `0 0 14px ${color}` }}
        />
      </div>

      <div className="flex flex-col leading-tight">
        <span className="text-[10px] tracking-[0.3em] text-white/40 font-display">G H O S T</span>
        <span className="text-xs tracking-[0.25em] font-display" style={{ color }} data-testid="ghost-status-label">
          {label}
        </span>
      </div>

      {status === 'speaking' && (
        <div className="flex items-end gap-1 h-6 ml-2" data-testid="speaking-wave">
          {[0, 1, 2, 3, 4, 5, 6].map((i) => (
            <span
              key={i}
              className="w-[3px] rounded-sm wave-bar"
              style={{ height: '100%', background: '#8BE9FD', animationDelay: `${i * 0.08}s` }}
            />
          ))}
        </div>
      )}

      <div className="ml-auto flex items-center gap-2 text-[10px] tracking-[0.25em] text-white/30 font-display">
        <span className="ghost-blink" style={{ color }}>●</span>
        <span>v0.1 · CLAUDE</span>
      </div>
    </div>
  );
}
