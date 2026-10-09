/* The assistant client — shared by /start and the search box.
 * (docs/AI_INTEGRATION_PLAN.md Phase 1-2-9, docs/HOME_SEARCH_ASSISTANT_PLAN.md Phase 7.)
 *
 *   window.CSSAssistant.ask(raw, mountEl, opts)
 *
 * Posts the typed query to POST /api/ai/route. On {"kind":"navigate", ...} it
 * shows a result card (Go/Cancel + 👍/👎) and, when opts.autoNavigate is on,
 * navigates after ~1.5s. On {"kind":"answer"|"help", ...} it shows the
 * server-templated sentence or guide excerpt with the same 👍/👎, no
 * auto-navigate. On {"kind":"action", ...} (assistant mode only) it shows a
 * confirmation card describing exactly what will happen, with a Confirm button
 * that submits the *real* request (a hidden form POST, or a plain navigation
 * for a GET export) to the existing, independently capability-checked +
 * audited endpoint — nothing the model said is ever executed directly, only
 * what the user clicks Confirm on. On anything else — {"kind":"fallback"}, a
 * non-2xx response, or the client-side timeout — it calls opts.onFallback(raw)
 * and shows nothing itself, so the caller decides what "no answer" looks like
 * (/start shows the keyword palette; the search box just drops its Ask row).
 *
 * Assistant mode is also conversational: a short in-memory history of the last
 * few exchanges is replayed to the server on every request so a follow-up like
 * "do it" can resolve against what was just discussed. The history never
 * leaves this tab (no storage) and is capped in length.
 *
 * opts: statusEl      — element to un-hide while waiting (optional)
 *       timeoutMs     — client budget before it degrades to onFallback (default 9000)
 *       autoNavigate  — navigate cards navigate on their own after 1.5s (default true)
 *       onFallback(raw)
 *       onSettled(kind) — called once the reply is rendered ("navigate", "answer", ...)
 */
