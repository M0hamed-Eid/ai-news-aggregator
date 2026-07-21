'use client';

import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import { useAppStore } from '@/lib/store';

const SUGGESTION_CHIPS = [
  'Explain this article',
  "Summarize today's AI news",
  'What happened this week?',
  'Compare GPT-5 vs Claude',
  'What did the speaker say about MCP?',
  'Latest OpenAI news',
];

interface WelcomeStateProps {
  onSuggestionClick: (text: string) => void;
}

export default function WelcomeState({ onSuggestionClick }: WelcomeStateProps) {
  const { assistantContext } = useAppStore();
  const isGlobal = assistantContext.type === 'global';

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-8">
      {/* AI Avatar */}
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10"
      >
        <Sparkles className="h-7 w-7 text-primary" />
      </motion.div>

      {/* Headline */}
      <motion.h2
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="mb-2 text-lg font-semibold tracking-tight text-ink"
      >
        How can I help you today?
      </motion.h2>

      {/* Subtitle */}
      <motion.p
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.15 }}
        className="mb-6 max-w-xs text-center text-sm leading-relaxed text-ink-muted"
      >
        {isGlobal
          ? 'I can answer questions about articles, videos, AI models, today\'s news, weekly summaries, and technical explanations.'
          : 'Ask me anything about this content. I can summarize, explain, compare, or find related information.'}
      </motion.p>

      {/* Suggestion Chips */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.2 }}
        className="flex max-w-full flex-wrap justify-center gap-2"
      >
        {SUGGESTION_CHIPS.map((chip, i) => (
          <motion.button
            key={chip}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: 0.25 + i * 0.04 }}
            onClick={() => onSuggestionClick(chip)}
            className="rounded-full border border-border bg-card px-3.5 py-1.5 text-[13px] text-ink transition-all duration-150 hover:border-primary/30 hover:bg-primary/5 hover:text-primary hover:shadow-sm"
          >
            {chip}
          </motion.button>
        ))}
      </motion.div>
    </div>
  );
}