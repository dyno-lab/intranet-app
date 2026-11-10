(() => {
  'use strict';
  document.querySelectorAll('[data-monthly-open]').forEach(button => {
    button.addEventListener('click', () => document.getElementById(button.dataset.monthlyOpen)?.showModal());
  });
  document.querySelectorAll('[data-monthly-close]').forEach(button => {
    button.addEventListener('click', () => button.closest('dialog')?.close());
  });
  document.querySelectorAll('.monthly-page form[method="post"]').forEach(form => {
    form.addEventListener('submit', () => {
      form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = true; });
    });
  });
})();
