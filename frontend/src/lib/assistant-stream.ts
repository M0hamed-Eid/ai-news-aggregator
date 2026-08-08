// Real RAG assistant transport — mirrors web/static/js/assistant.js's
// PROVEN sendViaStream()/renderAnswerHtml() logic exactly (same SSE frame
// shapes, same "network failure only" fallback rule), just as a reusable
// TypeScript module instead of vanilla JS baked into a Django template.
//
// POST /assistant/stream/ -> "data: {...}\n\n" frames: {type:'token', text}
// while generating, then one final {type:'done', answer, citations,
// grounded, suggestions, conversation_id} or {type:'error', error}.
// POST /assistant/message/ -> the same final shape, non-streaming — the
// fallback used ONLY when the stream never even connects (a real 403/429/
// 503 from the stream endpoint itself is surfaced directly, not retried
// here, since the non-streaming endpoint would fail identically).
import { api, apiUrl, getCsrfToken } from './api';
import type { AssistantContextType } from './types';

export interface Citation {
  marker: string;
  content_type: string;
  content_id: number;
  chunk_index: number;
  title: string;
  url: string;
  source?: string | null;
  start_seconds?: number | null;
  end_seconds?: number | null;
}

export interface AssistantAnswer {
  answer: string;
  citations: Citation[];
  grounded: boolean;
  suggestions: string[];
  conversation_id: number;
}

export interface AssistantRequestPayload {
  question: string;
  scope: 'article' | 'video' | 'topic' | 'kb';
  content_type?: 'article' | 'youtube_video';
  content_id?: number;
  topic_slug?: string;
  conversation_id?: number;
}

// Maps the panel's current AssistantContextType to the request shape
// apps.assistant.views._parse_message_payload expects. 'search'/'global'
// both resolve to the whole-knowledge-base scope — there is no dedicated
// "search" scope server-side.
export function buildRequestScope(
  context: AssistantContextType,
  parseContentRef: (id: string) => { contentType: 'article' | 'youtube_video'; contentId: number } | null
): Pick<AssistantRequestPayload, 'scope' | 'content_type' | 'content_id' | 'topic_slug'> {
  if (context.type === 'article' || context.type === 'video') {
    const ref = parseContentRef(context.id);
    if (ref) {
      return { scope: context.type, content_type: ref.contentType, content_id: ref.contentId };
    }
  }
  if (context.type === 'topic') {
    return { scope: 'topic', topic_slug: context.label };
  }
  return { scope: 'kb' };
}

export function sendAssistantMessage(payload: AssistantRequestPayload): Promise<AssistantAnswer> {
  return api.post<AssistantAnswer>('/assistant/message/', payload);
}

export interface StreamCallbacks {
  onToken: (delta: string) => void;
  onDone: (result: AssistantAnswer) => void;
  /** A real error FROM THE SERVER (rate limit, not configured, etc.) —
   * terminal, do not fall back to sendAssistantMessage for this case. */
  onServerError: (message: string) => void;
}

/** Throws only when the stream never genuinely connected (network failure,
 * not a server error response) — callers catch this specific case to fall
 * back to sendAssistantMessage(), matching assistant.js's exact rule. */
export class StreamUnavailableError extends Error {}

export async function streamAssistantMessage(payload: AssistantRequestPayload, callbacks: StreamCallbacks): Promise<void> {
  let res: Response;
  try {
    res = await fetch(apiUrl('/assistant/stream/'), {
      method: 'POST',
      credentials: 'include',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new StreamUnavailableError('network error opening the assistant stream');
  }

  if (!res.ok || !res.body) {
    // A real response came back but signals a server-side failure (403 not
    // logged in, 429 rate-limited, 503 not configured/upstream down) —
    // surface it directly, don't retry via the non-streaming endpoint.
    let message = 'The assistant is temporarily unavailable. Please try again shortly.';
    try {
      const data = await res.json();
      if (data?.error) message = data.error;
    } catch {
      // non-JSON error body — keep the generic message
    }
    callbacks.onServerError(message);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      if (!frame.startsWith('data: ')) continue;
      let data: any;
      try {
        data = JSON.parse(frame.slice(6));
      } catch {
        continue;
      }
      if (data.type === 'token') callbacks.onToken(data.text);
      else if (data.type === 'done') callbacks.onDone(data);
      else if (data.type === 'error') callbacks.onServerError(data.error || 'The assistant is temporarily unavailable. Please try again shortly.');
    }
  }
}
