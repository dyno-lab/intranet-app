(() => {
  "use strict";

  const visit = document.querySelector("[data-faro-turkey]");
  if (!visit) return;
  const sprite = visit.querySelector(".faro-login-turkey__sprite");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (!sprite || reducedMotion.matches || document.visibilityState === "hidden") {
    visit.remove();
    return;
  }

  // The atlas has four running strides followed by half/open fan-tail poses.
  const poses = ["0% 0%", "50% 0%", "100% 0%", "0% 100%", "50% 100%", "100% 100%"];
  const image = new Image();
  const controls = [...document.querySelectorAll("input, select, textarea, button, a, label")];
  let obstacles = [];
  let geometryDirty = true;
  let width = 0;
  let size = 0;
  let top = 0;
  let startedAt = null;
  let frameId = 0;
  let delayId = 0;
  let finished = false;

  function finish() {
    if (finished) return;
    finished = true;
    window.clearTimeout(delayId);
    window.cancelAnimationFrame(frameId);
    image.onload = image.onerror = null;
    document.removeEventListener("focusin", onFocus);
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("scroll", refreshGeometry, true);
    window.removeEventListener("resize", refreshGeometry);
    window.removeEventListener("pagehide", finish);
    reducedMotion.removeEventListener("change", onMotionPreference);
    visit.remove();
  }

  function onFocus(event) {
    if (event.target.closest("form")) finish();
  }

  function onVisibility() {
    if (document.visibilityState === "hidden") finish();
  }

  function onMotionPreference(event) {
    if (event.matches) finish();
  }

  function refreshGeometry() {
    geometryDirty = true;
  }

  function animate(now) {
    if (finished) return;
    if (startedAt === null) startedAt = now;
    const elapsed = now - startedAt;
    if (elapsed >= 4800) {
      finish();
      return;
    }
    if (geometryDirty) {
      width = visit.clientWidth;
      size = sprite.offsetWidth;
      top = visit.getBoundingClientRect().top;
      obstacles = controls.map(control => control.getBoundingClientRect())
        .filter(rect => rect.width && rect.height);
      geometryDirty = false;
    }

    const stopAt = Math.max(0, width * .32 - size / 2);
    let x;
    let pose;
    let bob = 0;
    if (elapsed < 1850) {
      x = -size + (stopAt + size) * elapsed / 1850;
      pose = Math.floor(elapsed / 100) % 4;
      bob = -Math.abs(Math.sin(elapsed / 100 * Math.PI)) * 2;
    } else if (elapsed < 2850) {
      x = stopAt;
      pose = elapsed < 2050 || elapsed >= 2650 ? 4 : 5;
    } else {
      x = stopAt + (width + size - stopAt) * (elapsed - 2850) / 1950;
      pose = Math.floor((elapsed - 2850) / 100) % 4;
      bob = -Math.abs(Math.sin(elapsed / 100 * Math.PI)) * 2;
    }

    // Never draw over a field, its label, or a button, including after scrolling.
    const obscuresControl = obstacles.some(rect =>
      x < rect.right + 6 && x + size > rect.left - 6 &&
      top + bob < rect.bottom + 6 && top + size > rect.top - 6);
    sprite.style.visibility = obscuresControl ? "hidden" : "visible";
    sprite.style.backgroundPosition = poses[pose];
    sprite.style.transform = `translate3d(${x}px, ${bob}px, 0)`;
    frameId = window.requestAnimationFrame(animate);
  }

  document.addEventListener("focusin", onFocus);
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("scroll", refreshGeometry, {capture: true, passive: true});
  window.addEventListener("resize", refreshGeometry, {passive: true});
  window.addEventListener("pagehide", finish);
  reducedMotion.addEventListener("change", onMotionPreference);
  image.onerror = finish;
  image.onload = () => {
    delayId = window.setTimeout(() => {
      if (finished) return;
      if (document.activeElement?.closest("form")) {
        finish();
        return;
      }
      sprite.style.backgroundImage = `url("${image.src}")`;
      visit.hidden = false;
      frameId = window.requestAnimationFrame(animate);
    }, 650);
  };
  image.src = visit.dataset.spriteUrl;
})();
