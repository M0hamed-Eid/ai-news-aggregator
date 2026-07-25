'use client';

import { motion } from 'framer-motion';
import type { ChatMessage } from '@/lib/types';
import { useState, useCallback } from 'react';
import {
  Copy,
  Check,
  ThumbsUp,
  ThumbsDown,
  Sparkles,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import SourceCard from './SourceCard';
import FollowUpSuggestions from './FollowUpSuggestions';

function formatTime(ts: number) {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

interface MessageBubbleProps {
  message: ChatMessage;
  onFollowUpClick: (text: string) => void;
}

export default function MessageBubble({ message, onFollowUpClick }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [liked, setLiked] = useState<'up' | 'down' | null>(null);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [message.content]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className={`flex items-start gap-2.5 px-4 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
        </div>
      )}

      <div className={`flex max-w-[85%] flex-col gap-2 ${isUser ? 'items-end' : ''}`}>
        {/* Bubble */}
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? 'rounded-tr-sm bg-primary text-white dark:text-primary-foreground'
              : 'rounded-tl-sm bg-muted text-ink'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose-compass max-w-none !my-0 [&_p]:text-sm [&_p]:leading-relaxed [&_p]:text-ink [&_h1]:text-base [&_h2]:text-[15px] [&_h2]:mt-4 [&_h2]:mb-2 [&_h3]:text-[14px] [&_h3]:mt-3 [&_h3]:mb-1.5 [&_ul]:text-sm [&_ol]:text-sm [&_li]:text-sm [&_li]:mb-1 [&_blockquote]:border-l-2 [&_blockquote]:border-primary/30 [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:text-ink-muted [&_a]:text-primary [&_a]:underline [&_table]:w-full [&_table]:text-xs [&_th]:text-left [&_th]:px-2 [&_th]:py-1.5 [&_th]:border-b [&_th]:border-border [&_th]:font-medium [&_td]:px-2 [&_td]:py-1.5 [&_td]:border-b [&_td]:border-border [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_code]:font-mono [&_pre]:!m-0 [&_pre]:!rounded-lg [&_pre]:!bg-[#282a36] [&_pre]:p-3">
              <ReactMarkdown
                components={{
                  code(props) {
                    const { children, className, ...rest } = props;
                    const isBlock = className?.startsWith('language-');
                    if (isBlock) {
                      return (
                        <SyntaxHighlighter
                          style={oneDark}
                          language={className.replace('language-', '')}
                          PreTag="div"
                          customStyle={{
                            margin: 0,
                            borderRadius: '0.5rem',
                            fontSize: '12px',
                          }}
                        >
                          {String(children).replace(/\n$/, '')}
                        </SyntaxHighlighter>
                      );
                    }
                    return (
                      <code className={className} {...rest}>
                        {children}
                      </code>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Timestamp + Actions (assistant only) */}
        {!isUser && (
          <div className="flex items-center gap-1 pl-1">
            <span className="text-[10px] text-ink-muted/60">{formatTime(message.timestamp)}</span>
            <span className="mx-1 text-[10px] text-ink-muted/30">|</span>
            <button
              onClick={handleCopy}
              className="rounded p-1 text-ink-muted/50 transition-colors hover:bg-muted hover:text-ink-muted"
              title="Copy"
            >
              {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
            </button>
            <button
              onClick={() => setLiked(liked === 'up' ? null : 'up')}
              className={`rounded p-1 transition-colors hover:bg-muted ${
                liked === 'up' ? 'text-primary' : 'text-ink-muted/50 hover:text-ink-muted'
              }`}
              title="Helpful"
            >
              <ThumbsUp className="h-3 w-3" />
            </button>
            <button
              onClick={() => setLiked(liked === 'down' ? null : 'down')}
              className={`rounded p-1 transition-colors hover:bg-muted ${
                liked === 'down' ? 'text-destructive' : 'text-ink-muted/50 hover:text-ink-muted'
              }`}
              title="Not helpful"
            >
              <ThumbsDown className="h-3 w-3" />
            </button>
          </div>
        )}

        {/* Source references */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="flex flex-col gap-2">
            {message.sources.map((src) => (
              <SourceCard key={src.id} source={src} />
            ))}
          </div>
        )}

        {/* Follow-up suggestions */}
        {!isUser && message.followUps && message.followUps.length > 0 && (
          <FollowUpSuggestions
            suggestions={message.followUps}
            onClick={onFollowUpClick}
          />
        )}
      </div>
    </motion.div>
  );
}