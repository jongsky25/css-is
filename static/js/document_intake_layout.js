/* Switch visibility only: the single form stays mounted with its entered values. */
(() => {
  const page = document.querySelector('.doc-intake-review');
  if (!page) return;
  const controls = page.querySelector('.doc-view-switch');
  if (!controls) return;
  controls.hidden = false;
  page.dataset.view = 'review';
  controls.addEventListener('click', event => {
    const button = event.target.closest('[data-doc-view]');
    if (!button) return;
    page.dataset.view = button.dataset.docView;
    controls.querySelectorAll('button').forEach(item => {
      item.setAttribute('aria-pressed', String(item === button));
    });
  });
})();
