/* A link to an owned reservation only navigates/focuses its existing row. */
(function () {
  function focusRow() {
    var hash = location.hash;
    if (!/^#room-\d+$/.test(hash)) return;
    var row = document.getElementById(hash.slice(1));
    if (row) row.focus();
  }
  addEventListener('hashchange', focusRow);
  document.addEventListener('click', function (event) {
    var link = event.target.closest('a[href^="#room-"]');
    if (link && link.hash === location.hash) focusRow();
  });
  focusRow();
})();
