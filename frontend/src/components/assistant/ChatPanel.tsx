'use client';

import { useCallback, useRef, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Minus, Plus, Square, AlertCircle, WifiOff, MessageSquareOff, Sparkles } from 'lucide-react';
import { useAppStore } from '@/lib/store';
import { parseContentRef } from '@/lib/api';
import {
  streamAssistantMessage, sendAssistantMessage, buildRequestScope, StreamUnavailableError,
  type AssistantAnswer, type AssistantRequestPayload,
} from '@/lib/assistant-stream';
import type { ChatMessage, SourceReference } from '@/lib/types';
import WelcomeState from './WelcomeState';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';
import ChatInput from './ChatInput';
import ContextIndicator from './ContextIndicator';

function formatCitationTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function citationsToSources(citations: AssistantAnswer['citations']): SourceReference[] {
  return citations.map((c) => ({
    id: c.marker,
    title: c.title,
    source: c.source || c.content_type,
    sourceType: c.content_type === 'youtube_video' ? 'video' : 'article',
    url: c.url,
    time: c.start_seconds != null ? formatCitationTime(c.start_seconds) : undefined,
  }));
}

// ============================================================
// Panel animation variants
// ============================================================
const PANEL_VARIANTS = {
  closed: { x: '100%', opacity: 0 },
  open: { x: 0, opacity: 1 },
  minimized: { x: '100%', opacity: 0 },
};

const BACKDROP_VARIANTS = {
  closed: { opacity: 0 },
  open: { opacity: 1 },
  minimized: { opacity: 0 },
};

