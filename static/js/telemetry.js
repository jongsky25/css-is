/* telemetry.js — passive UX-behavior capture (docs/UX_TELEMETRY_HANDOFF_PLAN.md).
 *
 * Ported from jongsky25/ofis-platform's app/components/Telemetry.tsx + lib/telemetry.ts
 * (commit 7a7e369) to a plain script for this server-rendered (Jinja, full page loads,
 * no client router) app. Loaded once from dash_layout.html, signed-in shell only.
 *
 * Batches sanitized events and ships them to POST /telemetry via sendBeacon (fetch
 * keepalive fallback). Best-effort throughout: never throws into the page, never
 * blocks navigation. Everything sensitive is masked HERE, before it leaves the
 * browser — the server re-sanitizes again on ingest (see app.py telemetry_ingest),
 * never trusting the client mask alone.
 */
(function () {
  "use strict";

  var FLUSH_MS = 10000;
  var MAX_QUEUE = 25;
  var RAGE_WINDOW_MS = 800;
  var RAGE_RADIUS_PX = 24;
  var RAGE_MIN = 3;
  var RAGE_COOLDOWN_MS = 1500;
  var MAX_TEXT = 160;
  var MAX_SELECTOR = 1000;
  var MAX_DEPTH = 6;

  // Elements that legitimately do something when clicked — a click on/inside
  // one is never "dead".
  var INTERACTIVE = 'a,button,input,select,textarea,label,summary,option,' +
    '[role="button"],[role="link"],[role="tab"],[role="menuitem"],[role="switch"],' +
    '[role="checkbox"],[onclick],[tabindex],[data-tour],[contenteditable="true"]';

  // Our own Spot Feedback picker overlay (static/js/feedback.js) — never measure
  // clicks on/inside it as friction against itself.
  var OWN_UI = "#sfBtn, .sf-backdrop, .sf-hl, .sf-toast";

  // ── sanitizers (mirror ui_telemetry.py; re-sanitized server-side too) ──────

  function sanitizeText(s, max) {
    max = max || MAX_TEXT;
    if (!s) return null;
    var clean = String(s).replace(/\s+/g, " ").trim();
    if (!clean) return null;
    clean = clean.replace(/\d{3,}/g, "###").trim();
    if (!clean) return null;
    return clean.length > max ? clean.slice(0, max) + "…" : clean;
  }

  function sanitizeSelector(s) {
    if (!s) return null;
    var clean = String(s).trim();
    if (!clean) return null;
    return clean.length > MAX_SELECTOR ? clean.slice(0, MAX_SELECTOR) : clean;
  }

  var DATE_RE = /^\d{4}-\d{2}(-\d{2})?$/;
  var HEX_TOKEN_RE = /^[0-9a-f]{6,}$/i;
  var NUMERIC_ID_RE = /^\d+$/;

  // Best-effort route mask: numeric id / hex token (the /r/<token>, /e/<token>
  // link shapes) / date segment -> a placeholder, same curly-brace convention
  // as monitoring.bucket_path. Query string and hash are dropped. Idempotent —
  // see ui_telemetry.mask_route for why that matters.
  function maskRoute(path) {
    if (!path) return "/";
    var p = String(path);
    var cut = p.search(/[?#]/);
    if (cut >= 0) p = p.slice(0, cut);
    p = p.replace(/^https?:\/\/[^/]+/i, "");
    if (p.charAt(0) !== "/") p = "/" + p;
    var masked = p.split("/").map(function (seg) {
      if (!seg) return seg;
      if (DATE_RE.test(seg)) return "{date}";
      if (HEX_TOKEN_RE.test(seg)) return "{token}";
      if (NUMERIC_ID_RE.test(seg)) return "{id}";
      return seg;
    }).join("/");
    return masked.length > 1 ? masked.replace(/\/$/, "") : masked;
  }

  // ── element context (mirror lib/dom-path.ts) ───────────────────────────────

  function cssEscape(s) {
    if (typeof CSS !== "undefined" && typeof CSS.escape === "function") return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (c) { return "\\" + c; });
  }

  // Robust-ish CSS path up from `el`, preferring stable anchors (id, data-tour
  // — this app has no data-testid convention) and capped at MAX_DEPTH.
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    var parts = [];
    var node = el;
    var depth = 0;
    while (node && node.nodeType === 1 && depth < MAX_DEPTH) {
      if (node.id) { parts.unshift("#" + cssEscape(node.id)); break; }
      var tour = node.getAttribute && node.getAttribute("data-tour");
      if (tour) { parts.unshift('[data-tour="' + cssEscape(tour) + '"]'); break; }
      var part = node.tagName.toLowerCase();
      var parent = node.parentElement;
      if (parent) {
        var same = [];
        for (var i = 0; i < parent.children.length; i++) {
          if (parent.children[i].tagName === node.tagName) same.push(parent.children[i]);
        }
        if (same.length > 1) part += ":nth-of-type(" + (same.indexOf(node) + 1) + ")";
      }
      parts.unshift(part);
      node = parent;
      depth++;
    }
    return parts.join(" > ");
  }

  // Nearest data-tour above `el` — the source anchor an opportunity maps back
  // to code with (this app's equivalent of OFIS's data-testid).
  function componentOf(el) {
    var node = el;
    while (node && node !== document.body) {
      var id = node.getAttribute && node.getAttribute("data-tour");
      if (id) return id.slice(0, 120);
      node = node.parentElement;
    }
    return null;
  }

  function elementText(el) {
    var label = (el.getAttribute && el.getAttribute("aria-label")) ||
      el.innerText || el.textContent || el.placeholder || "";
    return sanitizeText(label);
  }

  function isOwnUi(el) {
    return !!(el && el.closest && el.closest(OWN_UI));
  }

  // ── session (sessionStorage, not a JS var — this app does full page loads,
  // not client-side navigation, so a plain variable would fragment every
  // pageview into its own "session") ─────────────────────────────────────────

  function newSessionId() {
    try {
      if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    } catch (e) { /* fall through */ }
    return "s-" + Date.now() + "-" + Math.floor(Math.random() * 1e9);
  }

  function getSessionId() {
    try {
      var existing = sessionStorage.getItem("csiTelemetrySession");
      if (existing) return existing;
      var id = newSessionId();
      sessionStorage.setItem("csiTelemetrySession", id);
      return id;
    } catch (e) {
      return newSessionId();
    }
  }

  var sessionId = getSessionId();
  var queue = [];
  var recentClicks = [];
  var lastRageAt = 0;

  // ── queue + flush ───────────────────────────────────────────────────────────

  function flush() {
    if (queue.length === 0) return;
    var batch = queue;
    queue = [];
    try {
      var blob = new Blob([JSON.stringify({ events: batch })], { type: "application/json" });
      var ok = navigator.sendBeacon && navigator.sendBeacon("/telemetry", blob);
      if (!ok) {
        fetch("/telemetry", { method: "POST", body: blob, keepalive: true }).catch(function () {});
      }
    } catch (e) {
      // Telemetry is best-effort — never surface an error to the user.
    }
  }

  function enqueue(ev) {
    queue.push(ev);
    if (queue.length >= MAX_QUEUE) flush();
  }

  function record(eventType, opts) {
    opts = opts || {};
    var el = opts.el || null;
    enqueue({
      event_type: eventType,
      route: maskRoute(location.pathname),
      component: el ? componentOf(el) : null,
      element_selector: el ? sanitizeSelector(cssPath(el)) : null,
      element_text: el ? elementText(el) : null,
      meta: opts.meta || null,
      session_id: sessionId,
    });
  }

  setInterval(flush, FLUSH_MS);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush();
  });
  window.addEventListener("pagehide", flush);

  // ── pageview — one per full page load; meta.from is the referring route
  // (same-origin only) since this app has no client-side router to track a
  // previous-route ref across navigations ────────────────────────────────────

  (function () {
    var from = null;
    if (document.referrer) {
      try {
        var refUrl = new URL(document.referrer);
        if (refUrl.origin === location.origin) from = maskRoute(refUrl.pathname);
      } catch (e) { /* malformed/opaque referrer — ignore */ }
    }
    record("pageview", { meta: from ? { from: from } : null });
  })();

  // ── dead clicks + rage clicks ────────────────────────────────────────────

  document.addEventListener("click", function (e) {
    var target = e.target;
    if (!target || isOwnUi(target)) return;

    var now = Date.now();
    recentClicks = recentClicks.filter(function (c) { return now - c.t < RAGE_WINDOW_MS; });
    recentClicks.push({ x: e.clientX, y: e.clientY, t: now });
    var near = recentClicks.filter(function (c) {
      return Math.abs(c.x - e.clientX) <= RAGE_RADIUS_PX && Math.abs(c.y - e.clientY) <= RAGE_RADIUS_PX;
    });
    if (near.length >= RAGE_MIN && now - lastRageAt > RAGE_COOLDOWN_MS) {
      lastRageAt = now;
      recentClicks = [];
      record("rage_click", { el: target });
      return;
    }

    if (!(target.closest && target.closest(INTERACTIVE))) record("dead_click", { el: target });
  }, true);

  // ── empty-search signal (dispatched by any search UI that wants to report
  // it — none does yet, this just wires the listener so one can) + client
  // errors ─────────────────────────────────────────────────────────────────

  window.addEventListener("csi:search-empty", function (e) {
    var term = e.detail && e.detail.term;
    record("search_empty", { meta: { term: sanitizeText(term, 80) } });
  });
  window.addEventListener("error", function (e) {
    record("client_error", { meta: { name: (e.error && e.error.name) || "Error", message: sanitizeText(e.message, 80) } });
  });
  window.addEventListener("unhandledrejection", function (e) {
    var reason = e.reason;
    var name = (reason && reason.name) || "UnhandledRejection";
    var reasonMessage = reason && typeof reason.message === "string" ? reason.message : String(reason || "");
    record("client_error", { meta: { name: name, message: sanitizeText(reasonMessage, 80) } });
  });
})();
