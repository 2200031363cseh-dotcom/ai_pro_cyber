import { useState } from 'react';
import { Brain, Trash, Plus } from '@phosphor-icons/react';

export default function MemoryPanel({ facts, onAdd, onClear }) {
  const [val, setVal] = useState('');

  const submit = () => {
    const v = val.trim();
    if (!v) return;
    onAdd(v);
    setVal('');
  };

  return (
    <div data-testid="memory-facts-panel" className="ghost-panel p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-display text-[11px] tracking-[0.3em] text-cyan flex items-center gap-2">
          <Brain size={14} weight="duotone" /> MEMORY
        </h3>
        {facts.length > 0 && (
          <button
            data-testid="memory-clear-btn"
            onClick={onClear}
            className="text-[10px] text-white/40 hover:text-rose-300 transition flex items-center gap-1 font-display tracking-widest"
          >
            <Trash size={11} /> WIPE
          </button>
        )}
      </div>

      <div className="flex flex-col gap-1.5 max-h-44 overflow-y-auto ghost-scroll pr-1">
        {facts.length === 0 && (
          <p className="text-[11px] text-white/30 italic font-mono">
            no memories yet. tell GHOST about you.
          </p>
        )}
        {facts.map((f, i) => (
          <div
            key={i}
            className="text-[11px] text-white/65 font-mono leading-relaxed px-2 py-1.5 rounded bg-white/[0.02] border border-white/5"
          >
            <span className="text-cyan mr-1">·</span>{f}
          </div>
        ))}
      </div>

      <div className="flex gap-1.5">
        <input
          data-testid="memory-fact-input"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder="add a fact…"
          className="flex-1 bg-white/[0.02] border border-white/5 rounded-md px-2 py-1.5 text-[11px] font-mono text-bone outline-none focus:border-[#8BE9FD]/40"
        />
        <button
          data-testid="memory-add-btn"
          onClick={submit}
          className="px-2 rounded-md bg-[#8BE9FD]/10 border border-[#8BE9FD]/30 hover:bg-[#8BE9FD]/20 transition"
        >
          <Plus size={12} weight="bold" className="text-cyan" />
        </button>
      </div>
    </div>
  );
}