export default function ChatPanel() {
  const {
    assistantPanelState,
    setAssistantPanelState,
    assistantContext,
    assistantConversations,
    assistantActiveConversationId,
    assistantIsTyping,
    assistantError,
    startNewAssistantConversation,
    addAssistantMessage,
    updateAssistantMessage,
    setConversationBackendId,
    setAssistantTyping,
    setAssistantError,
  } = useAppStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const isOpen = assistantPanelState === 'open';
  const isMinimized = assistantPanelState === 'minimized';

  // Current conversation
  const activeConversation = useMemo(
    () => assistantConversations.find((c) => c.id === assistantActiveConversationId) ?? null,
    [assistantConversations, assistantActiveConversationId],
  );

  const messages = activeConversation?.messages ?? [];
  const hasMessages = messages.length > 0;

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, assistantIsTyping]);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        setAssistantPanelState('closed');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, setAssistantPanelState]);

  // Real backend: POST /assistant/stream/ (SSE, apps.assistant.views.
  // AssistantStreamView) with a non-streaming fallback to /assistant/
  // message/ — see frontend/src/lib/assistant-stream.ts's module docstring
  // for the exact fallback rule (network failure only, never a real 403/
  // 429/503 from the stream endpoint itself).
  const handleSendMessage = useCallback(
    (text: string) => {
      let convId = assistantActiveConversationId;
      if (!convId) {
        convId = startNewAssistantConversation();
      }
      const conversationId = convId;

      const userMsg: ChatMessage = {
        id: `msg-${Date.now()}-user`,
        role: 'user',
        content: text,
        timestamp: Date.now(),
      };
      addAssistantMessage(conversationId, userMsg);

      setAssistantTyping(true);
      setAssistantError(null);

      const backendConversationId = useAppStore
        .getState()
        .assistantConversations.find((c) => c.id === conversationId)?.backendConversationId;

      const payload: AssistantRequestPayload = {
        question: text,
        ...buildRequestScope(assistantContext, parseContentRef),
        ...(backendConversationId ? { conversation_id: backendConversationId } : {}),
      };

      const assistantMsgId = `msg-${Date.now()}-assistant`;
      let streamedText = '';
      let bubbleCreated = false;

      const finalize = (result: AssistantAnswer) => {
        setConversationBackendId(conversationId, result.conversation_id);
        const sources = citationsToSources(result.citations);
        if (bubbleCreated) {
          updateAssistantMessage(conversationId, assistantMsgId, {
            content: result.answer, sources, followUps: result.suggestions, isStreaming: false,
          });
        } else {
          addAssistantMessage(conversationId, {
            id: assistantMsgId, role: 'assistant', content: result.answer, timestamp: Date.now(),
            sources, followUps: result.suggestions,
          });
        }
        setAssistantTyping(false);
      };

      const handleServerError = (message: string) => {
        setAssistantTyping(false);
        setAssistantError(message);
      };

      streamAssistantMessage(payload, {
        onToken: (delta) => {
          streamedText += delta;
          if (!bubbleCreated) {
            bubbleCreated = true;
            setAssistantTyping(false);
            addAssistantMessage(conversationId, {
              id: assistantMsgId, role: 'assistant', content: streamedText, timestamp: Date.now(), isStreaming: true,
            });
          } else {
            updateAssistantMessage(conversationId, assistantMsgId, { content: streamedText });
          }
        },
        onDone: finalize,
        onServerError: handleServerError,
      }).catch(async (err) => {
        if (!(err instanceof StreamUnavailableError)) {
          handleServerError('The assistant is temporarily unavailable. Please try again shortly.');
          return;
        }
        // Genuine network failure opening the stream — fall back to the
        // non-streaming endpoint, exactly once, same as assistant.js.
        try {
          const result = await sendAssistantMessage(payload);
          finalize(result);
        } catch {
          handleServerError('The assistant is temporarily unavailable. Please try again shortly.');
        }
      });
    },
    [
      assistantActiveConversationId, assistantContext, startNewAssistantConversation, addAssistantMessage,
      updateAssistantMessage, setConversationBackendId, setAssistantTyping, setAssistantError,
    ],
  );

  const handleSuggestionClick = useCallback(
    (text: string) => {
      handleSendMessage(text);
    },
    [handleSendMessage],
  );

  const handleNewConversation = useCallback(() => {
    startNewAssistantConversation();
  }, [startNewAssistantConversation]);

  const handleClose = useCallback(() => setAssistantPanelState('closed'), [setAssistantPanelState]);
  const handleMinimize = useCallback(() => setAssistantPanelState('minimized'), [setAssistantPanelState]);
  const handleRestore = useCallback(() => setAssistantPanelState('open'), [setAssistantPanelState]);

  const isNonGlobalContext = assistantContext.type !== 'global';

  return (
    <AnimatePresence mode="wait">
      {isOpen && (
        <>
          {/* Mobile backdrop overlay */}
          <motion.div
            key="assistant-backdrop"
            variants={BACKDROP_VARIANTS}
            initial="closed"
            animate="open"
            exit="closed"
            transition={{ duration: 0.25 }}
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden"
            onClick={handleClose}
          />

          {/* Panel */}
          <motion.div
            key="assistant-panel"
            variants={PANEL_VARIANTS}
            initial="closed"
            animate="open"
            exit="closed"
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="assistant-panel fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-border bg-surface shadow-2xl lg:inset-y-4 lg:right-4 lg:w-[420px] lg:rounded-2xl"
          >
            {/* ─── Header ─── */}
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              {/* AI Avatar + Title */}
              <div className="flex min-w-0 flex-1 items-center gap-2.5">
                <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                  <Sparkles className="h-4 w-4 text-primary" />
                  {/* Online indicator */}
                  <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface bg-emerald-500" />
                </div>
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold text-ink">AI Compass Assistant</h2>
                  <p className="text-[11px] text-emerald-600 dark:text-emerald-400">Online</p>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-0.5">
                <button
                  onClick={handleNewConversation}
                  className="rounded-lg p-2 text-ink-muted transition-colors hover:bg-muted hover:text-ink"
                  title="New conversation"
                >
                  <Plus className="h-4 w-4" />
                </button>
                <button
                  onClick={handleMinimize}
                  className="hidden rounded-lg p-2 text-ink-muted transition-colors hover:bg-muted hover:text-ink lg:block"
                  title="Minimize"
                >
                  <Minus className="h-4 w-4" />
                </button>
                <button
                  onClick={handleClose}
                  className="rounded-lg p-2 text-ink-muted transition-colors hover:bg-muted hover:text-ink"
                  title="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* ─── Context Indicator ─── */}
            {isNonGlobalContext && (
              <div className="border-b border-border px-4 py-2">
                <ContextIndicator context={assistantContext} />
              </div>
            )}

            {/* ─── Messages Area ─── */}
            <div
              ref={scrollContainerRef}
              className="assistant-messages flex-1 overflow-y-auto"
            >
              {hasMessages ? (
                <div className="flex flex-col gap-4 py-4">
                  {messages.map((msg) => (
                    <MessageBubble
                      key={msg.id}
                      message={msg}
                      onFollowUpClick={handleSuggestionClick}
                    />
                  ))}

                  {/* Typing indicator */}
                  <AnimatePresence>
                    {assistantIsTyping && <TypingIndicator />}
                  </AnimatePresence>

                  {/* Error state */}
                  {assistantError && (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mx-4 flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2.5 text-sm text-destructive"
                    >
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      <span>{assistantError}</span>
                    </motion.div>
                  )}

                  <div ref={messagesEndRef} />
                </div>
              ) : !assistantIsTyping ? (
                <WelcomeState onSuggestionClick={handleSuggestionClick} />
              ) : (
                <div className="flex flex-col gap-4 py-4">
                  <TypingIndicator />
                  <div ref={messagesEndRef} />
                </div>
              )}

              {/* Empty states (error / no context) */}
              {!hasMessages && !assistantIsTyping && !assistantError && (
                <div className="px-4 pb-2">
                  {/* Hidden error/connection states — shown via assistantError state */}
                </div>
              )}
            </div>

            {/* ─── Input Area ─── */}
            <ChatInput onSubmit={handleSendMessage} disabled={assistantIsTyping} />
          </motion.div>
        </>
      )}

      {/* Minimized pill — desktop only */}
      {isMinimized && (
        <motion.button
          key="assistant-minimized"
          initial={{ opacity: 0, scale: 0.9, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.9, y: 10 }}
          transition={{ duration: 0.2 }}
          onClick={handleRestore}
          className="fixed bottom-8 right-8 z-50 hidden items-center gap-2.5 rounded-full border border-border bg-surface px-4 py-2.5 shadow-lg backdrop-blur-md transition-shadow hover:shadow-xl lg:flex"
        >
          <div className="relative flex h-6 w-6 items-center justify-center rounded-lg bg-primary/10">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border-2 border-surface bg-emerald-500" />
          </div>
          <span className="text-sm font-medium text-ink">AI Assistant</span>
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">Resume</span>
        </motion.button>
      )}
    </AnimatePresence>
  );
}