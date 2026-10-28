/* Supplies 2.1: the picture grid works without this script. It adds + / - buttons, instant search (so typed quantities are
   kept) and the count in the bottom bar. */
(function () {
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
    minus.setAttribute('aria-label', 'One less: ' + (input.previousElementSibling ? input.previousElementSibling.textContent : ''));
    plus.setAttribute('aria-label', 'One more: ' + (input.previousElementSibling ? input.previousElementSibling.textContent : ''));
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
      var words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
      [].slice.call(form.querySelectorAll('.shop-card')).forEach(function (card) {
        var name = card.getAttribute('data-name') || '';
        card.hidden = !words.every(function (w) { return name.indexOf(w) >= 0; });
      });
    });
  }
  refresh();
})();
