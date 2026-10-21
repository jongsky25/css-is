(() => {
  function reveal() {
    if (!location.hash) return;
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); }
    catch (_) { return; }
    const target = document.getElementById(id);
    if (!target) return;
    for (let parent = target; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    // A section/card can contain several forms. Focus the heading or summary;
    // opening a link never submits or chooses a decision on the user's behalf.
    const focusTarget = target.tagName === 'DETAILS' ? target.querySelector('summary') : target;
    if (focusTarget.tagName !== 'SUMMARY' && !focusTarget.hasAttribute('tabindex')) focusTarget.setAttribute('tabindex', '-1');
    focusTarget.focus({ preventScroll: true });
    target.scrollIntoView({ block: 'start' });
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (link && !event.defaultPrevented && event.button === 0 &&
        !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey &&
        link.origin === location.origin && link.pathname === location.pathname &&
        link.search === location.search && link.hash && link.hash === location.hash) {
      event.preventDefault();
      reveal();
    }
  });
  addEventListener('hashchange', reveal);
  reveal();
})();
