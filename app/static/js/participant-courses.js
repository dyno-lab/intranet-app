(() => {
  const root = document.getElementById('course-report');
  if (!root) return;
  const form = document.getElementById('course-filters');
  const status = document.getElementById('course-status');
  const save = document.getElementById('course-save');
  const period = document.getElementById('course-period');
  const selects = Array.from(root.querySelectorAll('.course-choice'));
  let saving = false;
  const changed = () => selects.filter(select => select.value !== select.dataset.saved);
  const message = (text, error = false) => { status.textContent = text; status.dataset.error = String(error); };
  function syncPeriod() {
    const custom = period.value === 'custom';
    root.querySelectorAll('[data-monthly]').forEach(el => { el.hidden = custom; });
    root.querySelectorAll('[data-custom]').forEach(el => {
      el.hidden = !custom;
      el.querySelector('input').required = custom;
    });
  }
  function syncChanges() {
    const dirty = changed().length;
    if (save) save.disabled = saving || !dirty;
    const pending = selects.filter(select => !select.value).length + root.querySelectorAll('.course-readonly-pending').length;
    document.getElementById('course-pending').textContent = `${pending} selecciones mensuales pendientes`;
    message(dirty ? `${dirty} selecciones modificadas sin guardar.` : 'No hay cambios pendientes de guardar.');
  }
  period.addEventListener('change', syncPeriod);
  syncPeriod();
  selects.forEach(select => select.addEventListener('change', syncChanges));
  form.addEventListener('submit', event => {
    if (saving) { event.preventDefault(); return; }
    if (!changed().length) return;
    if (event.submitter?.hasAttribute('data-export')) {
      event.preventDefault(); message('Guarda los cursos antes de descargar o imprimir.', true);
    } else if (!window.confirm('Hay cursos sin guardar. ¿Continuar y descartar esos cambios?')) event.preventDefault();
  });
  window.addEventListener('beforeunload', event => {
    if (changed().length) { event.preventDefault(); event.returnValue = ''; }
  });
  if (save) save.addEventListener('click', async () => {
    const dirty = changed();
    if (!dirty.length || saving) return;
    saving = true; save.disabled = true;
    selects.forEach(select => { select.disabled = true; });
    message('Guardando cursos…');
    try {
      const response = await fetch(`/ui/reports/cursos/save?${root.dataset.query}`, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': root.dataset.token },
        body: JSON.stringify(dirty.map(select => ({ participant_id: Number(select.dataset.participant),
          year: Number(select.dataset.year), month: Number(select.dataset.month),
          revision: Number(select.dataset.revision), course: select.value })))
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !Array.isArray(result.saved)) throw new Error(typeof result.detail === 'string' ? result.detail : 'No se pudieron guardar los cursos. Vuelve a consultar el reporte.');
      const revisions = new Map(result.saved.map(row => [`${row.participant_id}/${row.year}/${row.month}`, row.revision]));
      dirty.forEach(select => {
        select.dataset.revision = revisions.get(`${select.dataset.participant}/${select.dataset.year}/${select.dataset.month}`);
        select.dataset.saved = select.value;
      });
      message('Cursos guardados correctamente. Ya puedes descargar el reporte.');
    } catch (error) { message(error.message || 'No se pudieron guardar los cursos.', true); }
    finally {
      saving = false; selects.forEach(select => { select.disabled = false; });
      save.disabled = !changed().length;
    }
  });
})();
