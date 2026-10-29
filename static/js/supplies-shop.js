/* Enhances the request grid: + / - buttons, live search that keeps typed quantities, and the "N items" bar.
   The page works without this file; the server enforces every limit. */
(function () {
  'use strict';
  var grid = document.getElementById('shop-grid');
  if (!grid) { return; }
  var bar = document.getElementById('shop-bar');
  var count = document.getElementById('shop-count');
  var inputs = Array.prototype.slice.call(grid.querySelectorAll('input[type=number]'));

  function clamp(input, value) {
    var max = input.max === '' ? Infinity : Number(input.max);
    if (isNaN(value) || value < 0) { value = 0; }
    return Math.min(value, max);
  }

  function refresh() {
    var chosen = inputs.filter(function (input) { return !input.disabled && Number(input.value) > 0; }).length;
    count.textContent = chosen + (chosen === 1 ? ' item' : ' items');
    bar.hidden = chosen === 0;
  }

  inputs.forEach(function (input) {
    var row = document.createElement('div');
    row.className = 'shop-qty-row';
    var name = input.getAttribute('data-item') || 'item';
    function button(label, text, delta) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'shop-step';
      b.textContent = text;
      b.setAttribute('aria-label', label + ' ' + name);
      b.disabled = input.disabled;
      b.addEventListener('click', function () {
        input.value = clamp(input, (Number(input.value) || 0) + delta) || '';
        refresh();
      });
      return b;
    }
    input.parentNode.insertBefore(row, input);
    row.appendChild(button('Fewer', '−', -1));
    row.appendChild(input);
    row.appendChild(button('More', '+', 1));
    input.addEventListener('input', function () {
      if (input.value !== '' && Number(input.value) > Number(input.max)) { input.value = input.max; }
      refresh();
    });
  });

  var search = document.getElementById('shop-q');
  if (search) {
    search.addEventListener('input', function () {
      var needle = search.value.trim().toLowerCase();
      Array.prototype.forEach.call(grid.children, function (card) {
        card.hidden = needle !== '' && (card.getAttribute('data-name') || '').indexOf(needle) === -1;
      });
    });
    search.form.addEventListener('submit', function (event) {
      event.preventDefault();
    });
  }
  refresh();
})();
