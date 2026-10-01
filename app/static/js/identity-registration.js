(() => {
  const dialog = document.getElementById('identity-registration-dialog');
  if (!dialog) return;
  const confirm = dialog.querySelector('[data-identity-confirm]');
  const update = () => { confirm.disabled = !dialog.querySelector('[name="identity_candidate_id"]:checked:not(:disabled)'); };
  dialog.addEventListener('change', update);
  update();
  if (typeof dialog.showModal !== 'function') return;
  dialog.close();
  dialog.showModal();
  dialog.querySelectorAll('[data-identity-close]').forEach(button => {
    button.addEventListener('click', event => { event.preventDefault(); dialog.close(); });
  });
  dialog.addEventListener('close', () => {
    dialog.closest('form').querySelector('[name="nombre"]')?.focus();
  });
})();
