(() => {
  const form = document.getElementById('intake-form');
  if (!form) return;
  const scenario = form.elements.scenario, mode = form.elements.work_mode;
  const update = () => {
    for (const kind of ['new', 'existing']) {
      const panel = document.getElementById(`intake-${kind}`);
      if (panel) { panel.hidden = mode.value !== kind; panel.disabled = mode.value !== kind; }
    }
    for (const guide of form.querySelectorAll('.intake-guide')) guide.open = guide.dataset.scenario === scenario.value;
  };
  scenario.addEventListener('change', () => {
    if (scenario.value === 'reference') mode.value = 'reference';
    else if (mode.value === 'reference' && [...mode.options].some(o => o.value === 'new')) mode.value = 'new';
    const guide = [...form.querySelectorAll('.intake-guide')].find(g => g.dataset.scenario === scenario.value);
    if (form.elements.outcome && !form.elements.outcome.value) form.elements.outcome.value = guide.dataset.outcome;
    form.elements.confirmed.checked = false;
    update();
  });
  mode.addEventListener('change', () => { form.elements.confirmed.checked = false; update(); });
  for (const button of form.querySelectorAll('.intake-use')) button.addEventListener('click', () => {
    const field = form.elements[button.dataset.field];
    if (field) { field.value = button.dataset.value; form.elements.confirmed.checked = false; field.focus(); }
  });
  update();
})();
