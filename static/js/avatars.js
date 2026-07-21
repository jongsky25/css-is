/* Avatar companions — the behavior engine behind templates/_avatars.html.
 *
 * What lives here (all first-party, offline-safe, no dependencies):
 *  - the delegated tap handler (happy bounce + sparkle + name bubble) that used
 *    to be inline in avatar_defs();
 *  - the IDLE PERSONALITY loop: every visible companion periodically performs a
 *    random behavior from its species' repertoire by toggling an av-do-* class
 *    (the animations themselves are CSS keyframes in avatar_defs());
 *  - the ROAMING engine for the two species that travel (bat flies, fish swims
 *    a lazy figure-eight) by easing the svg's .avmove group between waypoints;
 *  - the OWL's pointer-follow (its facial disc turns toward the cursor);
 *  - CARE actions: the water/feed button plays the droplet/treat animation and
 *    POSTs /avatar/care so the mood survives reloads (offline failures are
 *    swallowed — the animation still played, the mood syncs next load);
 *  - DRAG for [data-drag] companions inside a .av-play area, position kept in
 *    localStorage; arrow keys nudge when the companion is focused.
 *
 * Every motion source checks prefers-reduced-motion (live, via matchMedia
 * change) and the page's visibility, so a background tab spends nothing.
 */
