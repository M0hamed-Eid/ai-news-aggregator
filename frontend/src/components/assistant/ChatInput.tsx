'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { Send, CornerDownLeft } from 'lucide-react';
import { useAppStore } from '@/lib/store';
import type { AssistantContextType } from '@/lib/types';

const PLACEHOLDERS: Record<AssistantContextType['type'], string> = {
  article: 'Ask about this article...',
  video: 'Ask about this video...',
  topic: 'Ask about this topic...',
  search: 'Ask about your search...',
  global: 'Ask AI Compass anything...',
};

interface ChatInputProps {
  onSubmit: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSubmit, disabled = false }: ChatInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { assistantContext } = useAppStore();

  const placeholder = PLACEHOLDERS[assistantContext.type];

  // Auto-grow textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  }, [value]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue('');
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, disabled, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return (
    <div className="border-t border-border bg-surface p-3">
      <div className="relative flex items-end gap-2 rounded-xl border border-border bg-background px-3 py-2 shadow-sm transition-colors focus-within:border-primary/40 focus-within:shadow-[0_0_0_3px_rgba(79,70,229,0.08)]">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="max-h-[160px] min-h-[24px] flex-1 resize-none bg-transparent text-sm text-ink placeholder:text-ink-muted/50 focus:outline-none disabled:opacity-50"
        />
        <div className="flex shrink-0 items-center gap-1">
          {/* Shift+Enter hint */}
          {value && (
            <span className="hidden items-center gap-0.5 text-[10px] text-ink-muted/40 sm:flex">
              <CornerDownLeft className="h-2.5 w-2.5" />
              Shift+Enter
            </span>
          )}
          <button
            onClick={handleSubmit}
            disabled={!value.trim() || disabled}
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-all duration-150 hover:bg-primary/90 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
      <p className="mt-1.5 text-center text-[10px] text-ink-muted/40">
        AI Compass may produce inaccurate information. Verify important facts.
      </p>
    </div>
  );
}