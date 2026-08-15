/* Card decks — the arrows, dots and keys on top of a native scroll-snap track.
 *
 * The track already swipes with no JavaScript (scroll-snap-type:x mandatory), so
 * everything here is an ADDITION for people on a mouse or a keyboard. The nav is
 * built here rather than rendered server-side for exactly that reason: a button
 * that would do nothing without JS is worse than no button.
 *
 * One deck per [data-deck]; slides are its .deck-slide children.
 */
(function () {
  'use strict';

  function setupDeck(deck) {
    if (!deck || deck.__deckBound) return;
    var track = deck.querySelector('.deck-track');
    if (!track) return;
    var slides = Array.prototype.slice.call(track.querySelectorAll('.deck-slide'));
    if (slides.length < 2) return;                 // one reading needs no pager
    deck.__deckBound = true;

    var nav = document.createElement('div');
    nav.className = 'deck-nav';

    var dots = document.createElement('div');
    dots.className = 'deck-dots';
    dots.setAttribute('role', 'tablist');
    var dotBtns = slides.map(function (slide, i) {
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-label', slide.getAttribute('aria-label') || ('View ' + (i + 1)));
      b.addEventListener('click', function () { go(i); });
      dots.appendChild(b);
      return b;
    });

    var ind = document.createElement('span');
    ind.className = 'deck-ind';
    // polite, not assertive: the reader asked for the next slide, they don't
    // need to be interrupted to be told it arrived.
    ind.setAttribute('aria-live', 'polite');

    var btns = document.createElement('div');
    btns.className = 'deck-btns';
    var prev = document.createElement('button');
    prev.type = 'button';
    prev.setAttribute('aria-label', 'Previous view');
    prev.textContent = '‹';
    var next = document.createElement('button');
    next.type = 'button';
    next.setAttribute('aria-label', 'Next view');
    next.textContent = '›';
    btns.appendChild(prev);
    btns.appendChild(next);

    nav.appendChild(dots);
    nav.appendChild(ind);
    nav.appendChild(btns);
    deck.appendChild(nav);

    function current() {
      var w = track.clientWidth;
      return w ? Math.round(track.scrollLeft / w) : 0;
    }

    function go(i) {
      var n = Math.max(0, Math.min(slides.length - 1, i));
      track.scrollTo({ left: n * track.clientWidth, behavior: 'smooth' });
    }

    function sync() {
      var c = current();
      ind.textContent = (c + 1) + ' / ' + slides.length;
      prev.disabled = c <= 0;
      next.disabled = c >= slides.length - 1;
      dotBtns.forEach(function (b, i) {
        if (i === c) b.setAttribute('aria-current', 'true');
        else b.removeAttribute('aria-current');
      });
      // Off-screen slides are not reachable by tab — otherwise focus would
      // scroll the track sideways under the reader with no way back.
      slides.forEach(function (s, i) { s.inert = (i !== c); });
    }

    prev.addEventListener('click', function () { go(current() - 1); });
    next.addEventListener('click', function () { go(current() + 1); });

    var ticking = false;
    track.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(function () { ticking = false; sync(); });
    });
    window.addEventListener('resize', sync);

    deck.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight') { go(current() + 1); e.preventDefault(); }
      else if (e.key === 'ArrowLeft') { go(current() - 1); e.preventDefault(); }
    });

    sync();
  }

  function setupAll() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-deck]'), setupDeck);
  }

  window.setupDeck = setupDeck;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupAll);
  } else {
    setupAll();
  }
})();
