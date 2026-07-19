/* /reports/activities/<id> — "AI summary" (docs/AI_INTEGRATION_PLAN.md Phase 4).
 *
 * "Re-analyze with AI" is a plain form POST (full-page reload, like the other
 * activity-management forms on this page) — no JS needed there. This file
 * only wires the AJAX "AI summary" button: POST /reports/activities/<id>/
 * ai-summary, render up to 3 bullets on {"ok": true, "bullets": [...]}, or a
 * quiet notice on {"ok": false} / a non-2xx response (AI off, unconfigured,
 * budget/cooldown, or no comments) — the page never shows a raw error.
 */
(function () {
  "use strict";

  var btn = document.getElementById("aiSummaryBtn");
  var status = document.getElementById("aiSummaryStatus");
  var result = document.getElementById("aiSummaryResult");
  if (!btn || !result) return;

  function esc(s) {
    var n = document.createElement("div");
    n.textContent = s == null ? "" : s;
    return n.innerHTML;
  }

  function showBullets(bullets) {
    var html = '<div class="ai-summary-panel"><ul>';
    bullets.forEach(function (b) { html += "<li>" + esc(b) + "</li>"; });
    html += "</ul></div>";
    result.innerHTML = html;
  }

  function showUnavailable() {
    result.innerHTML = '<p class="hint">AI summary isn’t available right now ' +
      "(off, unconfigured, no comments yet, or the daily limit has been reached).</p>";
  }

  btn.addEventListener("click", function () {
    btn.disabled = true;
    if (status) status.hidden = false;
    result.innerHTML = "";
    fetch("/reports/activities/" + encodeURIComponent(btn.dataset.event) + "/ai-summary", {
      method: "POST",
    }).then(function (res) {
      if (!res.ok) throw new Error("bad status");
      return res.json();
    }).then(function (data) {
      if (status) status.hidden = true;
      btn.disabled = false;
      if (data && data.ok && data.bullets && data.bullets.length) showBullets(data.bullets);
      else showUnavailable();
    }).catch(function () {
      if (status) status.hidden = true;
      btn.disabled = false;
      showUnavailable();
    });
  });
})();
