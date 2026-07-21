'use client';

import { motion } from 'framer-motion';

interface FollowUpSuggestionsProps {
  suggestions: string[];
  onClick: (text: string) => void;
}

export default function FollowUpSuggestions({ suggestions, onClick }: FollowUpSuggestionsProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: 0.1 }}
      className="flex flex-wrap gap-1.5 pl-1"
    >
      {suggestions.map((s, i) => (
        <motion.button
          key={s}
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.15, delay: 0.15 + i * 0.04 }}
          onClick={() => onClick(s)}
          className="rounded-full border border-border bg-card px-3 py-1 text-[12px] text-ink-muted transition-all duration-150 hover:border-primary/30 hover:bg-primary/5 hover:text-primary hover:shadow-sm"
        >
          {s}
        </motion.button>
      ))}
    </motion.div>
  );
}