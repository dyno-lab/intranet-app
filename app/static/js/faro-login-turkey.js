(() => {
  "use strict";

  const visit = document.querySelector("[data-faro-turkey]");
  if (!visit) return;
  const sprite = visit.querySelector(".faro-login-turkey__sprite");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (!sprite) {
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
  let elapsed = 0;
  let lastFrameAt = null;
  let imageReady = false;
  let staticMode = reducedMotion.matches;
  let frameId = 0;
  let delayId = 0;
  let finished = false;

  function finish() {
    if (finished) return;
    finished = true;
    window.clearTimeout(delayId);
    window.cancelAnimationFrame(frameId);
    image.onload = image.onerror = null;
    document.removeEventListener("input", onInput);
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("scroll", refreshGeometry, true);
    window.removeEventListener("resize", refreshGeometry);
    window.removeEventListener("pagehide", finish);
    reducedMotion.removeEventListener("change", onMotionPreference);
    visit.remove();
  }

  function onInput(event) {
    if (event.target.closest("form")) finish();
  }

  function onVisibility() {
    if (document.visibilityState === "hidden") {
      window.clearTimeout(delayId);
      window.cancelAnimationFrame(frameId);
      delayId = frameId = 0;
      lastFrameAt = null;
      visit.hidden = true;
    } else {
      scheduleStart();
    }
  }

  function onMotionPreference(event) {
    // Keep the decoration visible without movement when motion is reduced.
    if (event.matches) staticMode = true;
  }

  function refreshGeometry() {
    geometryDirty = true;
  }

  function animate(now) {
    if (finished) return;
    if (lastFrameAt !== null) elapsed += now - lastFrameAt;
    lastFrameAt = now;
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
    if (staticMode) {
      x = stopAt;
      pose = 5;
    } else if (elapsed < 1850) {
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

  function scheduleStart() {
    if (finished || !imageReady || delayId || frameId || document.visibilityState === "hidden") return;
    delayId = window.setTimeout(() => {
      delayId = 0;
      if (finished || document.visibilityState === "hidden") return;
      geometryDirty = true;
      sprite.style.backgroundImage = `url("${image.src}")`;
      visit.hidden = false;
      frameId = window.requestAnimationFrame(animate);
    }, 650);
  }

  // Autofocus alone is not user input and must not cancel the visit.
  document.addEventListener("input", onInput);
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("scroll", refreshGeometry, {capture: true, passive: true});
  window.addEventListener("resize", refreshGeometry, {passive: true});
  window.addEventListener("pagehide", finish);
  reducedMotion.addEventListener("change", onMotionPreference);
  image.onerror = finish;
  image.onload = () => {
    imageReady = true;
    scheduleStart();
  };
  image.src = visit.dataset.spriteUrl;
})();
