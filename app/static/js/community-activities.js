(() => {
  document.querySelectorAll('.community-goal-fields').forEach((fields) => {
    const type = fields.querySelector('[data-goal-type]');
    const monthly = fields.querySelector('[data-monthly-field]');
    const period = fields.querySelector('[data-period-field]');
    const monthlyInput = monthly.querySelector('input');
    const periodInput = period.querySelector('input');
    const sync = () => {
      const hasGoal = type.value !== 'none';
      const isMonthly = type.value === 'monthly_fixed';
      const isPeriod = type.value === 'period_fixed';
      monthly.hidden = !isMonthly;
      monthlyInput.disabled = !isMonthly;
      monthlyInput.required = isMonthly;
      period.hidden = !hasGoal;
      periodInput.disabled = !hasGoal;
      periodInput.required = isPeriod;
      fields.querySelector('[data-period-help]').textContent = isPeriod
        ? 'Requerida para el período completo del año fiscal.' : 'Opcional para esta modalidad.';
      fields.querySelector('[data-goal-active]').hidden = !hasGoal;
    };
    type.addEventListener('change', sync);
    sync();
  });
  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
})();
