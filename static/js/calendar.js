/* Calendar toolbar (Phase 1 of docs/CALENDAR_UX_PLAN.md). Progressive enhancement: the form works
   without it (an Apply button submits it); with it, choosing a scope or a filter applies at once and
   the two menus close when you click elsewhere, press Escape, or pick something. */
(function () {
  "use strict";
  document.documentElement.classList.add("cal-js");
  var form = document.getElementById("cal-f");
  if (form) {
    Array.prototype.forEach.call(form.querySelectorAll(".cal-auto"), function (el) {
      el.addEventListener("change", function () {
        if (typeof form.requestSubmit === "function") form.requestSubmit(); else form.submit();
      });
    });
  }
  // "Swipe sideways" only where the Week / Timeline box really is wider than the screen.
  var scrollers = Array.prototype.slice.call(document.querySelectorAll(".cal-people-week, .cal-timeline"));
  function hints() {
    scrollers.forEach(function (box) {
      var hint = box.previousElementSibling;
      if (hint && hint.classList.contains("cal-scrollhint")) hint.classList.toggle("show", box.scrollWidth > box.clientWidth + 1);
    });
  }
  if (scrollers.length) { hints(); window.addEventListener("resize", hints); }
  var menus = function () { return Array.prototype.slice.call(document.querySelectorAll(".cal-more[open], .cal-fdrop[open]")); };
  document.addEventListener("click", function (ev) {
    menus().forEach(function (m) {
      if (!m.contains(ev.target) || (ev.target.closest && ev.target.closest(".cal-menu-item"))) m.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    menus().forEach(function (m) { m.removeAttribute("open"); var s = m.querySelector("summary"); if (s) s.focus(); });
  });
})();

/* Phase 4 of docs/CALENDAR_UX_PLAN.md: the item sheet, keyboard shortcuts and swipe. Each part works
   alone and only adds to the page: without script an item is an ordinary link, the arrows are
   ordinary links, and nothing here is needed to read or add anything. No HTML is built from a string:
   the item's own page is fetched, its article is taken out of the parsed document and moved in. */
(function () {
  "use strict";
  var ENTRY = /^\/calendar\/entries\/(\d+)\/?$/;
  var sheet = document.getElementById("cal-sheet");

  // ---- the item sheet ------------------------------------------------------
  if (sheet && typeof sheet.showModal === "function") {
    var body = sheet.querySelector("[data-sheet-body]");
    var openLink = sheet.querySelector("[data-sheet-open]");
    var closeBtn = sheet.querySelector("[data-sheet-close]");
    var ticket = 0, pushed = false, byHistory = false;
    var returnFocus = null, releaseFocus = null;

    var withItem = function (id) {
      var u = new URL(location.href);
      if (id) u.searchParams.set("item", id); else u.searchParams.delete("item");
      return u.pathname + u.search + u.hash;
    };

    var show = function (path, push) {
      var m = ENTRY.exec(path);
      if (!m) return false;
      var mine = ++ticket;
      openLink.setAttribute("href", path);
      sheet.querySelector(".cal-sheet-t").textContent = "Calendar item";
      while (body.firstChild) body.removeChild(body.firstChild);
      var notice = document.createElement("p");
      notice.setAttribute("role", "status");
      notice.textContent = "Loading the current calendar item…";
      body.appendChild(notice);
      body.setAttribute("aria-busy", "true");
      if (!sheet.open) {
        returnFocus = document.activeElement; sheet.showModal();
        if (window.OfficeA11y) releaseFocus = OfficeA11y.open(sheet, {initialFocus:closeBtn, returnFocus:returnFocus, onDismiss:closeSheet});
      }
      closeBtn.focus();
      if (push && !pushed) { history.pushState({ sheet: m[1] }, "", withItem(m[1])); pushed = true; }
      fetch(path, { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) throw new Error(String(r.status));
        return r.text();
      }).then(function (html) {
        if (mine !== ticket || !sheet.open) return;                 // a newer tap or dismissal won
        var art = new DOMParser().parseFromString(html, "text/html").querySelector(".cal-detail");
        if (!art) throw new Error("not an item page");
        Array.prototype.forEach.call(art.querySelectorAll("script, iframe, object, embed, link, style"), function (n) { n.remove(); });
        while (body.firstChild) body.removeChild(body.firstChild);
        body.appendChild(document.importNode(art, true));
        openLink.setAttribute("href", path);
        var title = art.querySelector("h1");
        sheet.querySelector(".cal-sheet-t").textContent = title ? title.textContent : "Calendar item";
        body.removeAttribute("aria-busy");
        body.scrollTop = 0;
      }).catch(function () {
        if (mine !== ticket || !sheet.open) return;
        body.removeAttribute("aria-busy");
        while (body.firstChild) body.removeChild(body.firstChild);
        var message = document.createElement("p");
        message.setAttribute("role", "alert");
        message.textContent = "Could not load this item. It may be unavailable or your access may have changed. Nothing was changed. Try again or open the full page.";
        var retry = document.createElement("button");
        retry.type = "button"; retry.className = "cal-btn"; retry.textContent = "Try loading again";
        retry.addEventListener("click", function () { show(path, false); });
        body.appendChild(message); body.appendChild(retry);
      });
      return true;
    };

    document.addEventListener("click", function (ev) {
      if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
      var a = ev.target.closest && ev.target.closest("a[href]");
      if (!a || a.target === "_blank" || a.closest("dialog")) return;
      var u;
      try { u = new URL(a.href, location.href); } catch (e) { return; }
      if (u.origin !== location.origin || !ENTRY.test(u.pathname) || u.search) return;
      ev.preventDefault();
      show(u.pathname, true);
    });

    var closeSheet = function () {
      ticket++;                                                       // drop a fetch still in flight
      if (sheet.open) sheet.close();
    };
    closeBtn.addEventListener("click", closeSheet);
    sheet.addEventListener("click", function (ev) { if (ev.target === sheet) closeSheet(); });   // the backdrop
    sheet.addEventListener("close", function () {
      ticket++;                                                       // native Escape also invalidates pending reads
      body.removeAttribute("aria-busy");
      while (body.firstChild) body.removeChild(body.firstChild);
      if (releaseFocus) { releaseFocus(); releaseFocus = null; }
      else if (returnFocus && returnFocus.isConnected && returnFocus !== document.body) returnFocus.focus();
      else { var fallback = document.querySelector('.cal-add'); if (fallback) fallback.focus(); }
      if (byHistory) { byHistory = false; pushed = false; return; }
      if (pushed) { pushed = false; history.back(); }                // take our own entry back off the history
      else if (new URL(location.href).searchParams.has("item")) history.replaceState(null, "", withItem(""));
    });
    window.addEventListener("popstate", function () {
      var id = new URL(location.href).searchParams.get("item");
      if (id && /^\d+$/.test(id)) { pushed = true; show("/calendar/entries/" + id, false); }
      else if (sheet.open) { byHistory = true; ticket++; sheet.close(); }
    });
    var first = new URL(location.href).searchParams.get("item");        // a shared link opens the sheet
    if (first && /^\d+$/.test(first)) { pushed = false; show("/calendar/entries/" + first, false); }
  }

  // ---- keyboard ------------------------------------------------------------
  document.addEventListener("keydown", function (ev) {
    if (ev.defaultPrevented || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var t = ev.target;
    if (t && (/^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName) || t.isContentEditable)) return;
    if (document.querySelector("dialog[open]")) return;
    var nav = document.querySelectorAll(".cal-nav a");
    var key = ev.key;
    if (key === "ArrowLeft" && nav[0]) nav[0].click();
    else if (key === "ArrowRight" && nav[2]) nav[2].click();
    else if ((key === "t" || key === "T") && nav[1]) nav[1].click();
    else if (key === "a" || key === "A") {
      var quick = document.querySelector(".cal-quick-open"), add = document.querySelector(".cal-add");
      if (quick && !quick.hidden) quick.click(); else if (add) add.click();
    } else if (key === "s" || key === "S") {                          // "/" already opens the app-wide search palette
      var q = document.querySelector(".cal-q");
      if (!q) return;
      q.focus(); q.select();
    } else return;
    ev.preventDefault();                                              // also keeps the "s" out of the box it just focused
  });

  // ---- swipe: left = later, right = earlier (agenda and the phone month only) -----------------
  var sx = 0, sy = 0, t0 = 0, tracking = false;
  var swipeable = function (el) {
    return !!(el.closest && el.closest(".cal-agenda, .cal-mgrid, .cal-empty")) &&
           !(el.closest("input, select, textarea, dialog, .cal-people-week, .cal-timeline"));
  };
  document.addEventListener("touchstart", function (ev) {
    tracking = ev.touches.length === 1 && swipeable(ev.target);
    if (tracking) { sx = ev.touches[0].clientX; sy = ev.touches[0].clientY; t0 = Date.now(); }
  }, { passive: true });
  document.addEventListener("touchend", function (ev) {
    if (!tracking) return;
    tracking = false;
    var p = ev.changedTouches[0], dx = p.clientX - sx, dy = p.clientY - sy;
    if (Date.now() - t0 > 700 || Math.abs(dx) < 70 || Math.abs(dx) < 2 * Math.abs(dy)) return;   // a flick, mostly sideways
    var nav = document.querySelectorAll(".cal-nav a");
    var go = dx < 0 ? nav[2] : nav[0];
    if (go) go.click();
  }, { passive: true });
})();

/* Calendar quick-add (office calendar H2). A progressive enhancement: the page works without it
   (the "+ Add" button and the full form do everything); with it, "Quick add", the day headers and
   an empty day on a person's timeline row open a small sheet that posts to the ordinary add route.
   No HTML is ever built from a string: names and dates go in with textContent / value. */
(function () {
  "use strict";
  var dlg = document.getElementById("cal-quick");
  if (!dlg || typeof dlg.showModal !== "function") return;           // old browser: the buttons stay hidden
  var me = (document.currentScript && document.currentScript.dataset.me) || "";
  var form = dlg.querySelector("form");
  var people = form.querySelector("[data-people]");
  var who = form.querySelector("[data-who]");
  var audience = form.querySelector("[data-audience]");
  var hasOwner = !!form.querySelector("[data-owner]").value;
  var returnFocus = null, releaseFocus = null;
  dlg.addEventListener("close", function () {
    if (releaseFocus) { releaseFocus(); releaseFocus = null; }
    else if (returnFocus && returnFocus.isConnected) returnFocus.focus();
  });

  Array.prototype.forEach.call(document.querySelectorAll("[hidden][data-quick], .cal-tl-plus"), function (b) { b.hidden = false; });

  function setPeople(uid, name) {
    while (people.firstChild) people.removeChild(people.firstChild);
    var ids = [];
    if (uid) ids.push(uid);
    // With no owning section the sheet can only make an item that belongs to someone, so put the
    // person adding it on it (the server needs a "who is this for" anyway).
    if (!hasOwner && me && ids.indexOf(me) < 0) ids.push(me);
    ids.forEach(function (id) {
      var h = document.createElement("input");
      h.type = "hidden"; h.name = "people"; h.value = id;
      people.appendChild(h);
    });
    who.hidden = !(uid && name);
    who.textContent = uid && name ? "For " + name + ". They will see it in their calendar." : "";
    if (uid && audience) audience.value = "people";                 // an item for a person is for that person
    else if (audience && hasOwner) audience.value = "unit";
  }

  function open(date, uid, name) {
    form.reset();
    form.querySelector("[data-start]").value = date || "";
    // Setting .value (or reset()) fires no event, and the date fields wear a display overlay (app.js)
    // that only redraws on "change", so without this it kept showing "Pick a date".
    Array.prototype.forEach.call(form.querySelectorAll("input[type=date]"), function (el) {
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });
    setPeople(uid || "", name || "");
    if (uid && audience) audience.value = "people";
    var more = form.querySelector("[data-more]");
    more.href = "/calendar/new" + (date ? "?day=" + encodeURIComponent(date) : "");
    returnFocus = document.activeElement;
    dlg.showModal();
    var first = form.querySelector("[data-first]");
    if (window.OfficeA11y) releaseFocus = OfficeA11y.open(dlg, {initialFocus:first, returnFocus:returnFocus, onDismiss:function () { dlg.close(); }});
    else if (first) first.focus();
  }

  // "More options…" carries what is already typed into the full form (on a phone the sheet is
  // typed into first, so a bare link would throw that away).
  form.querySelector("[data-more]").addEventListener("click", function () {
    var p = [];
    function add(k, v) { if (v) p.push(encodeURIComponent(k) + "=" + encodeURIComponent(v)); }
    ["title", "kind", "audience", "owner_org_id", "start_date", "end_date", "start_time", "end_time"].forEach(function (n) {
      var el = form.elements[n];
      add(n === "start_date" ? "day" : n, el && el.value);
    });
    Array.prototype.forEach.call(form.querySelectorAll("input[name=people]"), function (el) { add("people", el.value); });
    this.href = "/calendar/new" + (p.length ? "?" + p.join("&") : "");
  });

  document.addEventListener("click", function (ev) {
    var t = ev.target;
    var btn = t.closest && t.closest("[data-quick]");
    if (btn) {
      ev.preventDefault();
      open(btn.dataset.date, btn.dataset.uid, btn.dataset.person);
      return;
    }
    var cell = t.closest && t.closest(".cal-tl-cell[data-date]");
    if (cell && !(t.closest && t.closest("a"))) {
      var row = cell.closest(".cal-tl-row");
      open(cell.dataset.date, row && row.dataset.uid, row && row.dataset.person);
      return;
    }
    if (t === dlg) dlg.close();                                      // a click on the backdrop
    if (t.closest && t.closest("[data-quick-close]")) dlg.close();
  });

  form.querySelector("[data-start]").addEventListener("change", function () {
    var end = form.querySelector("[data-end]");
    if (end.value && end.value < this.value) end.value = "";
  });
})();
