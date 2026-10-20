/* Spot Feedback — pick an element on the page, then leave a comment.
   Vanilla, no deps. Pairs with the #sfBtn button and the .sf-* styles in app.css.
   Capture is element-pick only (D4=A): we record the element's CSS selector +
   bounding box + page URL + viewport, never a screenshot. */
(function () {
  "use strict";
  var btn = document.getElementById("sfBtn");
  if (!btn) return;

  var picking = false;
  var hl = null;        // floating highlight overlay
  var modalEl = null;   // open modal, if any

  // --- a stable-ish CSS selector for the picked element -----------------------
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el.id) return "#" + cssEscape(el.id);
    var parts = [];
    while (el && el.nodeType === 1 && parts.length < 6 && el.nodeName !== "BODY") {
      var sel = el.nodeName.toLowerCase();
      if (el.id) { parts.unshift("#" + cssEscape(el.id)); break; }
      var parent = el.parentNode;
      if (parent && parent.children) {
        var same = Array.prototype.filter.call(parent.children,
          function (c) { return c.nodeName === el.nodeName; });
        if (same.length > 1) sel += ":nth-of-type(" + (same.indexOf(el) + 1) + ")";
      }
      parts.unshift(sel);
      el = el.parentElement;
    }
    return parts.join(" > ");
  }
  function cssEscape(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/[^\w-]/g, "\\$&");
  }

  function isOurs(el) {
    return el && el.closest && el.closest("#sfBtn, .sf-backdrop, .sf-hl, .sf-toast");
  }

  // --- pick mode --------------------------------------------------------------
  function enterPick() {
    if (picking) return;
    picking = true;
    document.body.classList.add("sf-picking");
    hl = document.createElement("div");
    hl.className = "sf-hl";
    document.body.appendChild(hl);
    document.addEventListener("mousemove", onMove, true);
    document.addEventListener("click", onPick, true);
    document.addEventListener("keydown", onEsc, true);
    toast("Click the spot you want to comment on — Esc to cancel.", true);
  }
  function exitPick() {
    picking = false;
    document.body.classList.remove("sf-picking");
    if (hl) { hl.remove(); hl = null; }
    document.removeEventListener("mousemove", onMove, true);
    document.removeEventListener("click", onPick, true);
    document.removeEventListener("keydown", onEsc, true);
    clearToast();
  }
  function onMove(e) {
    var el = e.target;
    if (!hl || isOurs(el)) { if (hl) hl.style.display = "none"; return; }
    var r = el.getBoundingClientRect();
    hl.style.display = "block";
    hl.style.top = r.top + "px"; hl.style.left = r.left + "px";
    hl.style.width = r.width + "px"; hl.style.height = r.height + "px";
  }
  function onEsc(e) { if (e.key === "Escape") { exitPick(); } }
  function onPick(e) {
    if (isOurs(e.target)) return;            // let our own UI work normally
    e.preventDefault(); e.stopPropagation();
    var el = e.target, r = el.getBoundingClientRect();
    var region = {
      rect: { x: Math.round(r.left), y: Math.round(r.top),
              w: Math.round(r.width), h: Math.round(r.height) },
      viewport: { w: window.innerWidth, h: window.innerHeight,
                  scrollX: Math.round(window.scrollX), scrollY: Math.round(window.scrollY) }
    };
    var selector = cssPath(el);
    var label = el.nodeName.toLowerCase() +
      (el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/)[0] : "");
    exitPick();
    openModal(selector, region, label);
  }

  // --- comment modal ----------------------------------------------------------
  function openModal(selector, region, label) {
    closeModal();
    var back = document.createElement("div");
    back.className = "sf-backdrop";
    back.innerHTML =
      '<div class="sf-modal" role="dialog" aria-modal="true" aria-label="Send feedback">' +
        '<h2>Send feedback</h2>' +
        '<p class="sf-target">About: <code></code></p>' +
        '<textarea class="sf-text" rows="5" maxlength="4000" ' +
          'placeholder="What\'s off here? What would make it better?"></textarea>' +
        '<p class="sf-err" hidden></p>' +
        '<div class="sf-actions">' +
          '<button type="button" class="sf-cancel">Cancel</button>' +
          '<button type="button" class="sf-send">Send feedback</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(back);
    modalEl = back;
    back.querySelector(".sf-target code").textContent = label || selector || "this page";
    var ta = back.querySelector(".sf-text");
    var err = back.querySelector(".sf-err");
    var send = back.querySelector(".sf-send");
    setTimeout(function () { ta.focus(); }, 30);

    back.addEventListener("click", function (e) { if (e.target === back) closeModal(); });
    back.querySelector(".sf-cancel").addEventListener("click", closeModal);
    back.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });

    send.addEventListener("click", function () {
      var msg = ta.value.trim();
      if (!msg) { ta.focus(); return; }
      send.disabled = true; err.hidden = true;
      var body = new URLSearchParams();
      body.append("message", msg);
      body.append("page_url", location.href);
      body.append("element_selector", selector || "");
      body.append("region_json", JSON.stringify(region));
      var tries = 0;
      (function attempt() {
        fetch("/feedback", {
          method: "POST", credentials: "same-origin",
          headers: { "X-Requested-With": "fetch",
                     "Content-Type": "application/x-www-form-urlencoded" },
          body: body.toString()
        }).then(function (r) {
          if (r.status === 204) { closeModal(); toast("Thanks — your feedback was sent. 🙏"); return; }
          if (r.status >= 500 && tries++ < 1) { setTimeout(attempt, 1500); return; }
          if (r.status === 403) {
            r.text().then(function (t) {
              showErr(err, /could not be verified/i.test(t)
                ? "Couldn’t verify the request — reload the page and try again. Your message is kept."
                : "Feedback is currently turned off.");
              send.disabled = false;
            }, function () { showErr(err, "Feedback is currently turned off."); send.disabled = false; });
          } else if (r.status === 401) { showErr(err, "You were signed out — sign in again, then resend. Your message is kept."); send.disabled = false; }
          else { showErr(err, "Couldn’t send (code " + r.status + ") — please try again. Your message is kept."); send.disabled = false; }
        }).catch(function () {
          if (tries++ < 1) { setTimeout(attempt, 1500); return; }
          showErr(err, "Couldn’t send — check your connection and try again. Your message is kept."); send.disabled = false;
        });
      })();
    });
  }
  function closeModal() { if (modalEl) { modalEl.remove(); modalEl = null; } }
  function showErr(el, text) { el.textContent = text; el.hidden = false; }

  // --- transient toast --------------------------------------------------------
  var toastEl = null, toastTimer = null;
  function toast(text, sticky) {
    clearToast();
    toastEl = document.createElement("div");
    toastEl.className = "sf-toast";
    toastEl.textContent = text;
    document.body.appendChild(toastEl);
    if (!sticky) toastTimer = setTimeout(clearToast, 3200);
  }
  function clearToast() {
    if (toastTimer) { clearTimeout(toastTimer); toastTimer = null; }
    if (toastEl) { toastEl.remove(); toastEl = null; }
  }

  btn.addEventListener("click", enterPick);
})();
