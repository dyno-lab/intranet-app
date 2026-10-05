/* Community's review role can inspect choices, but cannot enter or submit data.
 * Server dependencies enforce authorization independently of these UI controls. */
(() => {
  const main = document.querySelector('main');
  if (!main) return;
  const blocked = form => form && (
    form.hasAttribute('data-viewer-block-submit') ||
    (form.method.toLowerCase() !== 'get' &&
      new URL(form.getAttribute('action') || location.href, location.href).pathname !== '/community/context')
  );
  const lock = () => {
    main.querySelectorAll('input, textarea, button').forEach(control => {
      if (control.type === 'hidden') return;
      if (control.tagName === 'TEXTAREA' || (control.tagName === 'INPUT' &&
          !['checkbox', 'radio', 'submit', 'reset', 'button', 'file', 'range', 'color'].includes(control.type))) {
        if (!control.readOnly) control.readOnly = true;
      } else if (blocked(control.form) &&
          (control.tagName !== 'BUTTON' || control.type === 'submit')) {
        if (!control.disabled) control.disabled = true;
      }
    });
    main.querySelectorAll('[data-viewer-download]').forEach(link => {
      link.removeAttribute('href');
      link.classList.add('disabled');
      link.setAttribute('aria-disabled', 'true');
      link.setAttribute('tabindex', '-1');
    });
  };
  // Capture runs before page-specific submit handlers (including identity checks).
  main.addEventListener('submit', event => {
    if (blocked(event.target)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  lock();
  // Dependent dropdowns can refresh asynchronously; write buttons stay disabled.
  new MutationObserver(lock).observe(main, {
    subtree: true, childList: true, attributes: true,
    attributeFilter: ['disabled', 'readonly']
  });
})();
