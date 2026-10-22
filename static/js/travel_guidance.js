/* Open and focus real checklist sections, without submitting a form. */
(function () {
  'use strict';
  function reveal() {
    var id; try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; }
    if (!/^(item-[a-z0-9_]+|travel-answers|travel-flags|flag-\d+)$/.test(id)) return;
    var target = document.getElementById(id);
    if (!target) return;
    if (target.tagName === 'DETAILS') target.open = true;
    var details = target.querySelector('details');
    if (details) details.open = true;
    var focus = target.querySelector('summary') || target;
    if (focus.tabIndex < 0 && !focus.hasAttribute('tabindex')) focus.setAttribute('tabindex','-1');
    focus.focus(); target.scrollIntoView({block:'start'});
  }
  window.addEventListener('hashchange', reveal);
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest && ev.target.closest('a[href]');
    if (a && a.pathname === location.pathname && a.search === location.search && a.hash === location.hash) reveal();
  });
  var error = document.getElementById('travel-form-error');
  if (error) error.focus(); else reveal();
})();
