/* Filter the calendar item's people without changing checked selections. */
(function () {
  var box = document.getElementById("people-search");
  var list = document.querySelector(".cf-people .cf-checks");
  var none = document.getElementById("people-nomatch");
  if (!box || !list || !none) return;

  var labels = list.querySelectorAll("label[data-name]");
  var scroll = list.parentElement;

  function filterPeople() {
    var query = box.value.trim().toLocaleLowerCase();
    var shown = 0;
    Array.prototype.forEach.call(labels, function (label) {
      var matches = !query || label.getAttribute("data-name").toLocaleLowerCase().indexOf(query) !== -1;
      label.hidden = !matches;
      if (matches) shown++;
    });
    none.hidden = shown !== 0;
    scroll.scrollTop = 0;
  }

  box.addEventListener("input", filterPeople);
  box.addEventListener("search", filterPeople);
  box.addEventListener("change", filterPeople);
  box.addEventListener("keydown", function (event) {
    if (event.key === "Enter") event.preventDefault();
  });
  filterPeople();
})();
