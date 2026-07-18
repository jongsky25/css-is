/* Search palette — one engine, two mount points.
 *
 *   1. Global command palette: Ctrl/⌘-K (or "/") from any page, plus the
 *      "Search" button in the top nav.
 *   2. The landing-page inline box (any <form data-search>).
 *
 * The index is injected server-side as window.SEARCH_INDEX — it only ever
 * contains destinations the current user may open, so there's no client-side
 * role gate to get wrong. Every result is a real <a>, so middle-click / open-in-
 * new-tab work and there's a no-JS fallback (the form posts to /search?q=).
 *
 * DB-record results (activities, people, comments) are fetched from /api/search
 * after a 200 ms debounce and appended below the page results with no change to
 * the core engine or the result-row rendering contract.
 */
(function () {
  "use strict";

  var INDEX = window.SEARCH_INDEX || [];

  // ---- ranking -------------------------------------------------------------
  function wordStart(hay, term) {
    var i = hay.indexOf(term);
    while (i !== -1) {
      if (i === 0 || hay[i - 1] === " " || hay[i - 1] === "/") return true;
      i = hay.indexOf(term, i + 1);
    }
    return false;
  }

  function score(item, terms, raw) {
    var title = item.title.toLowerCase();
    var hint = (item.hint || "").toLowerCase();
    var kw = (item.kw || "").toLowerCase();
    var section = (item.section || "").toLowerCase();
    var hay = title + " " + hint + " " + kw + " " + section;
    var s = 0;
    for (var i = 0; i < terms.length; i++) {
      var t = terms[i];
      if (hay.indexOf(t) === -1) return -1;          // every term must match somewhere
      if (title === t) s += 100;
      else if (title.indexOf(t) === 0) s += 60;      // title prefix
      else if (wordStart(title, t)) s += 40;         // word start in title
      else if (title.indexOf(t) !== -1) s += 25;     // title substring
      else if (hint.indexOf(t) !== -1) s += 10;      // hint hit
      else s += 4;                                    // keyword-only hit
    }
    if (title.indexOf(raw) === 0) s += 30;           // whole-query prefix bonus
    s -= title.length * 0.05;                         // tie-break: shorter titles win
    return s;
  }

  function search(query) {
    var raw = query.trim().toLowerCase();
    if (!raw) return [];
    var terms = raw.split(/\s+/);
    var hits = [];
    for (var i = 0; i < INDEX.length; i++) {
      var sc = score(INDEX[i], terms, raw);
      if (sc >= 0) hits.push({ item: INDEX[i], sc: sc, ord: i });
    }
    hits.sort(function (a, b) { return b.sc - a.sc || a.ord - b.ord; });
    return hits.map(function (h) { return h.item; });
  }

  // ---- rendering -----------------------------------------------------------
  function esc(s) {
    var n = document.createElement("div");
    n.textContent = s == null ? "" : s;
    return n.innerHTML;
  }

  // Highlight the typed query inside a label (case-insensitive, first hit per term).
  function mark(text, raw) {
    var safe = esc(text);
    if (!raw) return safe;
    var terms = raw.trim().split(/\s+/).filter(Boolean).map(function (t) {
      return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    });
    if (!terms.length) return safe;
    try {
      return safe.replace(new RegExp("(" + terms.join("|") + ")", "ig"),
                          "<mark>$1</mark>");
    } catch (e) { return safe; }
  }

  // Attach the engine to an input + results <ul>. Returns a small controller.
  //   opts.input, opts.results  — elements
  //   opts.showAllOnEmpty       — list the whole index when the box is empty
  //   opts.onPick(item)         — optional; default navigates to item.url
  function attach(opts) {
    var input = opts.input, listEl = opts.results;
    var showAll = !!opts.showAllOnEmpty;
    var idPrefix = (listEl.id || "res") + "-opt-";
    var loadingId = (listEl.id || "res") + "-db-loading";
    var current = [], active = -1;

    // ---- DB async state --------------------------------------------------
    var _dbTimer = null, _dbCtrl = null, _dbQuery = "";
    var _reportedEmpty = {};    // per-page dedup for the csi:search-empty signal

    // Tell telemetry.js a search came up completely empty (page index AND DB
    // records). Fired at most once per term per page load; the listener
    // sanitizes the term before anything leaves the browser.
    function _reportEmpty(raw) {
      if (!raw || _reportedEmpty[raw]) return;
      _reportedEmpty[raw] = true;
      try {
        window.dispatchEvent(new CustomEvent("csi:search-empty", { detail: { term: raw } }));
      } catch (e) { /* telemetry is best-effort */ }
    }

    function _removeLoadingRow() {
      var el = document.getElementById(loadingId);
      if (el) el.parentNode.removeChild(el);
    }

    function _showLoadingRow() {
      _removeLoadingRow();
      var li = document.createElement("li");
      li.id = loadingId;
      li.className = "palette-loading";
      li.setAttribute("aria-hidden", "true");
      li.textContent = "Searching records…";
      listEl.appendChild(li);
    }

    function _appendDBRows(data, raw) {
      _removeLoadingRow();
      if (!data.length) return;
      var startIdx = current.length;
      var lastSection = null;
      var html = "";
      for (var i = 0; i < data.length; i++) {
        var it = data[i];
        if (it.section !== lastSection) {
          html += '<li class="palette-group palette-divider" role="presentation">' +
                  esc(it.section) + "</li>";
          lastSection = it.section;
        }
        var idx = startIdx + i;
        html += '<li id="' + idPrefix + idx + '" role="option" class="palette-item"' +
                ' aria-selected="false">' +
                '<a href="' + esc(it.url) + '" tabindex="-1">' +
                '<span class="pi-title">' + mark(it.title, raw) + "</span>" +
                '<span class="pi-hint">' + mark(it.hint, raw) + "</span>" +
                '<span class="pi-tag">' + esc(it.section) + "</span>" +
                "</a></li>";
      }
      listEl.insertAdjacentHTML("beforeend", html);
      for (var j = 0; j < data.length; j++) current.push(data[j]);
    }

    function _cancelDB() {
      if (_dbTimer) { clearTimeout(_dbTimer); _dbTimer = null; }
      if (_dbCtrl) { try { _dbCtrl.abort(); } catch (e) {} _dbCtrl = null; }
      _removeLoadingRow();
    }

    function _fetchDB(raw) {
      _cancelDB();
      if (!raw || raw.length < 2) return;
      _dbQuery = raw;
      _dbTimer = setTimeout(function () {
        _dbTimer = null;
        _showLoadingRow();
        var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
        _dbCtrl = ctrl;
        fetch("/api/search?q=" + encodeURIComponent(raw),
              ctrl ? { signal: ctrl.signal } : {})
          .then(function (res) {
            if (res.ok && (res.headers.get("content-type") || "").indexOf("json") >= 0)
              return res.json();
            return [];
          })
          .then(function (data) {
            if (_dbQuery !== raw) return;
            _dbCtrl = null;
            _appendDBRows(Array.isArray(data) ? data : [], raw);
            // The debounced DB fetch settling empty on top of zero page hits
            // is the "this search truly found nothing" moment.
            if (current.length === 0) _reportEmpty(raw);
          })
          .catch(function () { _removeLoadingRow(); });
      }, 200);
    }

    // ---- core engine ---------------------------------------------------------

    function go(item) {
      if (!item) return;
      if (opts.onPick) opts.onPick(item);
      else window.location.href = item.url;
    }

    function paint(raw) {
      if (!current.length) {
        // Inline box stays closed until the user types; the palette shows a hint.
        if (!raw && !showAll) { listEl.innerHTML = ""; }
        else {
          listEl.innerHTML = '<li class="palette-empty">' +
            (raw ? "No matching page. Try another word." :
                   "Type to search pages and actions.") + "</li>";
        }
        input.setAttribute("aria-activedescendant", "");
        return;
      }
      var html = "";
      var lastSection = null;
      for (var i = 0; i < current.length; i++) {
        var it = current[i];
        // group header only when listing everything (empty query)
        if (!raw && it.section !== lastSection) {
          html += '<li class="palette-group" role="presentation">' + esc(it.section) + "</li>";
          lastSection = it.section;
        }
        html += '<li id="' + idPrefix + i + '" role="option" class="palette-item' +
                (i === active ? " active" : "") + '" aria-selected="' +
                (i === active) + '">' +
                '<a href="' + esc(it.url) + '" tabindex="-1">' +
                '<span class="pi-title">' + mark(it.title, raw) + "</span>" +
                '<span class="pi-hint">' + mark(it.hint, raw) + "</span>" +
                (raw ? '<span class="pi-tag">' + esc(it.section) + "</span>" : "") +
                "</a></li>";
      }
      listEl.innerHTML = html;
      syncActive();
    }

    function syncActive() {
      var items = listEl.querySelectorAll(".palette-item");
      for (var i = 0; i < items.length; i++) {
        var on = items[i].id === idPrefix + active;
        items[i].classList.toggle("active", on);
        items[i].setAttribute("aria-selected", on);
        if (on) {
          input.setAttribute("aria-activedescendant", items[i].id);
          items[i].scrollIntoView({ block: "nearest" });
        }
      }
      if (active < 0) input.setAttribute("aria-activedescendant", "");
    }

    function render() {
      var raw = input.value.trim();
      _cancelDB();
      current = raw ? search(raw) : (showAll ? INDEX.slice() : []);
      active = current.length ? 0 : -1;
      paint(raw);
      if (raw) _fetchDB(raw);
    }

    function move(delta) {
      if (!current.length) return;
      active = (active + delta + current.length) % current.length;
      syncActive();
    }

    input.addEventListener("input", render);
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") {
        if (active >= 0 && current[active]) { e.preventDefault(); go(current[active]); }
      } else if (e.key === "Escape" && opts.onEscape) {
        opts.onEscape();
      }
    });
    // Mouse hover sets the active row so Enter stays predictable.
    listEl.addEventListener("mousemove", function (e) {
      var li = e.target.closest && e.target.closest(".palette-item");
      if (!li) return;
      var idx = parseInt(li.id.slice(idPrefix.length), 10);
      if (!isNaN(idx) && idx !== active) { active = idx; syncActive(); }
    });

    return { render: render, focus: function () { input.focus(); } };
  }

  // ---- global command palette (Ctrl/⌘-K) -----------------------------------
  function initPalette() {
    var backdrop = document.getElementById("cmdk");
    var input = document.getElementById("cmdkInput");
    var results = document.getElementById("cmdkResults");
    if (!backdrop || !input || !results) return;

    var ctrl = attach({
      input: input, results: results, showAllOnEmpty: true,
      onEscape: close
    });

    function open() {
      if (!backdrop.hidden) return;
      backdrop.hidden = false;
      document.body.classList.add("cmdk-open");
      input.value = "";
      ctrl.render();
      input.focus();
    }
    function close() {
      backdrop.hidden = true;
      document.body.classList.remove("cmdk-open");
    }

    backdrop.addEventListener("mousedown", function (e) {
      if (e.target === backdrop) close();          // click outside the panel
    });

    var btn = document.getElementById("navSearchBtn");
    if (btn) btn.addEventListener("click", open);

    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        backdrop.hidden ? open() : close();
        return;
      }
      if (e.key === "Escape" && !backdrop.hidden) { close(); return; }
      // "/" opens the palette unless the user is typing into a field.
      if (e.key === "/" && backdrop.hidden) {
        var t = e.target, tag = t && t.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" ||
            (t && t.isContentEditable)) return;
        e.preventDefault();
        open();
      }
    });
  }

  // ---- landing-page inline box(es) -----------------------------------------
  function initInline() {
    var forms = document.querySelectorAll("form[data-search]");
    for (var i = 0; i < forms.length; i++) {
      (function (form) {
        var input = form.querySelector(".gsearch-input");
        var results = form.querySelector(".gsearch-results");
        if (!input || !results) return;
        var ctrl = attach({ input: input, results: results, showAllOnEmpty: false });
        form.classList.add("js");                   // lets CSS reveal the live list
        // Enter is handled by the engine (opens the active row); stop the GET
        // fallback from firing when JS is live.
        form.addEventListener("submit", function (e) { e.preventDefault(); });
        input.addEventListener("focus", ctrl.render);
      })(forms[i]);
    }
  }

  function init() { initPalette(); initInline(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }

  window.CSSSearch = { search: search, attach: attach, index: INDEX };
})();
