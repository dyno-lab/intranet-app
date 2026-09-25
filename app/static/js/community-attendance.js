(() => {
  document.querySelectorAll('[data-minutes-input]').forEach((input) => {
    const output = document.getElementById(input.dataset.minutesInput);
    const sync = () => {
      const minutes = Number(input.value);
      output.value = input.value && Number.isFinite(minutes) && minutes >= 0
        ? `${Math.floor(minutes / 60)} h ${Math.round(minutes % 60)} min` : '';
    };
    input.addEventListener('input', sync);
    sync();
  });

  document.querySelectorAll('[data-session-form]').forEach((form) => {
    const program = form.querySelector('[name="program_id"]');
    const year = form.querySelector('[name="fiscal_year_id"]');
    const activity = form.querySelector('[name="activity_id"]');
    const day = form.querySelector('[name="session_date"]');
    const message = form.querySelector('[data-context-message]');
    const submit = form.querySelector('[data-session-submit]');
    let requestNumber = 0;
    const reload = async () => {
      const currentRequest = ++requestNumber;
      const selectedActivity = activity.value;
      activity.replaceChildren(new Option('Seleccione una actividad', ''));
      activity.disabled = true;
      submit.disabled = true;
      const option = year.selectedOptions ? year.selectedOptions[0] : null;
      day.min = option?.dataset.min || '';
      day.max = option?.dataset.max || form.dataset.today;
      if (!program.value || !year.value || year.value === '0' || program.value === '0') {
        message.textContent = 'Seleccione un programa y un año fiscal para cargar sus actividades.';
        return;
      }
      if (option?.dataset.closed === 'true') {
        message.textContent = 'Este año fiscal está cerrado o no tiene fechas disponibles para registrar sesiones.';
        return;
      }
      message.textContent = 'Cargando actividades del programa y año fiscal…';
      try {
        const params = new URLSearchParams({program_id: program.value, fiscal_year_id: year.value});
        const response = await fetch('/community/attendance/activities?' + params, {headers: {'Accept': 'application/json'}});
        if (!response.ok) throw new Error('No se pudieron cargar las actividades.');
        const data = await response.json();
        if (currentRequest !== requestNumber) return;
        data.activities.forEach((row) => activity.add(new Option(row.label, row.id)));
        if ([...activity.options].some((item) => item.value === selectedActivity)) activity.value = selectedActivity;
        activity.disabled = !data.activities.length;
        submit.disabled = !data.activities.length;
        message.textContent = data.activities.length
          ? 'Solo se muestran actividades activas de este programa y año fiscal.'
          : 'No hay actividades activas asociadas a este programa y año fiscal.';
      } catch (_) {
        if (currentRequest === requestNumber) message.textContent = 'No se pudieron cargar las actividades. Recargue la página e intente nuevamente.';
      }
    };
    program.addEventListener('change', reload);
    year.addEventListener('change', reload);
    reload();
  });

  const roster = document.querySelector('[data-attendance-roster]');
  if (roster) {
    const rows = [...roster.querySelectorAll('[data-participant-row]')];
    const range = document.getElementById('age-range-filter');
    const min = document.getElementById('age-min-filter');
    const max = document.getElementById('age-max-filter');
    const inactive = document.getElementById('hide-inactive-filter');
    const attended = document.getElementById('show-attended-only-filter');
    const count = document.getElementById('attendance-counter-value');
    const visible = document.getElementById('visible-participants-count');
    const empty = document.getElementById('no-participant-filter-results-row');
    const apply = () => {
      const lower = min.value === '' ? null : Number(min.value);
      const upper = max.value === '' ? null : Number(max.value);
      min.setCustomValidity(lower !== null && upper !== null && lower > upper ? 'La edad desde no puede superar la edad hasta.' : '');
      if (!min.reportValidity() || !max.reportValidity()) return;
      let shown = 0;
      let selected = 0;
      rows.forEach((row) => {
        const checkbox = row.querySelector('input[type="checkbox"]');
        const age = row.dataset.age === '' ? null : Number(row.dataset.age);
        if (checkbox.checked) selected++;
        const matchesAge = (lower === null || (age !== null && age >= lower)) && (upper === null || (age !== null && age <= upper));
        const show = matchesAge && (!inactive.checked || row.dataset.isActive === '1') && (!attended.checked || checkbox.checked);
        row.hidden = !show;
        if (show) shown++;
      });
      count.textContent = String(selected);
      visible.textContent = String(shown);
      empty.hidden = shown !== 0;
    };
    range.addEventListener('change', () => {
      min.value = range.selectedOptions[0].dataset.min || '';
      max.value = range.selectedOptions[0].dataset.max || '';
    });
    document.getElementById('apply-age-filter').addEventListener('click', apply);
    document.getElementById('clear-age-filter').addEventListener('click', () => {
      range.value = ''; min.value = ''; max.value = '';
      inactive.checked = true; attended.checked = false;
      apply();
    });
    inactive.addEventListener('change', apply);
    attended.addEventListener('change', apply);
    roster.addEventListener('change', apply);
    apply();
  }

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
})();
