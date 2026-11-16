/* Community welcome only. No report client, data requests or stored conversation. */
(() => {
  'use strict';
  const root = document.querySelector('[data-community-farogpt]');
  if (!root) return;
  const panel = root.querySelector('#community-farogpt-welcome');
  const launcher = root.querySelector('[data-cfg-launcher]');
  const invitation = root.querySelector('[data-cfg-invitation]');
  const dismiss = root.querySelectorAll('[data-cfg-dismiss]');

  function showWelcome(open, focus = true) {
    panel.hidden = !open;
    invitation.hidden = open;
    launcher.setAttribute('aria-expanded', String(open));
    launcher.setAttribute('aria-label', open ? 'Minimizar FaroGPT' : 'Abrir bienvenida de FaroGPT');
    if (focus) (open ? dismiss[0] : launcher).focus({ preventScroll: true });
  }

  launcher.addEventListener('click', () => showWelcome(panel.hidden));
  invitation.addEventListener('click', () => showWelcome(true));
  dismiss.forEach(button => button.addEventListener('click', () => showWelcome(false)));
  root.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden) {
      event.preventDefault();
      showWelcome(false);
    }
  });
  root.hidden = false;
  // Greet on arrival without moving focus away from the Community home page.
  showWelcome(true, false);
})();
