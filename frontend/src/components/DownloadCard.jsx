import { DownloadSimple, ShieldCheck, Cpu } from '@phosphor-icons/react';
import { motion } from 'framer-motion';

export default function DownloadCard({ apiBase }) {
  return (
    <div
      data-testid="download-agent-card"
      className="ghost-panel relative overflow-hidden p-0 download-bg"
      style={{ borderRadius: 20 }}
    >
      <div className="relative p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Cpu size={16} weight="duotone" className="text-cyan" />
          <span className="font-display text-[11px] tracking-[0.3em] text-cyan">
            / WINDOWS AGENT
          </span>
        </div>

        <h3 className="font-display text-lg leading-tight text-bone">
          Give GHOST real hands.
        </h3>
        <p className="text-[11.5px] text-white/65 leading-relaxed font-mono">
          A small Python starter for your PC. Opens apps, manages files, takes screenshots,
          and runs guarded PowerShell — all through Claude tool use. Confirmations are baked in.
        </p>

        <div className="flex items-center gap-2 text-[10px] text-white/45 font-display tracking-widest">
          <ShieldCheck size={12} weight="duotone" className="text-cyan" />
          SANDBOXED · CONFIRMS DESTRUCTIVE OPS · LOGS EVERYTHING
        </div>

        <motion.a
          whileHover={{ y: -2 }}
          whileTap={{ scale: 0.97 }}
          data-testid="download-agent-btn"
          href={`${apiBase}/agent/download`}
          className="mt-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-[#8BE9FD]/40 bg-[#8BE9FD]/10 hover:bg-[#8BE9FD]/20 transition text-cyan font-display text-xs tracking-[0.25em] glow-soft"
        >
          <DownloadSimple size={14} weight="bold" />
          DOWNLOAD AGENT.ZIP
        </motion.a>

        <p className="text-[10px] text-white/30 font-mono leading-relaxed">
          unzip · <span className="text-white/50">cd ghost-windows-agent</span> · pip install -r requirements.txt · python ghost.py
        </p>
      </div>
    </div>
  );
}
