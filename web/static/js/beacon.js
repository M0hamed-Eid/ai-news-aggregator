/*
 * Behavioral instrumentation beacon (M7) — vanilla JS, no framework, no build
 * step, matching this project's zero-JS-tooling convention. Only activates
 * for authenticated users (window.__AC_USER_ID set by base.html); anonymous
 * traffic never attempts a single request here.
 *
 * - IntersectionObserver fires one "impression" event per card the first
 *   time it becomes visible.
 * - visibilitychange accumulates visible time and flushes a "dwell" event
 *   (+ a coarse page-level "scroll" depth event) via navigator.sendBeacon
 *   when the tab is hidden/closed — sendBeacon is the only transport that
 *   reliably fires on unload.
 * - Periodic flush (every 10s) also drains the impression queue via
 *   sendBeacon, so a long, uninterrupted session doesn't hold everything
 *   until the very end.
 * - Save/Hide buttons use a normal fetch() with the standard Django AJAX
 *   CSRF pattern (X-CSRFToken header from the csrftoken cookie) — a normal
 *   same-origin request, unlike the beacon endpoint below.
 * - Follow/unfollow chip buttons (M9 — entity/topic chips on detail pages)
 *   use the identical fetch()+CSRF pattern against /behavior/follow/.
 */
(function () {
  "use strict";

  if (!window.__AC_USER_ID) return; // anonymous — instrument nothing

  var EVENTS_URL = "/behavior/events/";
  var FLUSH_INTERVAL_MS = 10000;
  var queue = [];
  var seenImpressions = new Set();
  var pageEnteredAt = Date.now();
  var maxScrollDepthPct = 0;

  function enqueue(evt) {
    queue.push(evt);
  }

  function flush(useBeacon) {
    if (queue.length === 0) return;
    var payload = JSON.stringify({ events: queue.splice(0, queue.length) });
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon(EVENTS_URL, new Blob([payload], { type: "application/json" }));
    } else {
      fetch(EVENTS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
      }).catch(function () {
        /* best-effort telemetry — a dropped batch isn't worth retry logic */
      });
    }
  }

  // ---- Impressions (IntersectionObserver) ---------------------------------
  // observeCards() is exposed via window.ACBeacon.observeNew so cards
  // injected later (e.g. My Feed's "Show More" button, see below) can be
  // wired into the same observer instead of only ever seeing the cards
  // present at script-load time.
  var observer = null;
  if ("IntersectionObserver" in window) {
    observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var el = entry.target;
          var key = el.dataset.contentType + ":" + el.dataset.contentId;
          if (seenImpressions.has(key)) return;
          seenImpressions.add(key);
          enqueue({
            event_type: "impression",
            content_type: el.dataset.contentType,
            content_id: parseInt(el.dataset.contentId, 10),
          });
          observer.unobserve(el);
        });
      },
      { threshold: 0.5 }
    );
  }

  function observeCards(root) {
    if (!observer) return;
    var scope = root || document;
    var cards = scope.querySelectorAll("[data-content-type][data-content-id]");
    cards.forEach(function (el) {
      observer.observe(el);
    });
  }

  observeCards(document);
  window.ACBeacon = { observeNew: observeCards };

  // ---- Clicks ---------------------------------------------------------------
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-content-type][data-content-id]");
    if (!el) return;
    // Ignore clicks on the save/hide toggle buttons themselves — those log
    // their own "save"/"hide" event server-side when they actually flip on.
    if (e.target.closest(".btn-icon-toggle")) return;
    enqueue({
      event_type: "click",
      content_type: el.dataset.contentType,
      content_id: parseInt(el.dataset.contentId, 10),
    });
  });

  // ---- Scroll depth (coarse, page-level) -------------------------------------
  window.addEventListener(
    "scroll",
    function () {
      var doc = document.documentElement;
      var scrolled = doc.scrollTop + doc.clientHeight;
      var pct = doc.scrollHeight ? Math.min(100, Math.round((scrolled / doc.scrollHeight) * 100)) : 0;
      if (pct > maxScrollDepthPct) maxScrollDepthPct = pct;
    },
    { passive: true }
  );

  // ---- Dwell + final flush on visibilitychange / unload ---------------------
  function flushDwellAndScroll() {
    var dwellMs = Date.now() - pageEnteredAt;
    enqueue({ event_type: "dwell", value: dwellMs });
    if (maxScrollDepthPct > 0) {
      enqueue({ event_type: "scroll", value: maxScrollDepthPct });
    }
    flush(true);
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      flushDwellAndScroll();
    } else {
      pageEnteredAt = Date.now(); // resumed — restart the dwell clock
    }
  });
  window.addEventListener("pagehide", flushDwellAndScroll);

  setInterval(function () {
    flush(false);
  }, FLUSH_INTERVAL_MS);

  // ---- Save / Hide toggle buttons ---------------------------------------------
  function getCsrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".btn-icon-toggle");
    if (!btn) return;
    e.preventDefault();

    var action = btn.dataset.action; // "save" | "hide"
    var url = action === "save" ? "/behavior/save/" : "/behavior/hide/";
    var icon = btn.querySelector("i");

    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({
        content_type: btn.dataset.contentType,
        content_id: parseInt(btn.dataset.contentId, 10),
      }),
    })
      .then(function (r) {
        if (r.status === 403) {
          window.location.href = "/accounts/login/?next=" + encodeURIComponent(window.location.pathname);
          return null;
        }
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (!data) return;
        var field = action === "save" ? "is_saved" : "is_hidden";
        var active = data[field];
        btn.dataset.active = active ? "true" : "false";
        if (action === "save" && icon) {
          icon.className = active ? "bi bi-bookmark-fill" : "bi bi-bookmark";
        }
        if (action === "hide" && icon) {
          icon.className = active ? "bi bi-eye-slash-fill" : "bi bi-eye-slash";
          if (active) {
            var card = btn.closest(".col");
            if (card) card.remove(); // "show less like this" — immediate feedback
          }
        }
      })
      .catch(function () {
        /* best-effort — leave the button in its current visual state */
      });
  });

  // ---- Follow/unfollow chip toggles (M9) ---------------------------------
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".btn-follow-chip");
    if (!btn) return;
    e.preventDefault();

    fetch("/behavior/follow/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({
        target_type: btn.dataset.targetType,
        target_key: btn.dataset.targetKey,
      }),
    })
      .then(function (r) {
        if (r.status === 403) {
          window.location.href = "/accounts/login/?next=" + encodeURIComponent(window.location.pathname);
          return null;
        }
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (!data) return;
        var active = data.following;
        btn.dataset.active = active ? "true" : "false";
        var icon = btn.querySelector("i");
        if (icon) icon.className = active ? "bi bi-check-lg" : "bi bi-plus-lg";
      })
      .catch(function () {
        /* best-effort — leave the button in its current visual state */
      });
  });

  // ---- My Feed "Show More" (progressive pagination, no full reload) -----
  // FeedView's ?fragment=1 branch returns {html, has_next, next_page} JSON
  // (same all-JSON convention as Save/Hide/Follow above) — no HTML-fragment-
  // with-header response exists anywhere else in this codebase, so this is
  // deliberately kept consistent with the established pattern rather than
  // introducing a second one.
  var showMoreBtn = document.getElementById("feed-show-more");
  if (showMoreBtn) {
    showMoreBtn.addEventListener("click", function () {
      var nextPage = showMoreBtn.dataset.nextPage;
      if (!nextPage) return;

      showMoreBtn.disabled = true;
      var originalHtml = showMoreBtn.innerHTML;
      showMoreBtn.innerHTML = "Loading…";

      fetch("?fragment=1&page=" + encodeURIComponent(nextPage))
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          if (!data) return;
          var container = document.getElementById("feed-items");
          if (container && data.html) {
            container.insertAdjacentHTML("beforeend", data.html);
            observeCards(container); // wire impressions for the newly-injected cards
          }
          if (data.has_next && data.next_page) {
            showMoreBtn.dataset.nextPage = data.next_page;
          } else {
            var wrap = document.getElementById("feed-show-more-wrap");
            if (wrap) wrap.remove();
          }
        })
        .catch(function () {
          /* best-effort — button stays enabled below so the user can retry */
        })
        .finally(function () {
          showMoreBtn.disabled = false;
          showMoreBtn.innerHTML = originalHtml;
        });
    });
  }
})();
