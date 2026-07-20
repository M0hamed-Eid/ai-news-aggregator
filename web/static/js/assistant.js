/*
 * AI Assistant floating chat widget (M14) — vanilla JS, no build step, same
 * self-contained-per-file convention as beacon.js (each script defines its
 * own getCsrfToken() — there's no shared JS utils module in this project).
 *
 * Reads page context from #ac-page-context (a per-template JSON block —
 * see article_detail.html/video_detail.html) so "what does this mean?" on
 * an article page automatically scopes retrieval to that article without
 * the user ever naming it. Falls back to whole-knowledge-base scope on any
 * page without that block (lists, home, search, etc.).
 *
 * Conversation memory is per-tab-session only (a JS variable, not
 * persisted across page loads) — reloading the page starts a fresh thread.
 * The backend's GET /assistant/conversations/<id>/ endpoint exists for a
 * future "conversation history" list; this first version doesn't need it.
 *
 * Streaming (M14 Phase D): tries /assistant/stream/ first, rendering tokens
 * live via fetch()+ReadableStream (not the native EventSource API, which
 * can't send a POST body or a CSRF header). Falls back to the plain
 * /assistant/message/ endpoint on any network-level failure — a real
 * server-side error (403/429/503) is shown as-is either way, since retrying
 * on the non-streaming endpoint would fail identically.
 */