(function () {
  "use strict";

  var mq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  function still() { return !!(mq && mq.matches); }

  /* ---- species repertoires: [class, how long the animation runs (ms)] ---- */
  var BEHAVIORS = {
    plant:     [["av-do-stretch", 1400]],
    cactus:    [["av-do-stretch", 1400]],
    bonsai:    [["av-do-stretch", 1400]],
    sunflower: [["av-do-bloom", 3200], ["av-do-stretch", 1400]],
    fern:      [["av-do-ripple", 2000]],
    mushroom:  [["av-do-wobble", 1100], ["av-do-spore", 1600], ["av-do-blink", 500]],
    succulent: [["av-do-plump", 1200]],
    cat:       [["av-do-blink", 500], ["av-do-ear", 800], ["av-do-wag", 1100],
                ["av-do-stretch", 1400], ["av-do-tilt", 1800]],
    bird:      [["av-do-blink", 500], ["av-do-hop", 900], ["av-do-flap", 1200], ["av-do-tilt", 1800]],
    turtle:    [["av-do-blink", 600], ["av-do-hide", 2000], ["av-do-stretch", 1500]],
    dog:       [["av-do-wag", 1100], ["av-do-wag", 1100], ["av-do-blink", 500],
                ["av-do-hop", 900], ["av-do-tilt", 1800], ["av-do-ear", 800]],
    rabbit:    [["av-do-ear", 800], ["av-do-ear2", 900], ["av-do-blink", 500],
                ["av-do-hop", 900], ["av-do-peek", 1700]],
    fish:      [["av-do-bubbles", 1800], ["av-do-fin", 900], ["av-do-blink", 600]],
    owl:       [["av-do-slowblink", 1300], ["av-do-turn", 2600], ["av-do-flap", 1200]],
    bat:       [["av-do-flap", 1200], ["av-do-blink", 500], ["av-do-ear", 800]]
  };
  var ALL_DO = ["av-do-blink", "av-do-slowblink", "av-do-ear", "av-do-ear2", "av-do-wag",
                "av-do-hop", "av-do-tilt", "av-do-stretch", "av-do-flap", "av-do-peek",
                "av-do-hide", "av-do-turn", "av-do-bubbles", "av-do-fin", "av-do-ripple",
                "av-do-wobble", "av-do-spore", "av-do-plump", "av-do-bloom"];

  /* How often a companion does something: the succulent is famously unbothered,
   * a droopy (neglected) pet moves noticeably less, a happy one a bit more. */
  function idleDelay(w) {
    var base = w.dataset.kind === "succulent" ? 15000 + Math.random() * 15000
                                              : 3500 + Math.random() * 6000;
    var mood = w.dataset.mood;
    if (mood === "droopy") base *= 1.9;
    if (mood === "happy") base *= 0.75;
    return base;
  }

  function startIdle(w) {
    var reps = BEHAVIORS[w.dataset.kind];
    if (!reps || !reps.length) return;
    (function tick() {
      w._avIdleT = setTimeout(function () {
        if (!w.isConnected) return;                    // removed from the page
        if (still() || document.hidden) { tick(); return; }
        var pick = reps[Math.floor(Math.random() * reps.length)];
        w.classList.remove.apply(w.classList, ALL_DO); // clear any leftover
        void w.offsetWidth;                            // restart CSS animations
        w.classList.add(pick[0]);
        clearTimeout(w._avDoT);
        w._avDoT = setTimeout(function () { w.classList.remove(pick[0]); }, pick[1] + 80);
        tick();
      }, idleDelay(w));
    })();
  }

  /* ---- roaming: the bat flies, the fish swims -------------------------- */
  function startRoam(w) {
    var kind = w.dataset.kind;
    if (kind !== "bat" && kind !== "fish") return;
    var move = w.querySelector(".avmove");
    if (!move) return;
    move.style.transformOrigin = "50% 50%";
    /* the fish repeats a lazy figure-eight; the bat picks random waypoints */
    var fig8 = [[16, -5, -1], [0, -10, -1], [-16, -5, 1], [0, 0, 1]];
    var leg = 0;
    (function hop() {
      w._avRoamT = setTimeout(function () {
        if (!w.isConnected) return;
        if (still() || document.hidden) { hop(); return; }
        var x, y, flip;
        if (kind === "fish") {
          var p = fig8[leg++ % fig8.length];
          x = p[0]; y = p[1]; flip = p[2];
        } else {
          x = Math.round((Math.random() - 0.5) * 44);
          y = Math.round((Math.random() - 0.7) * 26);   // bats prefer up
          flip = x < 0 ? -1 : 1;
          w.classList.add("av-do-flap");                // flap through the leg
          clearTimeout(w._avDoT);
          w._avDoT = setTimeout(function () { w.classList.remove("av-do-flap"); }, 1300);
        }
        move.style.transition = "transform 2.4s ease-in-out";
        move.style.transform = "translate(" + x + "px," + y + "px) scale(" + flip + ",1)";
        hop();
      }, kind === "fish" ? 2600 : 2600 + Math.random() * 2600);
    })();
  }

  /* ---- owl: the facial disc follows the pointer ------------------------- */
  var owlRaf = null;
  document.addEventListener("pointermove", function (e) {
    if (still() || owlRaf) return;
    owlRaf = requestAnimationFrame(function () {
      owlRaf = null;
      var heads = document.querySelectorAll('.avwrap[data-kind="owl"] .av-head');
      for (var i = 0; i < heads.length; i++) {
        var h = heads[i], r = h.getBoundingClientRect();
        if (!r.width) continue;
        var tilt = Math.max(-12, Math.min(12, (e.clientX - (r.left + r.width / 2)) / 16));
        h.style.transform = "rotate(" + tilt.toFixed(1) + "deg)";
        h.style.transition = "transform .5s ease";
        clearTimeout(h._avBackT);
        h._avBackT = setTimeout((function (hh) {
          return function () { hh.style.transform = ""; };
        })(h), 2000);
      }
    });
  }, { passive: true });

  /* ---- tap: happy bounce + sparkle + name bubble ------------------------ */
  document.addEventListener("click", function (e) {
    if (e.target.closest(".av-care-btn")) return;      // care has its own handler
    var w = e.target.closest(".avwrap[data-interactive]");
    if (!w || w._avDragMoved) return;                  // a drag is not a tap
    w.classList.remove("happy");
    void w.offsetWidth;                                // force reflow => restart
    w.classList.add("happy");
    var b = w.querySelector(".av-bubble");
    if (b) {
      b.classList.add("show");
      clearTimeout(w._avBubT);
      w._avBubT = setTimeout(function () { b.classList.remove("show"); }, 1400);
    }
  });
  document.addEventListener("animationend", function (e) {
    if (e.animationName === "av-bounce") {
      var w = e.target.closest(".avwrap");
      if (w) w.classList.remove("happy");
    }
  });

  /* ---- care: water / feed ----------------------------------------------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".av-care-btn");
    if (!btn) return;
    var w = btn.closest(".avwrap");
    if (!w) return;
    var action = btn.getAttribute("data-care-action") || "";
    var cls = action === "water" ? "av-caring-water" : "av-caring-feed";
    w.classList.remove("av-caring-water", "av-caring-feed");
    void w.offsetWidth;
    w.classList.add(cls);
    clearTimeout(w._avCareT);
    w._avCareT = setTimeout(function () { w.classList.remove(cls); }, 3600);
    try {
      fetch("/avatar/care", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "action=" + encodeURIComponent(action)
      }).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (res) { if (res && res.ok && res.mood) w.dataset.mood = res.mood; })
        .catch(function () {});                        // offline: cosmetic anyway
    } catch (err) { /* fetch unavailable: animation already played */ }
  });

  /* ---- drag around the .av-play area ------------------------------------ */
  var POS_KEY = "css-av-pos";
  function initDrag(w) {
    if (!w.hasAttribute("data-drag") || w._avDrag) return;
    w._avDrag = true;
    var pos = { x: 0, y: 0 };
    function apply() { w.style.transform = "translate(" + pos.x + "px," + pos.y + "px)"; }
    function clampToPlay() {
      var play = w.closest(".av-play");
      if (!play) return;
      pos.x = Math.max(-w.offsetLeft, Math.min(play.clientWidth - w.offsetLeft - w.offsetWidth, pos.x));
      pos.y = Math.max(-w.offsetTop, Math.min(play.clientHeight - w.offsetTop - w.offsetHeight, pos.y));
    }
    function save() {
      try { localStorage.setItem(POS_KEY, JSON.stringify(pos)); } catch (e) {}
    }
    try {
      var saved = JSON.parse(localStorage.getItem(POS_KEY) || "null");
      if (saved && typeof saved.x === "number" && typeof saved.y === "number") {
        pos = saved; clampToPlay(); apply();
      }
    } catch (e) {}

    var start = null;
    w.addEventListener("pointerdown", function (e) {
      if (e.target.closest(".av-care-btn")) return;
      start = { px: e.clientX, py: e.clientY, x: pos.x, y: pos.y };
      w.setPointerCapture(e.pointerId);
    });
    w.addEventListener("pointermove", function (e) {
      if (!start) return;
      var dx = e.clientX - start.px, dy = e.clientY - start.py;
      if (!w._avDragMoved && Math.abs(dx) + Math.abs(dy) > 4) {
        w._avDragMoved = true;
        w.classList.add("av-dragging");
      }
      if (!w._avDragMoved) return;
      pos.x = start.x + dx; pos.y = start.y + dy;
      clampToPlay(); apply();
    });
    function done() {
      if (!start) return;
      start = null;
      w.classList.remove("av-dragging");
      if (w._avDragMoved) save();
      setTimeout(function () { w._avDragMoved = false; }, 0);  // let click see it
    }
    w.addEventListener("pointerup", done);
    w.addEventListener("pointercancel", done);
    w.addEventListener("keydown", function (e) {
      var d = { ArrowLeft: [-8, 0], ArrowRight: [8, 0], ArrowUp: [0, -8], ArrowDown: [0, 8] }[e.key];
      if (!d) return;
      e.preventDefault();
      pos.x += d[0]; pos.y += d[1];
      clampToPlay(); apply(); save();
    });
  }

  /* ---- boot ------------------------------------------------------------- */
  function initAll() {
    var wraps = document.querySelectorAll(".avwrap[data-kind]");
    for (var i = 0; i < wraps.length; i++) {
      var w = wraps[i];
      if (w._av) continue;
      w._av = true;
      startIdle(w);
      startRoam(w);
      initDrag(w);
    }
  }
  if (mq && mq.addEventListener) {
    mq.addEventListener("change", function () {
      if (!still()) return;
      // motion turned off mid-session: freeze the movers where they are
      var moves = document.querySelectorAll(".avwrap[data-kind] .avmove");
      for (var i = 0; i < moves.length; i++) {
        moves[i].style.transition = "none";
        moves[i].style.transform = "";
      }
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
  // pickers/pages that swap avatars in later still get the idle engine
  if (window.MutationObserver) {
    new MutationObserver(function () {
      clearTimeout(initAll._t);
      initAll._t = setTimeout(initAll, 200);
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
