(function () {
  const buttons = Array.from(document.querySelectorAll('.tab-button'));
  const pages = Array.from(document.querySelectorAll('.dashboard-page'));

  function activatePage(target, updateHash = true) {
    if (!target) return;

    const nextPage = document.getElementById(target);
    const nextButton = buttons.find((button) => button.getAttribute('data-target') === target);

    if (!nextPage || !nextButton) return;

    buttons.forEach((button) => {
      const isActive = button === nextButton;
      button.classList.toggle('active', isActive);
      button.setAttribute('aria-selected', String(isActive));
    });

    pages.forEach((page) => {
      const isActive = page === nextPage;
      page.classList.toggle('active', isActive);
      page.setAttribute('aria-hidden', String(!isActive));
    });

    if (updateHash) {
      history.replaceState(null, '', `#${target}`);
    }
  }

  buttons.forEach((button) => {
    button.setAttribute('type', 'button');
    button.setAttribute('role', 'tab');

    button.addEventListener('click', () => {
      activatePage(button.getAttribute('data-target'));
    });

    button.addEventListener('keydown', (event) => {
      const currentIndex = buttons.indexOf(button);
      let nextIndex = currentIndex;

      if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % buttons.length;
      if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + buttons.length) % buttons.length;

      if (nextIndex !== currentIndex) {
        event.preventDefault();
        buttons[nextIndex].focus();
        activatePage(buttons[nextIndex].getAttribute('data-target'));
      }
    });
  });

  const hashTarget = window.location.hash ? window.location.hash.substring(1) : '';
  if (hashTarget && document.getElementById(hashTarget)) {
    activatePage(hashTarget, false);
  } else {
    const activeButton = buttons.find((button) => button.classList.contains('active')) || buttons[0];
    if (activeButton) activatePage(activeButton.getAttribute('data-target'), false);
  }
})();
