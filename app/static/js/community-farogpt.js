/* Community welcome only. No report client, data requests or stored conversation. */
(() => {
  'use strict';
  const root = document.querySelector('[data-community-farogpt]');
  if (!root) return;
  const panel = root.querySelector('#community-farogpt-welcome');
  const launcher = root.querySelector('[data-cfg-launcher]');
  const invitation = root.querySelector('[data-cfg-invitation]');
  const dismiss = root.querySelectorAll('[data-cfg-dismiss]');
  const messages = [...root.querySelectorAll('[data-cfg-message]')];
  const body = root.querySelector('.farogpt__body');
  if (!messages.length) return;
  const nextMessageKey = 'community.farogpt.welcome.next';
  let greetingIndex = 0;
  try {
    const saved = Number(window.sessionStorage.getItem(nextMessageKey));
    if (Number.isInteger(saved) && saved >= 0 && saved < messages.length) greetingIndex = saved;
  } catch (error) {
    // Alternation still works while this page is open if storage is unavailable.
  }

  function showWelcome(open, focus = true) {
    const opening = open && panel.hidden;
    if (opening) {
      messages.forEach((message, index) => { message.hidden = index !== greetingIndex; });
      greetingIndex = (greetingIndex + 1) % messages.length;
      try {
        window.sessionStorage.setItem(nextMessageKey, String(greetingIndex));
      } catch (error) {
        // Keep the greeting usable without browser storage.
      }
    }
    panel.hidden = !open;
    if (opening && body) body.scrollTop = 0;
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
