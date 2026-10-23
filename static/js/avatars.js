/* Avatar companions — the behavior engine behind templates/_avatars.html.
 *
 * What lives here (all first-party, offline-safe, no dependencies):
 *  - the delegated tap handler (happy bounce + sparkle + name bubble) that used
 *    to be inline in avatar_defs();
 *  - the IDLE PERSONALITY loop: every visible companion periodically performs a
 *    random behavior from its species' repertoire by toggling an av-do-* class
 *    (the animations themselves are CSS keyframes in avatar_defs());
 *  - the ROAMING engine for the species that travel (bat flies; fish and
 *    dolphin swim a lazy figure-eight) by easing the .avmove group between
 *    waypoints, leaving the swimmers' static water backdrop behind it;
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

  /* ---- night-time sleep: 9pm-6am on the viewer's clock ------------------ */
  function isNight() {
    var h = new Date().getHours();
    return h >= 21 || h < 6;
  }
  function asleep(w) { return w.classList.contains("av-asleep"); }
  function refreshSleep(w) {
    // The bat is nocturnal — night is its active time, so it never sleeps here
    // (a bat that dozed all workday would never be seen awake at the office).
    var should = isNight() && w.dataset.kind !== "bat" &&
                 !(w._avWakeUntil && Date.now() < w._avWakeUntil);
    w.classList.toggle("av-asleep", should);
  }
  function wake(w) {
    if (!isNight() || w.dataset.kind === "bat") return;
    w._avWakeUntil = Date.now() + 45000;               // stirs for a bit, then dozes off
    w.classList.remove("av-asleep");
    clearTimeout(w._avSleepT);
    w._avSleepT = setTimeout(function () { refreshSleep(w); }, 45500);
  }

  /* Recorded voices share one mixer; idle playback never unlocks audio. */
  function play(what, kind) {
    if (window.AvatarAudio) window.AvatarAudio.play(what, kind);
  }
  function maybeVoice(w) {
    if (!window.AvatarAudio || !window.AvatarAudio.isOn()) return;
    if (still() || document.hidden || asleep(w) || w._avAway) return;
    var now = Date.now();
    if (w._avNextVoice && now < w._avNextVoice) return;
    if (Math.random() > 0.18) return;
    w._avNextVoice = now + 45000 + Math.random() * 45000;
    window.AvatarAudio.play("voice", w.dataset.kind, true);
  }

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
    dolphin:   [["av-do-bubbles", 1800], ["av-do-fin", 900], ["av-do-blink", 600],
                ["av-do-hop", 900]],
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
        if (still() || document.hidden || asleep(w)) { tick(); return; }
        if (w._avBusy && Date.now() < w._avBusy) { tick(); return; }  // mid-walk: gait owns .avstage
        var pick = reps[Math.floor(Math.random() * reps.length)];
        w.classList.remove.apply(w.classList, ALL_DO); // clear any leftover
        void w.offsetWidth;                            // restart CSS animations
        w.classList.add(pick[0]);
        clearTimeout(w._avDoT);
        w._avDoT = setTimeout(function () { w.classList.remove(pick[0]); }, pick[1] + 80);
        maybeVoice(w);                                 // occasionally vocalize, too
        tick();
      }, idleDelay(w));
    })();
  }

  /* ---- ground roaming: walkers wander their .av-play panel on their own.
   * Travels the .avmove layer only (drag owns the wrap transform, so the two
   * compose), recomputing the reachable range live each leg. A gait class
   * (av-do-trot/zoom/bound/plod — deliberately NOT in ALL_DO, or the idle tick
   * would strip it mid-leg) animates the walk itself. ---------------------- */
  var WALKERS = {
    dog:    { dur: 1600, pause: [2500, 7000],  gait: "av-do-trot",  zoom: 0.08 },
    cat:    { dur: 2800, pause: [6000, 14000], gait: "av-do-trot" },
    rabbit: { dur: 900,  pause: [4000, 10000], gait: "av-do-bound", hops: [1, 3], step: [40, 70] },
    bird:   { dur: 800,  pause: [3000, 8000],  gait: "av-do-bound", flap: true, step: [50, 90] },
    turtle: { dur: 6000, pause: [4000, 9000],  gait: "av-do-plod",  step: [30, 55], ease: "linear" }
  };
  var GAITS = ["av-do-trot", "av-do-zoom", "av-do-bound", "av-do-plod"];

  function startWalk(w) {
    var spec = WALKERS[w.dataset.kind];
    var move = w.querySelector(".avmove");
    if (!move) return;
    move.style.transformOrigin = "50% 50%";
    w._avGX = 0;
    function pause() { return spec.pause[0] + Math.random() * (spec.pause[1] - spec.pause[0]); }
    function stride(fast) {
      // one leg of travel; returns its duration, or 0 when there's nowhere to go
      var play = w.closest(".av-play");
      if (!play) return 0;
      var pr = play.getBoundingClientRect(), wr = w.getBoundingClientRect();
      if (!wr.width) return 0;
      // the wrap rect ignores the .avmove offset, so these bounds stay valid
      // wherever the art currently is — and self-correct after a drag
      var min = pr.left - wr.left + 10, max = pr.right - wr.right - 10;
      if (max <= min) return 0;
      var target;
      if (spec.step) {                        // short-stepping species (hop / plod)
        var s = spec.step[0] + Math.random() * (spec.step[1] - spec.step[0]);
        target = w._avGX + (Math.random() < 0.5 ? -s : s);
      } else {
        target = min + Math.random() * (max - min);
      }
      target = Math.max(min, Math.min(max, target));
      var dur = fast ? 700 : spec.dur;
      var flip = target < w._avGX ? -1 : 1;
      w._avGX = target;
      w._avBusy = Date.now() + dur + 200;    // idle loop yields while travelling
      w.classList.add(fast ? "av-do-zoom" : spec.gait);
      if (spec.flap) w.classList.add("av-do-flap");
      move.style.transition = "transform " + (dur / 1000) + "s " + (spec.ease || "ease-in-out");
      move.style.transform = "translate(" + Math.round(target) + "px,0) scale(" + flip + ",1)";
      clearTimeout(w._avGaitT);
      w._avGaitT = setTimeout(function () {
        w.classList.remove.apply(w.classList, GAITS);
        if (spec.flap) w.classList.remove("av-do-flap");
      }, dur + 80);
      return dur;
    }
    (function amble() {
      w._avRoamT = setTimeout(function () {
        if (!w.isConnected) return;
        if (still() || document.hidden || asleep(w) || w._avAway ||
            w._avDragMoved || w._avChasing || w.classList.contains("av-dragging")) { amble(); return; }
        var legs = 1, fast = false;
        if (spec.zoom && Math.random() < spec.zoom) { legs = 3; fast = true; }  // zoomies!
        else if (spec.hops) legs = spec.hops[0] + Math.floor(Math.random() * (spec.hops[1] - spec.hops[0] + 1));
        (function run(n) {
          var dur = stride(fast);
          if (!dur) { amble(); return; }
          clearTimeout(w._avChainT);
          w._avChainT = setTimeout(function () {
            if (n <= 1) amble(); else run(n - 1);
          }, dur + 140);
        })(legs);
      }, pause());
    })();
  }

  /* ---- roaming: the bat flies, the fish & dolphin swim ----------------- */
  function startRoam(w) {
    var kind = w.dataset.kind;
    if (WALKERS[kind] && w.closest(".av-play")) { startWalk(w); return; }
    var swims = kind === "fish" || kind === "dolphin";
    if (kind !== "bat" && !swims) return;
    var move = w.querySelector(".avmove");
    if (!move) return;
    move.style.transformOrigin = "50% 50%";
    /* swimmers repeat a lazy figure-eight; the bat picks random waypoints */
    var fig8 = [[16, -5, -1], [0, -10, -1], [-16, -5, 1], [0, 0, 1]];
    var leg = 0;
    (function hop() {
      w._avRoamT = setTimeout(function () {
        if (!w.isConnected) return;
        if (still() || document.hidden || asleep(w)) { hop(); return; }
        var x, y, flip;
        if (swims) {
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
      }, swims ? 2600 : 2600 + Math.random() * 2600);
    })();
  }

  /* ---- explore: the swimmer leaves its card and swims the whole page ----
   * Opt-in via the 🌊 button (fish/dolphin only — the template gates it). The
   * REAL svg is moved (not cloned) into a fixed, pointer-events:none overlay;
   * the holder carries the avwrap/fam-* classes and data-kind/mood because
   * every descendant selector (breathe, mood tint, av-do-*) stops matching the
   * moment the art leaves its wrap. Tap the swimming pet (or the button) to
   * send it home. Preference is remembered per device. -------------------- */
  var EXPLORE_KEY = "css-av-explore";
  function exploreOn() {
    try { return localStorage.getItem(EXPLORE_KEY) === "on"; } catch (e) { return false; }
  }
  function setExplore(on) {
    try { localStorage.setItem(EXPLORE_KEY, on ? "on" : "off"); } catch (e) {}
  }
  function syncExploreBtn(w, on) {
    var btn = w.querySelector(".av-explore-btn");
    if (btn) btn.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function launchExplore(w) {
    if (w._avAway || still()) return;
    var svg = w.querySelector("svg");
    var span = svg && svg.parentElement;
    if (!svg || !span) return;
    var r = span.getBoundingClientRect();
    var overlay = document.createElement("div");
    overlay.className = "av-explore-layer";
    var holder = document.createElement("span");
    holder.className = "avwrap " + (w.classList.contains("fam-plant") ? "fam-plant" : "fam-animal") +
                       " av-explore-pet";
    holder.dataset.kind = w.dataset.kind;
    if (w.dataset.mood) holder.dataset.mood = w.dataset.mood;
    holder._av = true;                    // the MutationObserver must never re-init it
    holder.style.width = r.width + "px";
    holder.style.height = r.height + "px";
    holder.style.transform = "translate(" + Math.round(r.left) + "px," + Math.round(r.top) + "px)";
    holder.appendChild(svg);              // gradient url(#avg-*) refs resolve page-wide
    overlay.appendChild(holder);
    document.body.appendChild(overlay);
    w.classList.add("av-away");
    w._avAway = holder;
    w._avHomeSpan = span;
    startIdle(holder);                    // fins keep flicking, eyes keep blinking
    holder.addEventListener("click", function () {
      setExplore(false); syncExploreBtn(w, false); returnHome(w);
    });
    var homeX = r.left;
    (function voyage() {
      w._avExpT = setTimeout(function () {
        if (!w.isConnected || still() || asleep(w)) { returnHome(w); return; }
        if (document.hidden) { voyage(); return; }
        var x = 16 + Math.random() * Math.max(1, window.innerWidth - r.width - 32);
        var y = 72 + Math.random() * Math.max(1, window.innerHeight - r.height - 96);
        var dur = Math.max(2, Math.min(6, Math.abs(x - homeX) / 90));
        var flip = x < homeX ? -1 : 1;
        homeX = x;
        holder.style.transition = "transform " + dur.toFixed(2) + "s ease-in-out";
        holder.style.transform = "translate(" + Math.round(x) + "px," + Math.round(y) + "px) scale(" + flip + ",1)";
        if (w.dataset.kind === "dolphin" && Math.random() < 0.3) {
          holder.classList.add("av-do-hop");    // the dolphin leaps mid-swim
          setTimeout(function () { holder.classList.remove("av-do-hop"); }, 1000);
        }
        voyage();
      }, 2200 + Math.random() * 1800);
    })();
  }

  function returnHome(w) {
    var holder = w._avAway;
    if (!holder) return;
    clearTimeout(w._avExpT);
    w._avAway = null;
    var svg = holder.querySelector("svg");
    function restore() {
      if (!holder.isConnected) return;
      clearTimeout(holder._avIdleT); clearTimeout(holder._avDoT);
      if (svg && w._avHomeSpan) w._avHomeSpan.appendChild(svg);
      var overlay = holder.parentElement;
      holder.remove();
      if (overlay && overlay.classList.contains("av-explore-layer")) overlay.remove();
      w.classList.remove("av-away");
    }
    if (still() || !w.isConnected || !w._avHomeSpan) { restore(); return; }
    var r = w._avHomeSpan.getBoundingClientRect();
    holder.style.transition = "transform 1.1s ease-in-out";
    holder.style.transform = "translate(" + Math.round(r.left) + "px," + Math.round(r.top) + "px) scale(1,1)";
    var fallback = setTimeout(restore, 1300);
    holder.addEventListener("transitionend", function () {
      clearTimeout(fallback); restore();
    }, { once: true });
  }

  function initExplore(w) {
    if (w._avExpInit || !w.querySelector(".av-explore-btn")) return;
    w._avExpInit = true;
    syncExploreBtn(w, exploreOn());
    if (exploreOn() && !still()) {
      setTimeout(function () {
        if (exploreOn() && !w._avAway && w.isConnected && !still()) launchExplore(w);
      }, 800);
    }
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".av-explore-btn");
    if (!btn) return;
    var w = btn.closest(".avwrap");
    if (!w) return;
    var on = !w._avAway;
    if (on && still()) return;            // no exploring under reduced motion
    setExplore(on);
    syncExploreBtn(w, on);
    if (on) launchExplore(w); else returnHome(w);
  });

  /* ---- curiosity: some companions watch your pointer --------------------
   * The owl's whole act is the full ±12° disc swivel; dog/cat/bird get a
   * subtler ±8° glance. A fast pointer whooshing past the dog also gets it
   * excited (brief tail wag, cooled down so it can't wag forever). --------- */
  var WATCH = {
    owl: { max: 12, div: 16 },
    dog: { max: 8, div: 28 }, cat: { max: 8, div: 28 }, bird: { max: 8, div: 28 }
  };
  var watchRaf = null, lastPX = 0, lastPY = 0, lastPT = 0;
  document.addEventListener("pointermove", function (e) {
    if (still()) return;
    var now = Date.now(), vel = 0;
    if (lastPT && now > lastPT) {
      var dx = e.clientX - lastPX, dy = e.clientY - lastPY;
      vel = Math.sqrt(dx * dx + dy * dy) / (now - lastPT);   // px per ms
    }
    lastPX = e.clientX; lastPY = e.clientY; lastPT = now;
    if (watchRaf) return;
    watchRaf = requestAnimationFrame(function () {
      watchRaf = null;
      var wraps = document.querySelectorAll(".avwrap[data-kind]");
      for (var i = 0; i < wraps.length; i++) {
        var wr = wraps[i];
        if (asleep(wr) || wr._avAway) continue;

        // ---- 3D lean: any interactive companion leans toward the cursor
        // while it's over the companion's own box (Spot Feedback #82, "make
        // the pet 3d") — a tilt-card effect, not species curiosity, so it
        // runs for every kind, not just the WATCH list below.
        if (wr.hasAttribute("data-interactive")) {
          var stage = wr.querySelector(".av-tiltstage");
          if (stage) {
            var sr = wr.getBoundingClientRect();
            var within = sr.width > 0 &&
              e.clientX >= sr.left && e.clientX <= sr.right &&
              e.clientY >= sr.top && e.clientY <= sr.bottom;
            if (within) {
              var lx = (e.clientX - (sr.left + sr.width / 2)) / (sr.width / 2);
              var ly = (e.clientY - (sr.top + sr.height / 2)) / (sr.height / 2);
              stage.style.transition = "";
              stage.style.transform = "rotateY(" + (lx * 10).toFixed(1) + "deg) " +
                                       "rotateX(" + (ly * -8).toFixed(1) + "deg)";
              stage._avTilted = true;
            } else if (stage._avTilted) {
              stage.style.transition = "transform .35s cubic-bezier(.22,1,.36,1)";
              stage.style.transform = "";
              stage._avTilted = false;
            }
          }
        }

        var spec = WATCH[wr.dataset.kind];
        if (!spec) continue;
        var h = wr.querySelector(".av-head");
        if (!h) continue;
        var r = h.getBoundingClientRect();
        if (!r.width) continue;
        var tilt = Math.max(-spec.max, Math.min(spec.max,
                   (e.clientX - (r.left + r.width / 2)) / spec.div));
        h.style.transform = "rotate(" + tilt.toFixed(1) + "deg)";
        h.style.transition = "transform .5s ease";
        clearTimeout(h._avBackT);
        h._avBackT = setTimeout((function (hh) {
          return function () { hh.style.transform = ""; };
        })(h), 2000);
        if (wr.dataset.kind === "dog" && vel > 1.5 &&
            (!wr._avNextExcite || now > wr._avNextExcite)) {
          var wb = wr.getBoundingClientRect();
          var ex = e.clientX - (wb.left + wb.width / 2);
          var ey = e.clientY - (wb.top + wb.height / 2);
          if (ex * ex + ey * ey < 220 * 220) {
            wr._avNextExcite = now + 5000;
            wr.classList.add("av-do-wag");
            clearTimeout(wr._avWagT);
            wr._avWagT = setTimeout((function (ww) {
              return function () { ww.classList.remove("av-do-wag"); };
            })(wr), 1100);
          }
        }
      }
    });
  }, { passive: true });

  /* ---- what the companion says: personal, time-aware, care-aware --------
   * The bubble normally shows the pet's name; a tap swaps in a phrase for a
   * moment. Pools are weighted and never repeat back-to-back. English-only,
   * like the rest of the signed-in shell. -------------------------------- */
  var SPECIES_LINES = {
    dog:     ["Woof! Best day ever!", "Throw something — I'll fetch it!", "You're my favorite person."],
    cat:     ["Hmm. You may pet me.", "I knocked nothing over. Probably.", "Purrrr."],
    rabbit:  ["*wiggles nose*", "Got any carrots?", "Hop hop!"],
    bird:    ["Tweet! Nice to see you!", "La la la~ 🎵", "Look — I found a shiny thing!"],
    turtle:  ["Slow day. Perfect.", "No rush, no worries.", "Steady does it."],
    fish:    ["Blub blub.", "The water's lovely today.", "Just keep swimming~"],
    dolphin: ["Eee-ee! Race you!", "Did you see that flip?", "This whole page could be my ocean!"],
    owl:     ["Hoo… I see everything.", "Wisdom takes patience.", "Hoo's there?"],
    bat:     ["Hanging around, as usual.", "The night is young!", "Got mango?"],
    plant:   ["*rustles happily*", "Growing a little every day.", "Thanks for the sunshine."]
  };
  function phraseFor(w) {
    var pool = [];
    var h = new Date().getHours();
    var person = w.dataset.person || "";
    var greet = h < 12 ? "Good morning" : (h < 18 ? "Good afternoon" : "Good evening");
    pool.push([greet + (person ? ", " + person : "") + "!", 2]);
    var careBtn = w.querySelector(".av-care-btn");
    var waters = careBtn && careBtn.getAttribute("data-care-action") === "water";
    if (w.dataset.mood === "droopy") {
      pool.push(["I missed you…", 4]);
      pool.push([waters ? "A little water would be lovely…"
                        : "I could really use a snack…", 3]);
    }
    var last = Date.parse(w.dataset.lastCare || "");
    if (last && Date.now() - last < 6 * 3600 * 1000) {
      pool.push([waters ? "That water hit the spot!" : "That snack hit the spot!", 4]);
    }
    var streak = parseInt(w.dataset.careStreak || "0", 10);
    if (streak >= 3) pool.push(["Day " + streak + " of you looking after me!", 3]);
    var lines = SPECIES_LINES[w.dataset.kind] ||
                (w.classList.contains("fam-plant") ? SPECIES_LINES.plant : []);
    for (var i = 0; i < lines.length; i++) pool.push([lines[i], 2]);
    var total = 0, j;
    for (j = 0; j < pool.length; j++) if (pool[j][0] !== w._avLastPhrase) total += pool[j][1];
    var roll = Math.random() * total;
    for (j = 0; j < pool.length; j++) {
      if (pool[j][0] === w._avLastPhrase) continue;
      roll -= pool[j][1];
      if (roll <= 0) { w._avLastPhrase = pool[j][0]; return pool[j][0]; }
    }
    return pool[0][0];
  }
  /* show `text` in the bubble for a moment, then restore the pet's name */
  function bubbleFlash(w, text, ms) {
    var b = w.querySelector(".av-bubble");
    if (!b) return;
    if (w._avName === undefined) w._avName = b.textContent;
    b.textContent = text;
    b.classList.add("show");
    clearTimeout(w._avBubT);
    w._avBubT = setTimeout(function () {
      b.classList.remove("show");
      b.textContent = w._avName;
    }, ms || 2600);
  }

  /* ---- tap: happy bounce + sparkle + a personal word -------------------- */
  document.addEventListener("click", function (e) {
    if (e.target.closest(".av-care-btn") || e.target.closest(".av-sound-controls") ||
        e.target.closest(".av-explore-btn")) return;
    var w = e.target.closest(".avwrap[data-interactive]");
    // The space AROUND the companion — its name, stage line, the gaps beside
    // it ([data-pet-area] on the home greeting and the wellness hero) — taps
    // it too. People aimed at the pet and missed: those clicks were the home
    // screen's and wellness hub's remaining dead clicks. Real links inside
    // the area ("Change companion →") still go where they go.
    if (!w && !e.target.closest("a, button, input, select, textarea, label")) {
      var area = e.target.closest("[data-pet-area]");
      if (area) w = area.querySelector(".avwrap[data-interactive]");
    }
    if (!w || w._avDragMoved || w._avPetted || w._avAway) return;   // drags/pets aren't taps; nobody's home while exploring
    wake(w);                                           // a tap stirs a sleeper
    play("tap", w.dataset.kind);
    w.classList.remove("happy");
    void w.offsetWidth;                                // force reflow => restart
    w.classList.add("happy");
    bubbleFlash(w, phraseFor(w));
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
    if (w._avAway) {                     // call it home first, then care
      setExplore(false); syncExploreBtn(w, false); returnHome(w);
      return;
    }
    var action = btn.getAttribute("data-care-action") || "";
    var cls = action === "water" ? "av-caring-water" : "av-caring-feed";
    wake(w);                                           // being cared for stirs a sleeper
    play(action, w.dataset.kind);
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
        .then(function (res) {
          if (!res || !res.ok) return;
          if (res.mood) w.dataset.mood = res.mood;
          if (res.last_care_at) w.dataset.lastCare = res.last_care_at;
          if (typeof res.streak === "number") w.dataset.careStreak = String(res.streak);
          // ALWAYS say something back. `counted` is false inside the 6-hour
          // cooldown (storage.AVATAR_CARE_COOLDOWN_HOURS) — that is a success,
          // not a failure, but saying nothing read as a dead button: it was the
          // app's single biggest friction source (78 + 26 rage clicks over 8
          // users, and spot feedback saying "Not watering" / "Di gumagana").
          // Under prefers-reduced-motion the care animation is suppressed too
          // (_avatars.html "animation:none !important"), so this bubble is the
          // ONLY feedback those users get at all.
          bubbleFlash(w, res.counted
            ? (action === "water" ? "Ahh, thank you! 💧" : "Yum! Thank you! 😋")
            : (action === "water" ? "Still nicely watered 💧" : "Still full, thank you! 😋"),
            2200);
          if (res.badge) badgeToast(w, res.badge);
        })
        .catch(function () {});                        // offline: cosmetic anyway
    } catch (err) { /* fetch unavailable: animation already played */ }
  });

  /* petting: a few hearts drift up while the hold lasts. Base opacity is 0 and
     the float animation raises it, so under reduced motion (animation:none)
     hearts simply never appear — the .av-spark pattern. */
  function spawnHearts(w) {
    if (still()) return;
    var n = 2 + Math.floor(Math.random() * 2);
    for (var i = 0; i < n; i++) {
      var s = document.createElement("span");
      s.className = "av-heart";
      s.textContent = "❤";
      s.style.left = (30 + Math.random() * 40) + "%";
      s.style.animationDelay = (i * 0.15).toFixed(2) + "s";
      w.appendChild(s);
      setTimeout((function (el) { return function () { el.remove(); }; })(s), 1800);
    }
  }

  /* a freshly-earned badge floats up over the companion (the permanent chip
     appears in the wellness hub's badge row on the next load) */
  function badgeToast(w, label) {
    var t = document.createElement("span");
    t.className = "av-badge-toast";
    t.textContent = "🏅 " + label;
    w.appendChild(t);
    play("badge", null);
    setTimeout(function () { t.remove(); }, 4200);     // also covers reduced-motion
  }

  /* ---- drag around the .av-play area ------------------------------------ */
  var POS_KEY = "css-av-pos";
  function initDrag(w) {
    if (!w.hasAttribute("data-drag") || w._avDrag) return;
    w._avDrag = true;
    var pos = { x: 0, y: 0 };
    var posKey = w.getAttribute("data-drag-key") || POS_KEY;
    function apply() { w.style.transform = "translate(" + pos.x + "px," + pos.y + "px)"; }
    function clampToPlay() {
      var play = w.closest(".av-play");
      if (!play) return;
      pos.x = Math.max(-w.offsetLeft, Math.min(play.clientWidth - w.offsetLeft - w.offsetWidth, pos.x));
      pos.y = Math.max(-w.offsetTop, Math.min(play.clientHeight - w.offsetTop - w.offsetHeight, pos.y));
    }
    function save() {
      try { localStorage.setItem(posKey, JSON.stringify(pos)); } catch (e) {}
    }
    try {
      var saved = JSON.parse(localStorage.getItem(posKey) || "null");
      if (saved && typeof saved.x === "number" && typeof saved.y === "number") {
        pos = saved; clampToPlay(); apply();
      }
    } catch (e) {}

    var start = null;
    w.addEventListener("pointerdown", function (e) {
      if (e.target.closest(".av-care-btn") || e.target.closest(".av-sound-controls") ||
          e.target.closest(".av-explore-btn") || w._avAway) return;
      if (w._avGX) {
        // walk the art back under the hand: the drag clamp works on the wrap
        // box, so a leftover roam offset would make grab and pet disagree
        var mv = w.querySelector(".avmove");
        if (mv) { mv.style.transition = "transform .3s ease"; mv.style.transform = ""; }
        w._avGX = 0;
      }
      w.style.transition = "";
      start = { px: e.clientX, py: e.clientY, x: pos.x, y: pos.y };
      w.setPointerCapture(e.pointerId);
      // held still long enough = petting, not a tap and not a drag
      clearTimeout(w._avPetT);
      w._avPetT = setTimeout(startPet, 450);
    });
    function startPet() {
      w._avPetting = true;
      w.classList.add("av-petting");
      play("pet", w.dataset.kind);
      spawnHearts(w);
      clearInterval(w._avHeartI);
      w._avHeartI = setInterval(function () { spawnHearts(w); }, 900);
    }
    function stopPet() {
      clearTimeout(w._avPetT);
      clearInterval(w._avHeartI);
      if (!w._avPetting) return;
      w._avPetting = false;
      w.classList.remove("av-petting");
      w._avPetted = true;                                  // the release is not a tap
      setTimeout(function () { w._avPetted = false; }, 0);
    }
    w.addEventListener("pointermove", function (e) {
      if (!start) return;
      var dx = e.clientX - start.px, dy = e.clientY - start.py;
      if (!w._avDragMoved && Math.abs(dx) + Math.abs(dy) > 4) {
        stopPet();                                         // movement means drag, not pet
        clearTimeout(w._avPetT);
        w._avDragMoved = true;
        w.classList.add("av-dragging");
      }
      if (!w._avDragMoved) return;
      pos.x = start.x + dx; pos.y = start.y + dy;
      clampToPlay(); apply();
    });
    function done() {
      stopPet();
      if (!start) return;
      start = null;
      w.classList.remove("av-dragging");
      if (w._avDragMoved) save();
      setTimeout(function () { w._avDragMoved = false; }, 0);  // let click see it
    }
    w.addEventListener("pointerup", done);
    w.addEventListener("pointercancel", done);

    /* ---- chase: with data-chase the pet trots after a mouse pointer that is
     * moving over (or near) its .av-play stage, pounces when it catches up,
     * then loses interest a few seconds after the pointer goes still. ------- */
    if (w.hasAttribute("data-chase")) {
      var ptr = null, lastMove = 0, caught = 0, chaseT = null;
      document.addEventListener("pointermove", function (e) {
        if (e.pointerType === "touch") return;
        ptr = { x: e.clientX, y: e.clientY }; lastMove = Date.now();
      }, { passive: true });
      var stopChase = function () {
        if (!w._avChasing) return;
        w._avChasing = false;
        w.classList.remove.apply(w.classList, GAITS);
        w.classList.remove("av-chasing");
        w.style.transition = "";
      };
      chaseT = setInterval(function () {
        if (!w.isConnected) { clearInterval(chaseT); return; }
        var play = w.closest(".av-play");
        if (!ptr || !play || still() || document.hidden || asleep(w) || w._avAway || w._avPetting ||
            w._avDragMoved || start || Date.now() - lastMove > 5000) { stopChase(); return; }
        var pr = play.getBoundingClientRect();
        if (ptr.x < pr.left - 140 || ptr.x > pr.right + 140 ||
            ptr.y < pr.top - 100 || ptr.y > pr.bottom + 100) { stopChase(); return; }
        var wr = w.getBoundingClientRect();
        var dx = ptr.x - (wr.left + wr.width / 2), dy = ptr.y - (wr.top + wr.height * 0.6);
        var dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 55) {                              // got it! pounce, then wait
          stopChase();
          if (Date.now() - caught > 2500) {
            caught = Date.now();
            w.classList.remove("av-pounce"); void w.offsetWidth; w.classList.add("av-pounce");
            setTimeout(function () { w.classList.remove("av-pounce"); }, 850);
          }
          return;
        }
        var k = Math.min(1, 32 / dist);              // up to 32px per 80ms tick (~400px/s)
        if (!w._avChasing) {
          w._avChasing = true;
          if (w._avGX) { w._avGX = 0; }
        }
        w.classList.add("av-chasing");
        var mv = w.querySelector(".avmove");
        if (mv) {
          mv.style.transition = "transform .15s";
          mv.style.transform = "scale(" + (dx < 0 ? -1 : 1) + ",1)";
        }
        w._avBusy = Date.now() + 300;
        w.style.transition = "transform .08s linear";
        pos.x += dx * k; pos.y += dy * k;
        clampToPlay(); apply();
      }, 80);
    }
    w.addEventListener("keydown", function (e) {
      if (!e.target.closest(".av-play-btn")) return;
      var d = { ArrowLeft: [-8, 0], ArrowRight: [8, 0], ArrowUp: [0, -8], ArrowDown: [0, 8] }[e.key];
      if (!d) return;
      e.preventDefault();
      pos.x += d[0]; pos.y += d[1];
      clampToPlay(); apply(); save();
    });
  }

  /* ---- level-up reveal: notices the tracked wellness stage rising since the
   * last visit and announces the newly earned regalia (templates/_avatars_art
   * .html _regalia/_pot_regalia) through the same badge toast + sound used for
   * a freshly-earned wellness badge. Scoped to [data-interactive] only — the
   * viewer's OWN companion — so looking at someone else's avatar on a person
   * page never fires someone else's level-up. Keyed per device by species so
   * switching companions doesn't read as a level-up; the first time a given
   * species is ever seen just records its stage silently. --------------- */
  var STAGE_SEEN_PREFIX = "css-av-stage-seen-";
  var REGALIA_NAMES = { 2: "Bronze Collar", 3: "Silver Bandana", 4: "Gold Medal",
                         5: "Royal Cape", 6: "Champion's Crown" };
  function checkLevelUp(w) {
    if (!w.hasAttribute("data-interactive")) return;
    var stage = parseInt(w.dataset.stage || "1", 10);
    var key = STAGE_SEEN_PREFIX + w.dataset.kind;
    var seen;
    try { seen = parseInt(localStorage.getItem(key) || "0", 10); } catch (e) { seen = 0; }
    if (seen && stage > seen) {
      var name = REGALIA_NAMES[stage];
      if (name) {
        // let the page settle (idle loop, sleep check) before popping the toast
        setTimeout(function () {
          if (!w.isConnected) return;
          badgeToast(w, "New gear: " + name + "!");
          play("badge", null);
        }, 900);
      }
    }
    try { localStorage.setItem(key, String(stage)); } catch (e) {}
  }

  /* ---- boot ------------------------------------------------------------- */
  function initAll() {
    var wraps = document.querySelectorAll(".avwrap[data-kind]");
    for (var i = 0; i < wraps.length; i++) {
      var w = wraps[i];
      if (w._av) continue;
      w._av = true;
      refreshSleep(w);
      startIdle(w);
      startRoam(w);
      initDrag(w);
      initExplore(w);
      checkLevelUp(w);
    }
    if (window.AvatarAudio) window.AvatarAudio.sync();
  }
  // re-evaluate bedtime every 5 minutes so the page crosses 9pm/6am live
  setInterval(function () {
    var wraps = document.querySelectorAll(".avwrap[data-kind]");
    for (var i = 0; i < wraps.length; i++) refreshSleep(wraps[i]);
  }, 300000);
  if (mq && mq.addEventListener) {
    mq.addEventListener("change", function () {
      if (!still()) return;
      // motion turned off mid-session: freeze the movers where they are
      var moves = document.querySelectorAll(".avwrap[data-kind] .avmove");
      for (var i = 0; i < moves.length; i++) {
        moves[i].style.transition = "none";
        moves[i].style.transform = "";
      }
      var wraps = document.querySelectorAll(".avwrap[data-kind]");
      for (var j = 0; j < wraps.length; j++) {
        wraps[j].classList.remove.apply(wraps[j].classList, GAITS);
        wraps[j]._avGX = 0;
        if (wraps[j]._avAway) returnHome(wraps[j]);   // explorer comes straight home
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
