(() => {
  const carousel = document.querySelector('[data-faro-home-slideshow]');
  if (!carousel) return;

  const photos = [...carousel.querySelectorAll('.faro-home-slideshow__photo')];
  if (photos.length < 2) return;

  const backdrop = carousel.querySelector('.faro-home-slideshow__backdrop');
  const controls = carousel.querySelector('.faro-home-slideshow__controls');
  const count = carousel.querySelector('[data-slideshow-count]');
  const toggle = carousel.querySelector('[data-slideshow-toggle]');
  const icon = toggle.querySelector('i');
  const announcement = carousel.querySelector('[data-slideshow-announcement]');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const intervalMs = 6000;
  let index = 0;
  let playing = !reducedMotion.matches;
  let visible = true;
  let timer = null;

  function render(announce = false) {
    photos.forEach((photo, position) => { photo.hidden = position !== index; });
    backdrop.style.backgroundImage = `url("${photos[index].src}")`;
    count.textContent = `${index + 1} / ${photos.length}`;
    toggle.setAttribute('aria-label', playing ? 'Pausar presentación' : 'Reproducir presentación');
    toggle.setAttribute('aria-pressed', String(!playing));
    icon.className = playing ? 'bi bi-pause-fill' : 'bi bi-play-fill';
    if (announce) announcement.textContent = photos[index].alt;
  }

  function stopTimer() {
    window.clearInterval(timer);
    timer = null;
  }

  function schedule() {
    stopTimer();
    if (playing && visible && !document.hidden) {
      timer = window.setInterval(() => {
        index = (index + 1) % photos.length;
        render();
      }, intervalMs);
    }
  }

  function navigate(direction) {
    index = (index + direction + photos.length) % photos.length;
    playing = false;
    render(true);
    schedule();
  }

  carousel.querySelector('[data-slideshow-previous]').addEventListener('click', () => navigate(-1));
  carousel.querySelector('[data-slideshow-next]').addEventListener('click', () => navigate(1));
  toggle.addEventListener('click', () => {
    playing = !playing;
    render();
    schedule();
  });
  carousel.addEventListener('keydown', event => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      navigate(event.key === 'ArrowRight' ? 1 : -1);
    }
  });
  carousel.addEventListener('focusin', event => {
    if (toggle.contains(event.target)) return;
    playing = false;
    render();
    schedule();
  });
  reducedMotion.addEventListener('change', () => {
    if (reducedMotion.matches) {
      playing = false;
      render();
      schedule();
    }
  });
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      visible = entries[0].isIntersecting;
      schedule();
    }, { threshold: 0.1 });
    observer.observe(carousel);
  }
  document.addEventListener('visibilitychange', schedule);
  window.addEventListener('pagehide', stopTimer);
  window.addEventListener('pageshow', schedule);

  controls.hidden = false;
  render();
  schedule();
})();
