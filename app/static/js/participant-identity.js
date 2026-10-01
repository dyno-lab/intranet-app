(() => {
  if (!window.bootstrap?.Popover) return;
  const entries = [];
  document.querySelectorAll('[data-participant-identity-link]').forEach(button => {
    const tooltip = button.title;
    const popover = new bootstrap.Popover(button, {
      container: 'body',
      placement: 'auto',
      trigger: 'click',
      customClass: 'participant-identity-popover',
      title: 'Vínculo confirmado',
      content: button.dataset.identityDescription,
      html: false,
    });
    button.title = tooltip;
    button.addEventListener('show.bs.popover', () => {
      entries.forEach(entry => { if (entry.button !== button) entry.popover.hide(); });
      button.setAttribute('aria-expanded', 'true');
    });
    button.addEventListener('hide.bs.popover', () => button.setAttribute('aria-expanded', 'false'));
    entries.push({button, popover});
  });
  document.addEventListener('click', event => {
    if (event.target.closest('[data-participant-identity-link], .participant-identity-popover')) return;
    entries.forEach(entry => entry.popover.hide());
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') entries.forEach(entry => entry.popover.hide());
  });
})();
