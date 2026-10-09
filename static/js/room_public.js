/* Guest request page: Morning / Afternoon / Whole day set From and Until. The page works without it. */
(function () {
  var form = document.getElementById('rp-form');
  if (!form) return;
  var from = document.getElementById('rp-from'), to = document.getElementById('rp-to');
  Array.prototype.forEach.call(form.querySelectorAll('.rm-quick button'), function (b) {
    b.addEventListener('click', function () {
      var lo = -1, hi = -1;
      Array.prototype.forEach.call(from.options, function (o, i) { if (o.dataset.time === b.dataset.from) lo = i; });
      Array.prototype.forEach.call(to.options, function (o, i) { if (o.dataset.time === b.dataset.to) hi = i; });
      if (lo >= 0 && hi >= 0) { from.selectedIndex = lo; to.selectedIndex = hi; }
    });
  });
})();