(function () {
  "use strict";
  if (window.CSSAssistant) return;               // /start loads this twice (page + layout)

  var NAV_DELAY_MS = 1500;
  var HISTORY_MAX = 6;            // exchanges kept (user+assistant pairs), tab-local only
  var history = [];

  function pushHistory(role, text) {
    if (!text) return;
    history.push({ role: role, text: String(text).slice(0, 300) });
    if (history.length > HISTORY_MAX) history = history.slice(-HISTORY_MAX);
  }

  function esc(s) {
    var n = document.createElement("div");
    n.textContent = s == null ? "" : s;
    return n.innerHTML;
  }

  // Per-mount state, so /start and the search box can each have their own.
  function stateOf(mount) {
    if (!mount._csa) mount._csa = { last: "", timer: null };
    return mount._csa;
  }

  function clear(mount) {
    var s = stateOf(mount);
    if (s.timer) { clearTimeout(s.timer); s.timer = null; }
    mount.innerHTML = "";
  }

  function sendFeedback(interactionId, rating) {
    var body = "interaction_id=" + encodeURIComponent(interactionId) +
      "&rating=" + encodeURIComponent(rating);
    var sent = false;
    if (navigator.sendBeacon) {
      try {
        sent = navigator.sendBeacon("/api/ai/feedback",
          new Blob([body], { type: "application/x-www-form-urlencoded" }));
      } catch (e) { sent = false; }
    }
    if (!sent) {
      fetch("/api/ai/feedback", {
        method: "POST", body: body, keepalive: true,
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      }).catch(function () {});
    }
  }

  function wireFeedback(card, interactionId) {
    var fbBtns = card.querySelectorAll(".fb-btn");
    for (var i = 0; i < fbBtns.length; i++) {
      fbBtns[i].addEventListener("click", function (e) {
        var btn = e.currentTarget;
        sendFeedback(interactionId, btn.dataset.r);
        for (var j = 0; j < fbBtns.length; j++) fbBtns[j].disabled = true;
        btn.classList.add("fb-sent");
      });
    }
  }

  var FB = '<span class="start-fb">' +
    '<button type="button" class="fb-btn" data-r="up" aria-label="Good suggestion">👍</button>' +
    '<button type="button" class="fb-btn" data-r="down" aria-label="Not helpful">👎</button>' +
    "</span>";

  function showCard(mount, data, raw, opts) {
    clear(mount);
    var card = document.createElement("div");
    card.className = "start-card";
    card.innerHTML =
      '<p class="start-card-msg">' +
      (opts.autoNavigate ? "Taking you to " : "Open ") + '<strong>' + esc(data.label) + '</strong> — ' +
      esc(data.hint) + "</p>" +
      '<div class="start-card-actions">' +
      '<a class="btn" href="' + esc(data.url) + '">Go now</a>' +
      '<button type="button" class="btn ghost" id="startCancel">Cancel</button>' +
      FB + "</div>";
    mount.appendChild(card);

    card.querySelector("#startCancel").addEventListener("click", function () {
      var s = stateOf(mount);
      if (s.timer) { clearTimeout(s.timer); s.timer = null; }
      if (opts.onFallback) opts.onFallback(raw); else clear(mount);
    });
    wireFeedback(card, data.interaction_id);
    if (opts.autoNavigate) {
      stateOf(mount).timer = setTimeout(function () { window.location.href = data.url; }, NAV_DELAY_MS);
    }
  }

  // Buttons a reply may carry (a colleague card, the people a name could be). Server-built: label and url.
  function linksHtml(links) {
    if (!Array.isArray(links)) return "";
    return links.slice(0, 5).map(function (l) {
      return '<a class="btn ghost" href="' + esc(l.url) + '">' + esc(l.label) + "</a>";
    }).join("");
  }

  function showAnswerCard(mount, data) {
    clear(mount);
    var card = document.createElement("div");
    card.className = "start-card";
    card.innerHTML =
      '<p class="start-card-msg">' + esc(data.text) + "</p>" +
      '<div class="start-card-actions">' +
      (data.url ? '<a class="btn ghost" href="' + esc(data.url) + '">Open guide →</a>' : "") +
      linksHtml(data.links) +
      FB.replace("Good suggestion", "Good answer") + "</div>";
    mount.appendChild(card);
    wireFeedback(card, data.interaction_id);
  }

  function submitAction(data) {
    if (data.method === "GET") {
      window.location.href = data.url;
      return;
    }
    var f = document.createElement("form");
    f.method = "POST";
    f.action = data.url;
    f.style.display = "none";
    var fields = data.fields || {};
    for (var k in fields) {
      if (!Object.prototype.hasOwnProperty.call(fields, k)) continue;
      var inp = document.createElement("input");
      inp.type = "hidden";
      inp.name = k;
      inp.value = fields[k];
      f.appendChild(inp);
    }
    document.body.appendChild(f);
    f.submit();
  }

  function showActionCard(mount, data) {
    clear(mount);
    var card = document.createElement("div");
    card.className = "start-card";
    card.innerHTML =
      '<p class="start-card-msg">' + esc(data.description) + "</p>" +
      '<div class="start-card-actions">' +
      '<button type="button" class="btn" id="startConfirm">Confirm</button>' +
      '<button type="button" class="btn ghost" id="startCancel">Cancel</button>' +
      FB + "</div>";
    mount.appendChild(card);

    card.querySelector("#startCancel").addEventListener("click", function () {
      mount.innerHTML = "";
    });
    card.querySelector("#startConfirm").addEventListener("click", function () {
      submitAction(data);
    });
    wireFeedback(card, data.interaction_id);
  }

  // Passive telemetry (telemetry.js listens): that someone asked, and how it ended. Never the
  // question itself.
  function signal(stage, kind) {
    try {
      window.dispatchEvent(new CustomEvent("csi:ask", { detail: { stage: stage, kind: kind || null } }));
    } catch (e) { /* telemetry is best-effort */ }
  }

  function ask(raw, mount, opts) {
    opts = opts || {};
    signal("fired");
    if (opts.autoNavigate === undefined) opts.autoNavigate = true;
    var timeoutMs = opts.timeoutMs || 9000;
    var s = stateOf(mount);
    s.last = raw;
    if (opts.statusEl) opts.statusEl.hidden = false;
    var done = function () { if (opts.statusEl) opts.statusEl.hidden = true; };
    var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var to = ctrl ? setTimeout(function () { ctrl.abort(); }, timeoutMs) : null;
    var body = "q=" + encodeURIComponent(raw) +
      "&history=" + encodeURIComponent(JSON.stringify(history));
    fetch("/api/ai/route", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body,
      signal: ctrl ? ctrl.signal : undefined,
    }).then(function (res) {
      if (to) clearTimeout(to);
      if (!res.ok) throw new Error("bad status");
      return res.json();
    }).then(function (data) {
      done();
      if (s.last !== raw) return;                 // a newer query already superseded this one
      pushHistory("user", raw);
      var kind = data && data.kind;
      if (kind === "navigate") {
        showCard(mount, data, raw, opts);
        pushHistory("assistant", "Suggested opening " + data.label + ".");
      } else if (kind === "answer" || kind === "help") {
        showAnswerCard(mount, data);
        pushHistory("assistant", data.text);
      } else if (kind === "action") {
        showActionCard(mount, data);
        pushHistory("assistant", data.description);
      } else {
        signal("fallback");
        if (opts.onFallback) opts.onFallback(raw);
        return;
      }
      signal("answered", kind);
      if (opts.onSettled) opts.onSettled(kind);
    }).catch(function () {
      if (to) clearTimeout(to);
      done();
      if (s.last === raw) {
        signal("fallback");
        if (opts.onFallback) opts.onFallback(raw);
      }
    });
  }

  window.CSSAssistant = { ask: ask, clear: clear };
})();
