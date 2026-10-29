/* Supplies 2.1: the picture grid and the plain list both work without this script. It adds + / - buttons and the count in the
   bottom bar to the grid, and instant search to both pages (the grid's cards, and the plain list's drop-downs). The matching is
   the same as on the server: every word typed must be inside the item's words, at the start of one, or one typo away (words of
   four letters or more). */
(function () {
  function words(text) { return (String(text || '').toLowerCase().match(/[a-z0-9]+/g)) || []; }

  function withinOne(a, b) {
    if (a === b) return true;
    if (Math.abs(a.length - b.length) > 1) return false;
    var i;
    if (a.length === b.length) {
      var wrong = [];
      for (i = 0; i < a.length; i++) if (a[i] !== b[i]) wrong.push(i);
      return wrong.length <= 1 || (wrong.length === 2 && wrong[1] === wrong[0] + 1 && a[wrong[0]] === b[wrong[1]] && a[wrong[1]] === b[wrong[0]]);
    }
    var s = a.length < b.length ? a : b, l = a.length < b.length ? b : a;
    for (i = 0; i < l.length; i++) if (l.slice(0, i) + l.slice(i + 1) === s) return true;
    return false;
  }

  function matches(text, query) {
    var have = words(text), low = have.join(' ');
    return words(query).every(function (w) {
      if (low.indexOf(w) >= 0) return true;
      return w.length >= 4 && have.some(function (h) { return h.length >= 4 && withinOne(w, h); });
    });
  }

  /* ---- the plain list: filter every drop-down's items as you type ---- */
  var listSearch = document.querySelector('[data-list-search]');
  if (listSearch) {
    var selects = [].slice.call(document.querySelectorAll('select[name^="item_"]'));
    selects.forEach(function (select) { select._all = [].slice.call(select.options); });
    var applyList = function () {
      var q = listSearch.value;
      selects.forEach(function (select) {
        var keep = select.value;
        while (select.options.length) select.remove(0);
        select._all.forEach(function (option) {
          var search = option.getAttribute('data-search') || option.textContent;
          if (option.value === '' || option.value === keep || !q.trim() || matches(search + ' ' + option.textContent, q)) select.add(option);
        });
        select.value = keep;
      });
    };
    listSearch.addEventListener('input', applyList);
    if (listSearch.form) listSearch.form.addEventListener('submit', function (e) { if (listSearch.value.trim() === '') return; e.preventDefault(); applyList(); });
    if (listSearch.value) applyList();
  }

  /* ---- the picture grid ---- */
  var form = document.querySelector('[data-shop]');
  if (!form) return;
  var inputs = [].slice.call(form.querySelectorAll('[data-shop-qty]'));
  var count = form.querySelector('[data-shop-count]');

  function chosen() {
    return inputs.filter(function (i) { return !i.disabled && parseInt(i.value, 10) > 0; }).length;
  }
  function refresh() {
    var n = chosen();
    if (count) count.textContent = n ? n + (n === 1 ? ' item chosen' : ' items chosen') : 'Nothing chosen yet';
  }
  function clamp(input) {
    var v = parseInt(input.value, 10), max = parseInt(input.max, 10);
    if (isNaN(v) || v < 0) v = 0;
    if (!isNaN(max) && v > max) v = max;
    input.value = v ? String(v) : '';
    refresh();
  }

  inputs.forEach(function (input) {
    if (input.disabled) return;
    var wrap = document.createElement('div');
    wrap.className = 'shop-step';
    var minus = document.createElement('button'), plus = document.createElement('button');
    minus.type = plus.type = 'button';
    minus.textContent = '−'; plus.textContent = '+';
    var label = input.previousElementSibling ? input.previousElementSibling.textContent : '';
    minus.setAttribute('aria-label', 'One less: ' + label);
    plus.setAttribute('aria-label', 'One more: ' + label);
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(minus); wrap.appendChild(input); wrap.appendChild(plus);
    minus.addEventListener('click', function () { input.value = String(Math.max(0, (parseInt(input.value, 10) || 0) - 1) || ''); clamp(input); });
    plus.addEventListener('click', function () { input.value = String((parseInt(input.value, 10) || 0) + 1); clamp(input); });
    input.addEventListener('change', function () { clamp(input); });
    input.addEventListener('input', refresh);
  });

  var search = document.querySelector('[data-shop-search]');
  if (search) {
    search.form.addEventListener('submit', function (e) { e.preventDefault(); });
    search.addEventListener('input', function () {
      var shown = 0, cards = [].slice.call(form.querySelectorAll('.shop-card'));
      cards.forEach(function (card) {
        card.hidden = !matches(card.getAttribute('data-name') || '', search.value);
        if (!card.hidden) shown++;
      });
      var result = form.querySelector('[data-shop-result]');             // say how many are left, for a screen reader
      if (result) result.textContent = !search.value.trim() ? '' : shown ? shown + (shown === 1 ? ' item shown' : ' items shown') : 'No items match what you typed';
    });
  }
  refresh();
})();
