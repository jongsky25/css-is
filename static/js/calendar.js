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
    setPeople(uid || "", name || "");
    if (uid && audience) audience.value = "people";
    var more = form.querySelector("[data-more]");
    more.href = "/calendar/new" + (date ? "?day=" + encodeURIComponent(date) : "");
    dlg.showModal();
    var first = form.querySelector("[data-first]");
    if (first) first.focus();
  }

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
