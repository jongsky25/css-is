document.querySelectorAll('[data-doc-mention-picker]').forEach(function (picker) {
  var form = picker.closest('form');
  var field = form && form.querySelector('textarea[name="reason"]');
  var results = picker.querySelector('.doc-mention-results');
  if (!field || !results) return;
  var labels = Array.from(picker.querySelectorAll('[data-mention-label]'));
  function update() {
    var before = field.value.slice(0, field.selectionStart);
    var match = /(?:^|\s)@([^\s@]*)$/.exec(before);
    results.replaceChildren();
    if (!match) { results.hidden = true; return; }
    var term = match[1].toLocaleLowerCase();
    labels.filter(function (label) {
      return label.dataset.mentionName.toLocaleLowerCase().includes(term);
    }).slice(0, 8).forEach(function (label) {
      var button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('role', 'option');
      button.textContent = (label.dataset.mentionLabel === 'section' ? 'Section: ' : 'Person: ') + label.dataset.mentionName;
      button.addEventListener('click', function () {
        var start = field.selectionStart - match[0].length + (match[0][0] === ' ' ? 1 : 0);
        var name = label.dataset.mentionName;
        field.setRangeText('@' + name + ' ', start, field.selectionStart, 'end');
        label.querySelector('input').checked = true;
        results.hidden = true;
        field.focus();
      });
      results.appendChild(button);
    });
    results.hidden = !results.childElementCount;
  }
  field.addEventListener('input', update);
  field.addEventListener('click', update);
  field.addEventListener('keyup', update);
  field.addEventListener('blur', function () { setTimeout(function () { results.hidden = true; }, 150); });
});
