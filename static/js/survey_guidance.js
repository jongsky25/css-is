/* Survey validation and progress, with native controls and no write retries. */
(function () {
  'use strict';
  var form = document.getElementById('surveyform') || document.getElementById('combinedform');
  if (!form) return;
  var T = window.SURVEY_I18N || {};
  var box = form.querySelector('[data-survey-errors]');
  var status = form.querySelector('[data-survey-status]');
  var pending = false, marked = [];
  form.noValidate = true; // The server and native controls still own their existing rules.
  function clearMarkers() {
    marked.forEach(function (entry) {
      entry.el.removeAttribute('aria-invalid');
      var ids = (entry.el.getAttribute('aria-describedby') || '').split(/\s+/).filter(function (id) { return id && id !== entry.id; });
      if (ids.length) entry.el.setAttribute('aria-describedby', ids.join(' ')); else entry.el.removeAttribute('aria-describedby');
    });
    marked = [];
  }
  function reveal(control) {
    form.dispatchEvent(new CustomEvent('survey-reveal', {detail:control}));
    control.focus();
    control.scrollIntoView({block:'center'});
  }
  function renderErrors(focus) {
    clearMarkers(); box.textContent = '';
    var seen = {}, errors = [], controls = Array.from(form.elements), groups = new Map();
    controls.forEach(function (control) {
      if (!groups.has(control.name)) groups.set(control.name, []);
      groups.get(control.name).push(control);
    });
    controls.forEach(function (control, i) {
      if (!control.willValidate || control.disabled || control.validity.valid) return;
      var key = control.type === 'radio' ? control.name : 'field-' + i;
      if (seen[key]) return;
      seen[key] = true;
      var question = control.closest('[data-question]');
      var label = question ? question.dataset.question : (control.labels && control.labels[0] ? control.labels[0].textContent.trim() : control.name);
      if (!control.id) control.id = 'survey-field-' + i;
      errors.push({control:control, label:label, id:'survey-error-' + i});
    });
    box.hidden = !errors.length;
    if (!errors.length) return true;
    var heading = document.createElement('h2'); heading.textContent = T.correct || 'Check your answers'; box.appendChild(heading);
    var list = document.createElement('ul'); box.appendChild(list);
    errors.forEach(function (error) {
      var li = document.createElement('li'); li.id = error.id;
      var a = document.createElement('a'); a.href = '#' + error.control.id;
      a.textContent = error.label + ': ' + (error.control.validity.valueMissing ? (T.required || 'Choose an answer.') : (T.invalid || 'Check this value.'));
      a.addEventListener('click', function (event) { event.preventDefault(); reveal(error.control); });
      li.appendChild(a); list.appendChild(li);
      (error.control.type === 'radio' ? groups.get(error.control.name) : [error.control]).forEach(function (control) {
        control.setAttribute('aria-invalid','true');
        control.setAttribute('aria-describedby', ((control.getAttribute('aria-describedby') || '') + ' ' + error.id).trim());
        marked.push({el:control,id:error.id});
      });
    });
    if (focus) box.focus();
    return false;
  }
  function reset() {
    pending = false; form.removeAttribute('aria-busy');
    form.querySelectorAll('button[type=submit], #conv-next').forEach(function (button) {
      button.disabled = false;
      if (button.dataset.label) { button.textContent = button.dataset.label; button.classList.remove('loading'); }
    });
  }
  document.addEventListener('submit', function (event) {
    if (event.target !== form) return;
    if (pending || !renderErrors(true)) {
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    pending = true; form.setAttribute('aria-busy','true');
    form.querySelectorAll('button[type=submit], #conv-next').forEach(function (button) { button.disabled = true; });
    status.textContent = T.sending || 'Submitting. Wait for confirmation before closing this page.';
  }, true); // Before offline capture and loading-state handlers in app.js.
  form.addEventListener('input', function () { if (!box.hidden) renderErrors(false); });
  form.addEventListener('change', function () { if (!box.hidden) renderErrors(false); });
  form.addEventListener('survey-save-failed', function () {
    reset(); clearMarkers(); box.hidden = false;
    box.textContent = T.queue_failed || 'Your answers could not be saved on this device. They are still on this page. Keep it open and try again when connected.';
    status.textContent = ''; box.focus();
  });
  window.addEventListener('pageshow', function (event) {
    if (event.persisted && pending) {
      reset(); status.textContent = T.returned || 'The previous submission may already be recorded. Check its confirmation before submitting again.';
    }
  });
})();
