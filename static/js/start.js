/* /start — the NL landing page (docs/AI_INTEGRATION_PLAN.md Phase 1-2-9).
 *
 * A thin caller of window.CSSAssistant (assistant.js), which owns the
 * /api/ai/route call, the answer / navigate / action cards and the 👍/👎
 * feedback. This page supplies what "no answer" looks like: on a fallback
 * reply, a non-2xx response, or the client-side timeout it shows the same
 * keyword palette engine search.js attached to this page (window.CSSSearch),
 * so the box always answers something even with AI off/unconfigured/erroring.
 */
(function () {
  "use strict";

  var form = document.getElementById("startForm");
  var input = document.getElementById("startInput");
  var status = document.getElementById("startStatus");
  var results = document.getElementById("startResults");
  if (!form || !input || !results || !window.CSSAssistant) return;

  // Server-side timeout is 8s per model call (ai_core.ask default). The
  // "maximize" broader lookups make a SECOND fact-selection call after the router, so
  // that page gets a longer client budget before it degrades to the keyword
  // palette; every other mode keeps the snappy 9s. Either way a timeout just
  // shows the palette — never an error.
  var CLIENT_TIMEOUT_MS =
    (form.getAttribute("data-answer-engine") === "maximize") ? 15000 : 9000;

  function esc(s) {
    var n = document.createElement("div");
    n.textContent = s == null ? "" : s;
    return n.innerHTML;
  }

  function showFallback(raw) {
    window.CSSAssistant.clear(results);
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

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var raw = input.value.trim();
    if (!raw) return;
    window.CSSAssistant.ask(raw, results, {
      statusEl: status, timeoutMs: CLIENT_TIMEOUT_MS, autoNavigate: true,
      onFallback: showFallback,
    });
  });

  var chips = document.querySelectorAll(".start-chip");
  for (var i = 0; i < chips.length; i++) {
    chips[i].addEventListener("click", function (e) {
      input.value = e.currentTarget.dataset.q || "";
      form.dispatchEvent(new Event("submit", { cancelable: true }));
    });
  }
})();
