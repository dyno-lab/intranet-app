(() => {
  const year = document.getElementById('exp_year');
  const preview = document.getElementById('record-preview');
  const status = document.getElementById('record-preview-status');
  if (!year || !preview || !status) return;

  let timer;
  let controller;
  let generation = 0;
  let submitting = false;

  const pause = () => {
    clearTimeout(timer);
    generation++;
    controller?.abort();
    controller = null;
    preview.removeAttribute('aria-busy');
  };

  const refresh = async () => {
    pause();
    if (document.hidden || submitting) return;
    const selectedYear = year.value;
    if (!/^[1-9]\d{3}$/.test(selectedYear)) {
      preview.value = 'Seleccione un año válido';
      status.textContent = 'Seleccione el año de expediente para consultar la numeración.';
      return;
    }
    const requestId = generation;
    const requestController = new AbortController();
    controller = requestController;
    const timeout = setTimeout(() => requestController.abort(), 8000);
    if (preview.dataset.previewYear !== selectedYear) preview.value = 'Consultando…';
    preview.setAttribute('aria-busy', 'true');
    try {
      const url = new URL(preview.dataset.previewUrl, window.location.origin);
      url.searchParams.set('exp_year', selectedYear);
      const response = await fetch(url, {
        cache: 'no-store', credentials: 'same-origin',
        headers: { Accept: 'application/json' }, signal: requestController.signal,
      });
      if (!response.ok) throw new Error('Preview unavailable');
      const data = await response.json();
      if (requestId !== generation || year.value !== selectedYear) return;
      const expectedFormat = new RegExp(`^CP-${selectedYear}-(?!0000)\\d{4}$`);
      if (data.exp_year !== Number(selectedYear) ||
          (data.expediente_num !== null && !expectedFormat.test(data.expediente_num))) {
        throw new Error('Invalid preview');
      }
      preview.dataset.previewYear = selectedYear;
      preview.value = data.expediente_num ?? 'Numeración agotada';
      status.textContent = data.expediente_num
        ? 'Se actualiza cada 10 segundos; se confirma al guardar.'
        : 'No quedan números de cuatro dígitos disponibles para este año.';
    } catch (_) {
      if (requestId === generation) {
        preview.value = 'No disponible';
        status.textContent = 'No se pudo actualizar la vista previa. El número se asignará al guardar.';
      }
    } finally {
      clearTimeout(timeout);
      if (requestId === generation) {
        controller = null;
        preview.removeAttribute('aria-busy');
        if (!document.hidden && !submitting) timer = setTimeout(refresh, 10000);
      }
    }
  };

  year.addEventListener('change', refresh);
  window.addEventListener('focus', refresh);
  document.addEventListener('visibilitychange', () => document.hidden ? pause() : refresh());
  year.form.addEventListener('submit', () => { submitting = true; pause(); });
  window.addEventListener('pagehide', pause);
  window.addEventListener('pageshow', event => {
    if (event.persisted) { submitting = false; refresh(); }
  });
  refresh();
})();
