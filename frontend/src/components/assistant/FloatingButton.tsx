'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useAppStore } from '@/lib/store';

export default function FloatingButton() {
  const { assistantPanelState, setAssistantPanelState } = useAppStore();

  const isOpen = assistantPanelState === 'open' || assistantPanelState === 'minimized';

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <motion.button
          onClick={() => setAssistantPanelState(isOpen ? 'closed' : 'open')}
          className="group fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full shadow-lg transition-shadow duration-200 focus:outline-none lg:bottom-8 lg:right-8 lg:h-[60px] lg:w-[60px]"
          style={{
            background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
            boxShadow: isOpen
              ? '0 0 0 0 rgba(99, 102, 241, 0)'
              : '0 4px 24px -2px rgba(79, 70, 229, 0.45), 0 2px 8px -2px rgba(79, 70, 229, 0.3)',
          }}
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.94 }}
          aria-label="AI Compass Assistant"
        >
          {/* Pulse ring — only when closed */}
          <AnimatePresence>
            {!isOpen && (
              <motion.span
                className="absolute inset-0 rounded-full"
                style={{
                  background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                }}
                initial={{ opacity: 0.6, scale: 1 }}
                animate={{ opacity: 0, scale: 1.6 }}
                exit={{ opacity: 0 }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: 'easeOut',
                }}
              />
            )}
          </AnimatePresence>

          <Sparkles
            className="relative h-6 w-6 text-white lg:h-7 lg:w-7"
            strokeWidth={2}
          />

          {/* Hover glow */}
          <span className="absolute inset-0 rounded-full bg-white/0 transition-colors duration-200 group-hover:bg-white/10" />
        </motion.button>
      </TooltipTrigger>
      <TooltipContent
        side="left"
        className="rounded-lg border border-border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md"
        sideOffset={8}
      >
        Ask AI Compass
      </TooltipContent>
    </Tooltip>
  );
}