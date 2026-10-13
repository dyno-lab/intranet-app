(() => {
  const form = document.getElementById('notification-publish');
  if (!form) return;
  form.querySelectorAll('[data-audience-scope]').forEach(select => {
    const options = form.querySelector(`[data-audience-options="${select.dataset.audienceScope}"]`);
    function sync() {
      const all = select.value === 'all';
      options.hidden = all;
      options.querySelectorAll('input').forEach(input => { input.disabled = all; });
    }
    select.addEventListener('change', sync);
    sync();
  });
  form.addEventListener('submit', () => { form.querySelector('button[type="submit"]').disabled = true; });
})();
