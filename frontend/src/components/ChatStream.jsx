import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, Lightning, Ghost } from '@phosphor-icons/react';

function ToolTag({ name, input, result }) {
  let parsed = result;
  try { parsed = typeof result === 'string' ? JSON.parse(result) : result; } catch { /* ignore */ }
  const preview = typeof parsed === 'object' ? JSON.stringify(parsed).slice(0, 140) : String(parsed || '').slice(0, 140);
  return (
    <div className="my-2" data-testid={`tool-call-${name}`}>
      <span className="tool-tag">
        <Lightning size={12} weight="fill" />
        <span>{name}({input ? Object.keys(input).slice(0, 2).join(',') : ''})</span>
      </span>
      {result && (
        <pre className="mt-1 text-[10.5px] leading-relaxed text-white/45 font-mono whitespace-pre-wrap break-words pl-2 border-l border-white/5 ml-2">
          ↳ {preview}
        </pre>
      )}
    </div>
  );
}

export default function ChatStream({ messages, isThinking }) {
  const isEmpty = !messages || messages.length === 0;

  return (
    <div
      data-testid="chat-transcript-stream"
      className="flex-1 overflow-y-auto ghost-scroll px-6 md:px-10 py-6 flex flex-col gap-4"
    >
      {isEmpty && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="m-auto text-center max-w-md"
        >
          <Ghost size={60} weight="duotone" className="mx-auto mb-5 text-cyan opacity-80" />
          <h2 className="font-display text-3xl tracking-tight text-bone mb-2">
            <span className="text-cyan">/</span> hello, operator.
          </h2>
          <p className="text-sm text-white/50 leading-relaxed">
            Speak or type. I run reasoning, lookups, math, and lightweight automations.
            Toggle skills on the left. Grab the Windows agent on the right for real PC control.
          </p>
          <div className="mt-6 flex gap-2 justify-center flex-wrap">
            {['what time is it?', 'search the web for nano banana', '12.5% of 480?'].map((s) => (
              <span key={s} className="text-[11px] text-white/40 border border-white/5 rounded-full px-3 py-1 font-mono">
                {s}
              </span>
            ))}
          </div>
        </motion.div>
      )}

      <AnimatePresence initial={false}>
        {messages.map((m, idx) => (
          <motion.div
            key={`m-${idx}`}
            layout
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className={m.role === 'user' ? 'flex justify-end' : 'flex'}
            data-testid={`msg-${m.role}-${idx}`}
          >
            {m.role === 'user' ? (
              <div className="max-w-[80%] bg-white/5 border border-white/5 rounded-2xl rounded-br-sm px-4 py-3 text-[13.5px] text-bone leading-relaxed font-mono">
                {m.text}
              </div>
            ) : (
              <div className="max-w-[90%] pl-4 border-l-2 border-[#8BE9FD]/40 text-[13.5px] text-white/90 leading-relaxed font-mono whitespace-pre-wrap">
                {m.tool_calls && m.tool_calls.length > 0 && (
                  <div className="mb-1">
                    {m.tool_calls.map((tc, i) => (
                      <ToolTag key={i} name={tc.name} input={tc.input} result={tc.result} />
                    ))}
                  </div>
                )}
                {m.text}
              </div>
            )}
          </motion.div>
        ))}
      </AnimatePresence>

      {isThinking && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 text-xs text-lavender font-display tracking-widest pl-4 border-l-2 border-lavender/30"
          data-testid="thinking-indicator"
        >
          <Terminal size={14} />
          <span>GHOST is thinking</span>
          <span className="flex gap-1">
            <span className="w-1 h-1 rounded-full bg-lavender ghost-blink" />
            <span className="w-1 h-1 rounded-full bg-lavender ghost-blink" style={{ animationDelay: '0.2s' }} />
            <span className="w-1 h-1 rounded-full bg-lavender ghost-blink" style={{ animationDelay: '0.4s' }} />
          </span>
        </motion.div>
      )}
    </div>
  );
}
