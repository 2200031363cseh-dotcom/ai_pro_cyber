import { Folder, Globe, Desktop, Brain, Clock, Calculator, Lightning, Files } from '@phosphor-icons/react';

const ICONS = {
  get_current_time: Clock,
  calculate: Calculator,
  web_search: Globe,
  remember_fact: Brain,
  recall_facts: Brain,
  open_app: Desktop,
  file_action: Files,
};

export default function SkillsPanel({ skills, enabled, onToggle }) {
  return (
    <div data-testid="skills-toggle-panel" className="ghost-panel p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-display text-[11px] tracking-[0.3em] text-cyan">/ SKILLS</h3>
        <span className="text-[10px] text-white/30 font-display tracking-widest">
          {enabled.size}/{skills.length}
        </span>
      </div>

      <div className="flex flex-col gap-1 ghost-scroll max-h-[260px] overflow-y-auto pr-1">
        {skills.map((s) => {
          const Icon = ICONS[s.name] || Lightning;
          const on = enabled.has(s.name);
          return (
            <button
              key={s.name}
              onClick={() => onToggle(s.name)}
              data-testid={`skill-toggle-${s.name}`}
              className={`text-left px-3 py-2 rounded-lg flex items-center gap-3 group transition border ${
                on
                  ? 'border-[#8BE9FD]/30 bg-[#8BE9FD]/[0.04]'
                  : 'border-transparent hover:border-white/5 hover:bg-white/[0.02]'
              }`}
            >
              <Icon
                size={16}
                weight="duotone"
                className={on ? 'text-cyan' : 'text-white/40 group-hover:text-white/70'}
              />
              <div className="flex-1 min-w-0">
                <div className={`text-[12px] font-mono ${on ? 'text-bone' : 'text-white/70'}`}>
                  {s.name}
                </div>
                <div className="text-[10px] text-white/35 leading-tight line-clamp-1 font-mono">
                  {s.description}
                </div>
              </div>
              <span
                className={`w-7 h-3.5 rounded-full p-0.5 transition flex ${
                  on ? 'bg-[#8BE9FD]/70 justify-end' : 'bg-white/10 justify-start'
                }`}
              >
                <span className={`w-2.5 h-2.5 rounded-full ${on ? 'bg-black' : 'bg-white/60'}`} />
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
