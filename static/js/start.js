/* /start — the NL landing page (docs/AI_INTEGRATION_PLAN.md Phase 1-2-9).
 *
 * Posts the typed query to POST /api/ai/route. On {"kind":"navigate", ...} it
 * shows a result card (Go/Cancel + 👍/👎) and auto-navigates after ~1.5s. On
 * {"kind":"answer"|"help", ...} (Phase 2, answers-mode only) it shows the
 * server-templated sentence or guide excerpt with the same 👍/👎, no
 * auto-navigate. On {"kind":"action", ...} (Phase 9, assistant mode only) it
 * shows a confirmation card describing exactly what will happen, with a
 * Confirm button that submits the *real* request (a hidden form POST, or a
 * plain navigation for a GET export) to the existing, independently
 * capability-checked + audited endpoint — nothing the model said is ever
 * executed directly, only what the user clicks Confirm on. On anything else
 * — {"kind":"fallback"}, a non-2xx response, or the client-side timeout
 * firing before the server does — it falls back to the same keyword palette
 * engine search.js already attached to this page (window.CSSSearch), so the
 * box always answers something even with AI off/unconfigured/erroring.
 *
 * Assistant mode is also conversational: a short in-memory history of the
 * last few exchanges is replayed to the server on every request so a
 * follow-up like "do it" can resolve against what was just discussed. The
 * history never leaves this tab (no storage) and is capped in length.
 */
(function () {
  "use strict";

  var form = document.getElementById("startForm");
  var input = document.getElementById("startInput");
  var status = document.getElementById("startStatus");
  var results = document.getElementById("startResults");
  if (!form || !input || !results) return;

  var CLIENT_TIMEOUT_MS = 9000;   // server-side timeout is 8s (ai_core.ask default)
  var NAV_DELAY_MS = 1500;
  var HISTORY_MAX = 6;            // exchanges kept (user+assistant pairs), tab-local only
  var lastQuery = "";
  var navTimer = null;
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

  function clearResults() {
    if (navTimer) { clearTimeout(navTimer); navTimer = null; }
    results.innerHTML = "";
  }

  function showFallback(raw) {
    clearResults();
    var hits = (window.CSSSearch ? window.CSSSearch.search(raw) : []).slice(0, 8);
    if (!hits.length) {
      results.innerHTML = '<p class="start-empty">No matching page. Try another word, ' +
        'or <a href="/search?q=' + encodeURIComponent(raw) + '">see the full search</a>.</p>';
      return;
    }
    var html = '<ul class="start-hits">';
    hits.forEach(function (it) {
      html += '<li><a href="' + esc(it.url) + '"><span class="sh-title">' + esc(it.title) +
        '</span><span class="sh-hint">' + esc(it.hint) + '</span></a></li>';
    });
    html += "</ul>";
    results.innerHTML = html;
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

  function showCard(data, raw) {
    clearResults();
    var card = document.createElement("div");
    card.className = "start-card";
    card.innerHTML =
      '<p class="start-card-msg">Taking you to <strong>' + esc(data.label) + '</strong> — ' +
      esc(data.hint) + "</p>" +
      '<div class="start-card-actions">' +
      '<a class="btn" href="' + esc(data.url) + '">Go now</a>' +
      '<button type="button" class="btn ghost" id="startCancel">Cancel</button>' +
      '<span class="start-fb">' +
      '<button type="button" class="fb-btn" data-r="up" aria-label="Good suggestion">👍</button>' +
      '<button type="button" class="fb-btn" data-r="down" aria-label="Not helpful">👎</button>' +
      "</span></div>";
    results.appendChild(card);

    card.querySelector("#startCancel").addEventListener("click", function () {
      if (navTimer) { clearTimeout(navTimer); navTimer = null; }
      showFallback(raw);
    });
    wireFeedback(card, data.interaction_id);
    navTimer = setTimeout(function () { window.location.href = data.url; }, NAV_DELAY_MS);
  }

  function showAnswerCard(data) {
    clearResults();
    var card = document.createElement("div");
    card.className = "start-card";
    card.innerHTML =
      '<p class="start-card-msg">' + esc(data.text) + "</p>" +
      '<div class="start-card-actions">' +
      (data.url ? '<a class="btn ghost" href="' + esc(data.url) + '">Open guide →</a>' : "") +
      '<span class="start-fb">' +
      '<button type="button" class="fb-btn" data-r="up" aria-label="Good answer">👍</button>' +
      '<button type="button" class="fb-btn" data-r="down" aria-label="Not helpful">👎</button>' +
      "</span></div>";
    results.appendChild(card);
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

  function showActionCard(data) {
    clearResults();
    var card = document.createElement("div");
    card.className = "start-card";
    card.innerHTML =
      '<p class="start-card-msg">' + esc(data.description) + "</p>" +
      '<div class="start-card-actions">' +
      '<button type="button" class="btn" id="startConfirm">Confirm</button>' +
      '<button type="button" class="btn ghost" id="startCancel">Cancel</button>' +
      '<span class="start-fb">' +
      '<button type="button" class="fb-btn" data-r="up" aria-label="Good suggestion">👍</button>' +
      '<button type="button" class="fb-btn" data-r="down" aria-label="Not helpful">👎</button>' +
      "</span></div>";
    results.appendChild(card);

    card.querySelector("#startCancel").addEventListener("click", function () {
      results.innerHTML = "";
    });
    card.querySelector("#startConfirm").addEventListener("click", function () {
      submitAction(data);
    });
    wireFeedback(card, data.interaction_id);
  }

  function ask(raw) {
    lastQuery = raw;
    status.hidden = false;
    var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var to = ctrl ? setTimeout(function () { ctrl.abort(); }, CLIENT_TIMEOUT_MS) : null;
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
      status.hidden = true;
      if (lastQuery !== raw) return;              // a newer query already superseded this one
      pushHistory("user", raw);
      if (data && data.kind === "navigate") {
        showCard(data, raw);
        pushHistory("assistant", "Suggested opening " + data.label + ".");
      } else if (data && (data.kind === "answer" || data.kind === "help")) {
        showAnswerCard(data);
        pushHistory("assistant", data.text);
      } else if (data && data.kind === "action") {
        showActionCard(data);
        pushHistory("assistant", data.description);
      } else {
        showFallback(raw);
      }
    }).catch(function () {
      if (to) clearTimeout(to);
      status.hidden = true;
      if (lastQuery === raw) showFallback(raw);
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var raw = input.value.trim();
    if (!raw) return;
    ask(raw);
  });

  var chips = document.querySelectorAll(".start-chip");
  for (var i = 0; i < chips.length; i++) {
    chips[i].addEventListener("click", function (e) {
      input.value = e.currentTarget.dataset.q || "";
      form.dispatchEvent(new Event("submit", { cancelable: true }));
    });
  }
})();
