(() => {
  document.querySelectorAll('select[name="proposal_id"][multiple]').forEach((select, index) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'report-proposals';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'form-select report-proposals__toggle';
    button.id = `${select.id || 'report-proposals'}-toggle-${index}`;
    button.setAttribute('aria-expanded', 'false');
    const menu = document.createElement('div');
    menu.className = 'report-proposals__menu';
    menu.id = `${button.id}-options`;
    menu.hidden = true;
    menu.setAttribute('role', 'group');
    menu.setAttribute('aria-label', 'Propuestas');
    button.setAttribute('aria-controls', menu.id);
    const error = document.createElement('div');
    error.className = 'report-proposals__error';
    error.id = `${button.id}-error`;
    error.textContent = 'Selecciona al menos una propuesta.';
    error.hidden = true;
    button.setAttribute('aria-describedby', error.id);
    const addCheckbox = (text, all = false) => {
      const label = document.createElement('label');
      label.className = 'report-proposals__option' + (all ? ' report-proposals__all' : '');
      const input = document.createElement('input');
      input.type = 'checkbox';
      const caption = document.createElement('span');
      caption.textContent = text;
      label.append(input, caption);
      menu.append(label);
      return input;
    };
    const all = addCheckbox('Seleccionar todas', true);
    const options = Array.from(select.options);
    const checks = options.map(option => {
      const input = addCheckbox(option.textContent);
      input.disabled = option.disabled;
      input.addEventListener('change', () => {
        option.selected = input.checked;
        select.dispatchEvent(new Event('change', { bubbles: true }));
      });
      return input;
    });
    const sync = () => {
      checks.forEach((input, i) => { input.checked = options[i].selected; });
      const selected = options.filter(option => option.selected);
      button.textContent = selected.length === 0 ? 'Selecciona propuestas' : selected.length === 1 ? selected[0].textContent : `${selected.length} propuestas seleccionadas`;
      button.title = selected.map(option => option.textContent).join(', ');
      const enabled = options.filter(option => !option.disabled);
      all.checked = enabled.length > 0 && enabled.every(option => option.selected);
      all.indeterminate = enabled.some(option => option.selected) && !all.checked;
      if (selected.length) { error.hidden = true; button.removeAttribute('aria-invalid'); }
    };
    const close = () => { menu.hidden = true; button.setAttribute('aria-expanded', 'false'); };
    const open = () => { menu.hidden = false; button.setAttribute('aria-expanded', 'true'); };
    all.addEventListener('change', () => {
      options.forEach(option => { if (!option.disabled) option.selected = all.checked; });
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    button.addEventListener('click', () => { if (menu.hidden) open(); else close(); });
    wrapper.addEventListener('keydown', event => {
      if (event.key === 'Escape') { close(); button.focus(); }
      if (event.key === 'ArrowDown' && event.target === button) { event.preventDefault(); open(); all.focus(); }
    });
    wrapper.addEventListener('focusout', event => { if (!wrapper.contains(event.relatedTarget)) close(); });
    document.addEventListener('click', event => { if (!wrapper.contains(event.target)) close(); });
    select.addEventListener('change', sync);
    select.addEventListener('invalid', event => {
      event.preventDefault(); error.hidden = false; button.setAttribute('aria-invalid', 'true'); open(); button.focus();
    });
    if (select.form) select.form.addEventListener('reset', () => setTimeout(sync, 0));
    select.before(wrapper);
    wrapper.append(button, menu, error);
    const label = select.parentElement.querySelector('label.form-label');
    if (label) label.htmlFor = button.id;
    const help = select.parentElement.querySelector('#report-proposals-help');
    if (help) help.hidden = true;
    select.hidden = true;
    sync();
  });
})();
