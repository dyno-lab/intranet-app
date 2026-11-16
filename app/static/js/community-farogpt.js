/* Community welcome only. No report client, data requests or stored conversation. */
(() => {
  'use strict';
  const root = document.querySelector('[data-community-farogpt]');
  if (!root) return;
  const panel = root.querySelector('#community-farogpt-welcome');
  const launcher = root.querySelector('[data-cfg-launcher]');
  const invitation = root.querySelector('[data-cfg-invitation]');
  const dismiss = root.querySelectorAll('[data-cfg-dismiss]');
  const message = root.querySelector('[data-cfg-message]');
  const greetings = [
    'Estoy aquí en Cabo Rojo tomando sol y bien prendido. ☀️💡 ¡Recargando energía para cuando me toque trabajar en Comunidad!',
    'La brisa casi me despeina… ¡y eso que no tengo pelo! 🌊 La bombillita sigue firme, esperando mi turno en Comunidad.',
    'Traje arena hasta en los cables. 🏖️ Estoy sacudiendo la playa para llegar presentable a Comunidad. ¡Un farito también se prepara para su primer día!',
    'El mar está tranquilo, pero yo tengo una ola de ganas de ayudar. 🌊 Mientras preparan mi llegada a Comunidad, ¡aquí sigo dando luz!',
    '¡Me vine de visita con la bombillita encendida! 💡 Todavía estoy buscando dónde enchufarme. Cuando esté lista mi integración con Comunidad, ¡arrancamos!',
    'Ya traje la luz; ahora falta que terminen de ponerme los cables. 🔌 Mientras preparan mi integración con Comunidad, practico mi mejor saludo: ¡holaaa!',
    'Tengo el casco puesto y la bombillita lista. 🦺 Mi integración con Comunidad sigue en construcción; mientras tanto, ¡qué bueno verles por aquí!',
    'Dicen que Roma no se construyó en un día… ¡y un farito ayudante tampoco! 🛠️ Estoy preparándome para acompañarles en Comunidad.',
    'Vine a supervisar la instalación de mi enchufe… ¡y terminé saludando a todo el mundo! 🔌 Cuando esté listo en Comunidad, también ayudaré con las tareas.',
    'Mientras preparan mi llegada, estoy ensayando: «¡Buenos días, Comunidad!». 👋 Ya me sale con luz propia.',
    '¡Traje mi lonchera y muchas ganas de ayudar! 🥪 Mientras terminan mi integración con Comunidad, estoy en entrenamiento intensivo de saludos.',
    'Me dijeron «ve calentando motores», pero como soy un faro, ¡encendí la bombillita! 💡 Sigo preparándome para ayudarles en Comunidad.',
  ];
  let greetingIndex = Math.floor(Math.random() * greetings.length);

  function showWelcome(open, focus = true) {
    if (open && panel.hidden && message) {
      message.textContent = greetings[greetingIndex];
      greetingIndex = (greetingIndex + 1) % greetings.length;
    }
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
