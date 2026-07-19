/* /admin/ux-insights — "Analyze now" (docs/AI_INTEGRATION_PLAN.md Phase 3).
 *
 * Posts to POST /admin/ux-insights/analyze. On {"ok": true, ...} it renders
 * the analysis text in-page with the same 👍/👎 feedback chips /start uses
 * (posted to the existing /api/ai/feedback endpoint via sendBeacon). On
 * {"ok": false} or a non-2xx response — AI off, unconfigured, budget/cooldown,
 * or any other AIError — it shows a notice pointing back at the download
 * link, so the button never leaves the page looking broken.
 */
(function () {
  "use strict";

  var btn = document.getElementById("analyzeBtn");
  var status = document.getElementById("analyzeStatus");
  var result = document.getElementById("analyzeResult");
  if (!btn || !result) return;

  function esc(s) {
    var n = document.createElement("div");
    n.textContent = s == null ? "" : s;
    return n.innerHTML;
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

  function showResult(data) {
    var card = document.createElement("div");
    card.innerHTML =
      '<div class="analyze-result">' + esc(data.text) + "</div>" +
      '<div class="analyze-actions"><span class="analyze-fb">' +
      '<button type="button" class="fb-btn" data-r="up" aria-label="Good analysis">👍</button>' +
      '<button type="button" class="fb-btn" data-r="down" aria-label="Not helpful">👎</button>' +
      "</span></div>";
    result.innerHTML = "";
    result.appendChild(card);

    var fbBtns = card.querySelectorAll(".fb-btn");
    for (var i = 0; i < fbBtns.length; i++) {
      fbBtns[i].addEventListener("click", function (e) {
        var b = e.currentTarget;
        sendFeedback(data.interaction_id, b.dataset.r);
        for (var j = 0; j < fbBtns.length; j++) fbBtns[j].disabled = true;
        b.classList.add("fb-sent");
      });
    }
  }

  function showUnavailable() {
    result.innerHTML = '<p class="analyze-status">AI analysis isn’t available right now ' +
      "(off, unconfigured, or the daily limit has been reached) — use the download link " +
      "above and paste the file into an AI assistant instead.</p>";
  }

  btn.addEventListener("click", function () {
    btn.disabled = true;
    status.hidden = false;
    result.innerHTML = "";
    fetch("/admin/ux-insights/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "days=" + encodeURIComponent(btn.dataset.days || ""),
    }).then(function (res) {
      if (!res.ok) throw new Error("bad status");
      return res.json();
    }).then(function (data) {
      status.hidden = true;
      btn.disabled = false;
      if (data && data.ok) showResult(data);
      else showUnavailable();
    }).catch(function () {
      status.hidden = true;
      btn.disabled = false;
      showUnavailable();
    });
  });
})();
