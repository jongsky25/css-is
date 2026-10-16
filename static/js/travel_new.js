/* Keep the no-JavaScript form usable; progressively hide unrelated questions. */
(function () {
  'use strict';
  var form = document.querySelector('form[action="/travel/new"]');
  if (!form) return;
  function show(node, visible) {
    node.hidden = !visible;
    node.querySelectorAll('input, select').forEach(function (input) { input.disabled = !visible; });
  }
  function update() {
    var selected = form.querySelector('[name="kind"]:checked:not(:disabled)');
    var kind = selected ? selected.value : '';
    form.querySelectorAll('[data-claim-kinds]').forEach(function (node) {
      show(node, !!kind && node.dataset.claimKinds.split(' ').indexOf(kind) >= 0);
    });
    show(document.getElementById('liq-fields'), kind === 'liquidation');
    show(document.getElementById('external-advance'), kind === 'liquidation' && !form.elements.ca.value);
  }
  form.querySelectorAll('.tv-nojs-kinds').forEach(function (node) { node.hidden = true; });
  form.addEventListener('change', update);
  update();
})();
