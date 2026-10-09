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
 * On an unscoped box (the home box and the palette) a question-like query also
 * gets a first "Ask" row; choosing it hands the query to window.CSSAssistant
 * (assistant.js) and shows the answer card inside the dropdown, above the
 * normal results, which stay clickable underneath.
 *
 * DB-record results (activities and people) are fetched from /api/search
 * after a 200 ms debounce and appended below the page results with no change to
 * the core engine or the result-row rendering contract.
 */
(function () {
  "use strict";

  var INDEX = window.SEARCH_INDEX || [];
  var openPalette = function () {};      // set by initPalette once the overlay exists

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

  // scope "all" (or none) ranks the whole index; any other scope ranks only the
  // entries whose `mod` matches (e.g. the /css box passes "css").
  function search(query, scope) {
    var raw = query.trim().toLowerCase();
    if (!raw) return [];
    var terms = raw.split(/\s+/);
    var hits = [];
    for (var i = 0; i < INDEX.length; i++) {
      if (scope && scope !== "all" && INDEX[i].mod !== scope) continue;
      var sc = score(INDEX[i], terms, raw);
      if (sc >= 0) hits.push({ item: INDEX[i], sc: sc, ord: i });
    }
    hits.sort(function (a, b) { return b.sc - a.sc || a.ord - b.ord; });
    return hits.map(function (h) { return h.item; });
  }

  // ---- "does this read like a question?" -------------------------------------
  // Ends in "?", starts with a question word (English or Tagalog), or is four
  // words or more. Cheap and deliberately generous: the Ask row is only an offer.
  var QUESTION_WORDS = ["who", "what", "when", "where", "how", "is", "am", "do", "does", "can",
                        "sino", "ano", "kailan", "saan", "ilan", "may"];
  function looksLikeQuestion(q) {
    var t = (q || "").trim().toLowerCase();
    if (!t) return false;
    if (t.charAt(t.length - 1) === "?") return true;
    var words = t.split(/\s+/);
    if (QUESTION_WORDS.indexOf(words[0].replace(/[^a-z]/g, "")) !== -1) return true;
    return words.length >= 4;
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
  //   opts.scope                — "all" (default) or a module such as "css"; a scoped
  //                               box ends with a "Search everything" row
  function attach(opts) {
    var input = opts.input, listEl = opts.results;
    var scope = opts.scope && opts.scope !== "all" ? opts.scope : "all";
    var showAll = !!opts.showAllOnEmpty;
    var idPrefix = (listEl.id || "res") + "-opt-";
    var loadingId = (listEl.id || "res") + "-db-loading";
    var current = [], active = -1;

    // ---- DB async state --------------------------------------------------
    var _dbTimer = null, _dbCtrl = null, _dbQuery = "";
    var _reportedEmpty = {};    // per-page dedup for the csi:search-empty signal
    var _reportedSearch = {};   // ...and for csi:search (every settled search)

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

    // The scoped box's way out: always the last row, whatever has loaded so far.
    function _removeExitRow() {
      var el = listEl.querySelector(".palette-exit");
      if (el) el.parentNode.removeChild(el);
      if (current.length && current[current.length - 1].exit) current.pop();
    }

    function _addExitRow(raw) {
      _removeExitRow();
      if (scope === "all" || !raw) return;
      var item = { exit: true, title: "Search everything for \u201c" + raw + "\u201d \u2192",
                   url: "#", section: "" };
      var idx = current.length;
      var empty = listEl.querySelector(".palette-empty");
      if (empty) empty.parentNode.removeChild(empty);
      listEl.insertAdjacentHTML("beforeend",
        '<li id="' + idPrefix + idx + '" role="option" class="palette-item palette-exit"' +
        ' aria-selected="false"><a href="#" tabindex="-1" data-exit>' +
        '<span class="pi-title">' + esc(item.title) + "</span></a></li>");
      current.push(item);
      if (active < 0) { active = idx; syncActive(); }
    }

    function _appendDBRows(data, raw) {
      _removeLoadingRow();
      if (!data.length) { _addExitRow(raw); return; }
      _removeExitRow();
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
      _addExitRow(raw);
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
        fetch("/api/search?q=" + encodeURIComponent(raw) +
              (scope === "all" ? "" : "&scope=" + encodeURIComponent(scope)),
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
            var real = current.filter(function (c) { return !c.exit && !c.ask; }).length;
            if (real === 0) _reportEmpty(raw);
            // Every settled search (page hits + DB rows), once per term, so
            // telemetry can give an empty RATE rather than just a count.
            if (!_reportedSearch[raw]) {
              _reportedSearch[raw] = true;
              try {
                window.dispatchEvent(new CustomEvent("csi:search", { detail: {
                  hits: real } }));
              } catch (e) { /* telemetry is best-effort */ }
            }
          })
          .catch(function () { _removeLoadingRow(); });
      }, 200);
    }

    // ---- core engine ---------------------------------------------------------

    function go(item) {
      if (!item) return;
      if (item.exit) { openPalette(input.value.trim()); return; }
      if (item.ask) { askAssistant(item); return; }
      if (opts.onPick) opts.onPick(item);
      else window.location.href = item.url;
    }

    // Choosing the Ask row: the answer card goes in a box at the TOP of the list, the normal
    // results stay underneath. On a fallback (AI off and no rule matched, or an error) the row
    // and the box disappear and the page/record results are all that is left.
    function askAssistant(item) {
      var raw = input.value.trim();
      if (!raw || !window.CSSAssistant) return;
      var box = listEl.querySelector(".palette-ask-answer");
      if (!box) {
        box = document.createElement("li");
        box.className = "palette-ask-answer";
        box.setAttribute("role", "presentation");
        box.setAttribute("aria-live", "polite");
        listEl.insertBefore(box, listEl.firstChild);
      }
      var row = listEl.querySelector(".palette-ask");
      if (row) row.classList.add("asking");
      // The Ask row has done its job (answered, or nothing to say): retire it so Enter and the
      // arrow keys go back to the normal results.
      var retire = function () {
        item.dead = true;
        if (row) row.hidden = true;
        if (current[active] && current[active].dead) {
          active = -1;
          for (var i = 0; i < current.length; i++) if (!current[i].dead) { active = i; break; }
          syncActive();
        }
      };
      window.CSSAssistant.ask(raw, box, {
        autoNavigate: false, timeoutMs: 9000,
        onFallback: function () {
          window.CSSAssistant.clear(box);
          if (box.parentNode) box.parentNode.removeChild(box);
          retire();
        },
        onSettled: retire
      });
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
        if (it.ask) {
          html += '<li id="' + idPrefix + i + '" role="option" class="palette-item palette-ask' +
                  (i === active ? " active" : "") + '" aria-selected="' + (i === active) + '">' +
                  '<a href="#" tabindex="-1" data-ask><span class="pi-title">' + esc(it.title) +
                  "</span></a></li>";
          continue;
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
      current = raw ? search(raw, scope) : (showAll ? INDEX.slice() : []);
      if (raw && scope === "all" && window.CSSAssistant && looksLikeQuestion(raw)) {
        current.unshift({ ask: true, title: "\u2728 Ask: \u201c" + raw + "\u201d", url: "#", section: "" });
      }
      active = current.length ? 0 : -1;
      paint(raw);
      _addExitRow(raw);
      if (raw) _fetchDB(raw);
    }

    function move(delta) {
      if (!current.length) return;
      for (var n = 0; n < current.length; n++) {         // skip rows that have been dropped
        active = (active + delta + current.length) % current.length;
        if (!current[active].dead) break;
      }
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
    listEl.addEventListener("click", function (e) {
      var ask = e.target.closest && e.target.closest("a[data-ask]");
      if (ask) {
        e.preventDefault();
        for (var i = 0; i < current.length; i++) if (current[i].ask) { go(current[i]); break; }
        return;
      }
      var a = e.target.closest && e.target.closest("a[data-exit]");
      if (!a) return;
      e.preventDefault();
      go({ exit: true });
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

    function open(q) {
      var text = typeof q === "string" ? q : "";
      if (!backdrop.hidden) { if (!text) return; }
      backdrop.hidden = false;
      document.body.classList.add("cmdk-open");
      input.value = text;
      ctrl.render();
      input.focus();
    }
    openPalette = open;
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
        var ctrl = attach({ input: input, results: results, showAllOnEmpty: false,
                           scope: form.dataset.scope || "all" });
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

  window.CSSSearch = { search: search, attach: attach, index: INDEX, looksLikeQuestion: looksLikeQuestion,
                       openPalette: function (q) { openPalette(q); } };
})();
