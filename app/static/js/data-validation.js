(() => {
  'use strict';
  const root = document.getElementById('faro-data-quality');
  if (!root) return;
  const q = s => root.querySelector(s);
  const initial = q('[data-initial-dialog]');
  if (initial) { initial.close(); initial.showModal(); initial.addEventListener('cancel', () => { window.location.assign(initial.dataset.listUrl); }); }
  const targets = () => [...root.querySelectorAll('[data-target]')];
  const checked = () => targets().filter(input => input.checked);
  function selection() {
    const all = targets(), selected = checked();
    if (q('[data-bulk]')) q('[data-bulk]').disabled = !selected.length || selected.length > 100;
    if (q('[data-selection-error]')) q('[data-selection-error]').hidden = selected.length <= 100;
    if (q('[data-selected-count]')) q('[data-selected-count]').textContent = selected.length ? '(' + selected.length + ')' : '';
    if (q('[data-select-all]')) { q('[data-select-all]').checked = all.length > 0 && all.length === selected.length; q('[data-select-all]').indeterminate = selected.length > 0 && selected.length < all.length; q('[data-select-all]').disabled = !all.length; }
  }
  function followup(detail) {
    if (detail) { targets().forEach(input => { input.checked = false; }); if (initial?.open) initial.close(); }
    q('[data-followup-count]').textContent = (detail ? 1 : checked().length) + ' hallazgo(s) seleccionado(s)';
    q('#dq-followup').showModal();
  }
  q('[data-bulk]')?.addEventListener('click', () => followup(false));
  q('[data-detail-assign]')?.addEventListener('click', () => followup(true));
  q('[data-justify]')?.addEventListener('click', () => { initial.close(); q('#dq-exception').showModal(); });
  q('[data-select-all]')?.addEventListener('change', event => { targets().forEach(input => { input.checked = event.target.checked; }); selection(); });
  targets().forEach(input => input.addEventListener('change', selection));
  root.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => { button.closest('dialog').close(); if (initial) initial.showModal(); }));
  const form = q('[data-filters]');
  const monthNames = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const chosen = () => [...form.querySelectorAll('input[name="months"]:checked')];
  const monthLabel = () => { const items = chosen(); q('[data-month-label]').textContent = items.length === 1 ? monthNames[Number(items[0].value)-1] : items.length + ' meses'; };
  form?.addEventListener('change', monthLabel);
  form?.addEventListener('submit', event => { if (!chosen().length) { event.preventDefault(); q('[data-month-error]').hidden = false; q('.dq-months').open = true; } });
  monthLabel(); selection();
})();