(function () {
  "use strict";

  if (!window.__AC_USER_ID) return; // anonymous — the assistant is login-gated server-side too

  var MESSAGE_URL = "/assistant/message/";
  var STREAM_URL = "/assistant/stream/";

  var root = document.getElementById("ac-assistant-root");
  if (!root) return;

  var fab = document.getElementById("ac-assistant-fab");
  var panel = document.getElementById("ac-assistant-panel");
  var closeBtn = document.getElementById("ac-assistant-close");
  var messagesEl = document.getElementById("ac-assistant-messages");
  var emptyStateEl = document.getElementById("ac-assistant-empty");
  var suggestionsEl = document.getElementById("ac-assistant-suggestions");
  var form = document.getElementById("ac-assistant-form");
  var input = document.getElementById("ac-assistant-input");
  var sendBtn = form.querySelector(".ac-assistant-send");
  var scopeGroup = document.getElementById("ac-assistant-scope");
  var scopeDocumentLabel = document.getElementById("ac-scope-document-label");

  var conversationId = null;
  var pageContext = null; // {content_type, content_id} | null
  var pending = false;

  // ---- Page context ---------------------------------------------------------
  var contextEl = document.getElementById("ac-page-context");
  if (contextEl) {
    try {
      var parsed = JSON.parse(contextEl.textContent);
      if (parsed && parsed.content_type && parsed.content_id) {
        pageContext = parsed;
        scopeGroup.hidden = false;
        scopeDocumentLabel.textContent = parsed.content_type === "youtube_video" ? "This video" : "This article";
      }
    } catch (e) {
      /* malformed context block — behave as if there is none */
    }
  }

  function currentScope() {
    if (!pageContext) return { scope: "kb" };
    var checked = scopeGroup.querySelector("input[name='ac-scope']:checked");
    if (checked && checked.value === "document") {
      var scope = pageContext.content_type === "youtube_video" ? "video" : "article";
      return { scope: scope, content_type: pageContext.content_type, content_id: pageContext.content_id };
    }
    return { scope: "kb" };
  }

  // ---- Open / close -----------------------------------------------------------
  function openPanel() {
    panel.hidden = false;
    fab.setAttribute("aria-expanded", "true");
    input.focus();
  }

  function closePanel() {
    panel.hidden = true;
    fab.setAttribute("aria-expanded", "false");
  }

  fab.addEventListener("click", function () {
    if (panel.hidden) openPanel();
    else closePanel();
  });
  closeBtn.addEventListener("click", closePanel);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) closePanel();
  });

  // ---- CSRF (same pattern as beacon.js) ----------------------------------------
  function getCsrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  // ---- Rendering ----------------------------------------------------------------
  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // Turns raw answer text (paragraphs separated by blank lines, [S#] citation
  // markers still inline — see app/agents/assistant_agent.py, which only
  // strips INVENTED markers, never real ones) into safe HTML with each valid
  // marker replaced by a clickable citation chip. The model's output is plain
  // prose (no headers/lists in practice, per the system prompt), so this is
  // deliberately not a general markdown parser — just paragraphs + citations.
  function renderAnswerHtml(text, citations) {
    var byMarker = {};
    (citations || []).forEach(function (c) {
      byMarker[c.marker] = c;
    });

    var escaped = escapeHtml(text);
    var withCitations = escaped.replace(/\[S(\d+)\]/g, function (whole, n) {
      var citation = byMarker["S" + n];
      if (!citation) return "";
      var title = escapeHtml(citation.title || "");
      return (
        '<a class="ac-citation" href="' + escapeHtml(citation.url) + '" target="_blank" rel="noopener" title="' + title + '">' +
        n + "</a>"
      );
    });

    var paragraphs = withCitations
      .split(/\n\s*\n/)
      .map(function (p) {
        return "<p>" + p.replace(/\n/g, "<br>") + "</p>";
      })
      .join("");
    return paragraphs;
  }

  function renderSourcesHtml(citations) {
    if (!citations || !citations.length) return "";
    var seen = {};
    var links = [];
    citations.forEach(function (c) {
      var key = c.content_type + ":" + c.content_id;
      if (seen[key]) return;
      seen[key] = true;
      links.push(
        '<a class="ac-msg-source-link" href="' + escapeHtml(c.url) + '" target="_blank" rel="noopener">' +
        '<i class="bi bi-box-arrow-up-right"></i> ' + escapeHtml(c.title || c.url) + "</a>"
      );
    });
    return '<div class="ac-msg-sources">' + links.join("") + "</div>";
  }

  function appendMessage(role, html, extraClass) {
    if (emptyStateEl) {
      emptyStateEl.remove();
      emptyStateEl = null;
    }
    var el = document.createElement("div");
    el.className = "ac-msg ac-msg-" + role + (extraClass ? " " + extraClass : "");
    el.innerHTML = html;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  function appendUserMessage(text) {
    appendMessage("user", "<p>" + escapeHtml(text) + "</p>");
  }

  function appendAssistantMessage(result) {
    var html = renderAnswerHtml(result.answer, result.citations) + renderSourcesHtml(result.citations);
    appendMessage("assistant", html);
    renderSuggestions(result.suggestions);
  }

  function appendUnavailableMessage(text) {
    appendMessage("assistant", "<p>" + escapeHtml(text) + "</p>", "ac-msg-unavailable");
  }

  function showTyping() {
    var el = document.createElement("div");
    el.className = "ac-typing";
    el.id = "ac-typing-indicator";
    el.innerHTML = "<span></span><span></span><span></span>";
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function hideTyping() {
    var el = document.getElementById("ac-typing-indicator");
    if (el) el.remove();
  }

  function renderSuggestions(suggestions) {
    suggestionsEl.innerHTML = "";
    (suggestions || []).forEach(function (s) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "ac-suggestion-chip";
      chip.textContent = s;
      chip.addEventListener("click", function () {
        input.value = s;
        form.requestSubmit ? form.requestSubmit() : sendCurrentInput();
      });
      suggestionsEl.appendChild(chip);
    });
  }

  // ---- Send -----------------------------------------------------------------------
  function setPending(isPending) {
    pending = isPending;
    sendBtn.disabled = isPending;
    input.disabled = isPending;
  }

  function errorMessageFor(status, data) {
    if (status === 403) return data.error || "You've reached your daily limit — upgrade to Pro for unlimited access.";
    if (status === 429) return data.error || "Slow down a little — try again in a moment.";
    return data.error || "The assistant is temporarily unavailable. Please try again shortly.";
  }

  // A definitive server response (success or a real 403/429/503 with a JSON
  // body) — never worth retrying on the other endpoint, so this always
  // RESOLVES (never rejects) once the server has actually answered.
  function sendViaNonStreaming(payload) {
    return fetch(MESSAGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify(payload),
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        hideTyping();
        if (!res.ok) {
          appendUnavailableMessage(errorMessageFor(res.status, data));
          return;
        }
        conversationId = data.conversation_id || conversationId;
        appendAssistantMessage(data);
      });
    });
  }

  // Cuts a trailing, still-arriving "SUGGESTIONS: ..." trailer out of the
  // LIVE display buffer before the server has had a chance to strip it —
  // otherwise it would briefly flash as visible chat text mid-stream.
  function liveDisplayText(buffer) {
    var idx = buffer.search(/\n\s*SUGGESTIONS:/i);
    return idx === -1 ? buffer : buffer.slice(0, idx);
  }

  // Rejects ONLY on a network-level failure (no response at all, or the
  // browser can't stream) — the caller falls back to sendViaNonStreaming()
  // in that case. A real server error (403/429/503) resolves normally, same
  // as sendViaNonStreaming, since retrying elsewhere wouldn't help.
  function sendViaStream(payload) {
    return fetch(STREAM_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify(payload),
    }).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          hideTyping();
          appendUnavailableMessage(errorMessageFor(res.status, data));
        });
      }
      if (!res.body || !window.ReadableStream) {
        throw new Error("streaming not supported"); // network-level — triggers fallback
      }

      hideTyping();
      var bubble = appendMessage("assistant", "");
      var buffer = "";
      var sseBuffer = "";
      var reader = res.body.getReader();
      var decoder = new TextDecoder();

      function handleFrame(frame) {
        if (frame.indexOf("data: ") !== 0) return;
        var data;
        try {
          data = JSON.parse(frame.slice(6));
        } catch (e) {
          return;
        }
        if (data.type === "token") {
          buffer += data.text;
          bubble.innerHTML = renderAnswerHtml(liveDisplayText(buffer), []);
          messagesEl.scrollTop = messagesEl.scrollHeight;
        } else if (data.type === "done") {
          bubble.innerHTML = renderAnswerHtml(data.answer, data.citations) + renderSourcesHtml(data.citations);
          conversationId = data.conversation_id || conversationId;
          renderSuggestions(data.suggestions);
        } else if (data.type === "error") {
          bubble.remove();
          appendUnavailableMessage(data.error || "The assistant is temporarily unavailable. Please try again shortly.");
        }
      }

      function pump() {
        return reader.read().then(function (chunk) {
          if (chunk.done) return;
          sseBuffer += decoder.decode(chunk.value, { stream: true });
          var frames = sseBuffer.split("\n\n");
          sseBuffer = frames.pop(); // keep a possibly-incomplete trailing frame for the next chunk
          frames.forEach(handleFrame);
          return pump();
        });
      }
      return pump();
    });
  }

  function sendCurrentInput() {
    var question = input.value.trim();
    if (!question || pending) return;

    input.value = "";
    suggestionsEl.innerHTML = "";
    appendUserMessage(question);
    showTyping();
    setPending(true);

    var scoped = currentScope();
    var payload = {
      question: question,
      scope: scoped.scope,
      content_type: scoped.content_type,
      content_id: scoped.content_id,
    };
    if (conversationId) payload.conversation_id = conversationId;

    sendViaStream(payload)
      .catch(function () {
        return sendViaNonStreaming(payload);
      })
      .catch(function () {
        hideTyping();
        appendUnavailableMessage("The assistant is temporarily unavailable. Please try again shortly.");
      })
      .finally(function () {
        setPending(false);
        input.focus();
      });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    sendCurrentInput();
  });
})();
