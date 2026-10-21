/* Shared modal focus and background isolation. No form or network actions. */
(function () {
  'use strict';
  var stack = [], background = new Map();
  var selector = 'a[href],button,input,select,textarea,summary,[tabindex]';

  function visible(el) {
    if (!el || !el.isConnected || el.closest('[hidden],[inert]') || el.disabled) return false;
    if (!el.getClientRects().length || getComputedStyle(el).visibility === 'hidden') return false;
    for (var p = el.parentElement; p; p = p.parentElement) {
      if (p.tagName === 'DETAILS' && !p.open && !p.querySelector('summary').contains(el)) return false;
    }
    return true;
  }
  function controls(root) {
    return Array.from(root.querySelectorAll(selector)).filter(function (el) {
      return el.tabIndex >= 0 && visible(el);
    });
  }
  function focus(ctx) {
    var el = typeof ctx.options.initialFocus === 'string' ? ctx.focusRoot.querySelector(ctx.options.initialFocus) : ctx.options.initialFocus;
    if (!visible(el)) el = controls(ctx.focusRoot)[0] || ctx.focusRoot;
    if (!el.hasAttribute('tabindex') && el === ctx.focusRoot) el.setAttribute('tabindex', '-1');
    el.focus({ preventScroll: true });
  }
  function refresh() {
    background.forEach(function (wasInert, el) { el.toggleAttribute('inert', wasInert); });
    background.clear();
    var ctx = stack[stack.length - 1];
    document.body.classList.toggle('a11y-modal-open', !!ctx);
    if (!ctx) return;
    for (var node = ctx.focusRoot; node && node !== document.body; node = node.parentElement) {
      if (!node.parentElement) break;
      Array.from(node.parentElement.children).forEach(function (sibling) {
        if (sibling === node || (ctx.options.allow || []).includes(sibling)) return;
        background.set(sibling, sibling.hasAttribute('inert'));
        sibling.setAttribute('inert', '');
      });
    }
  }
  function open(root, options) {
    if (!root || !root.isConnected) return function () {};
    var existing = stack.find(function (ctx) { return ctx.root === root; });
    if (existing) return existing.release;
    options = options || {};
    var ctx = { root: root, focusRoot: options.focusRoot || root, options: options,
                returnFocus: options.returnFocus || document.activeElement };
    ctx.release = function () {
      var index = stack.indexOf(ctx);
      if (index < 0) return;
      var wasTop = index === stack.length - 1;
      stack.splice(index, 1);
      refresh();
      if (wasTop) {
        var target = ctx.returnFocus;
        if (!visible(target) || target === document.body) target = document.getElementById('maincontent');
        if (visible(target)) target.focus({ preventScroll: true });
        else if (stack.length) focus(stack[stack.length - 1]);
      }
    };
    stack.push(ctx);
    refresh();
    focus(ctx);
    return ctx.release;
  }
  document.addEventListener('keydown', function (event) {
    var ctx = stack[stack.length - 1];
    if (!ctx) {
      if (event.key !== 'Escape') return;
      var details = event.target.closest && event.target.closest('.topnav details[open], .pub-top details[open]');
      if (!details) return;
      details.open = false;
      details.querySelector('summary').focus();
      event.preventDefault(); event.stopImmediatePropagation();
      return;
    }
    if (!ctx.root.isConnected) { ctx.release(); return; }
    if (event.key === 'Escape') {
      if (!ctx.options.onDismiss) return;
      event.preventDefault(); event.stopImmediatePropagation();
      ctx.options.onDismiss();
    } else if (event.key === 'Tab') {
      var items = controls(ctx.focusRoot), first = items[0], last = items[items.length - 1];
      if (!items.length) { event.preventDefault(); focus(ctx); }
      else if (event.shiftKey && (document.activeElement === first || !ctx.focusRoot.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !ctx.focusRoot.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    }
  }, true);
  document.addEventListener('focusin', function (event) {
    var ctx = stack[stack.length - 1];
    if (!ctx) return;
    if (!ctx.root.isConnected) { ctx.release(); return; }
    if (!ctx.focusRoot.contains(event.target)) focus(ctx);
  }, true);
  window.OfficeA11y = { open: open };
})();
