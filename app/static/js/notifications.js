(() => {
  const dialog = document.getElementById('faro-notifications');
  const bell = document.getElementById('faro-notification-bell');
  if (!dialog || !bell) return;
  const list = document.getElementById('faro-notification-list');
  const status = document.getElementById('faro-notification-status');
  const badge = document.getElementById('faro-notification-badge');
  const filters = [...dialog.querySelectorAll('[data-notification-filter]')];
  let data = null, filter = 'all', loading = null, lastRefresh = 0;
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function message(text = '', error = false) {
    status.textContent = text;
    status.dataset.error = String(error);
  }
  function rememberShown() {
    if (!data) return;
    try {
      const key = `faro.notifications.${data.context_key}`;
      const ids = new Set(JSON.parse(sessionStorage.getItem(key) || '[]'));
      data.items.filter(item => item.unread).forEach(item => ids.add(item.id));
      sessionStorage.setItem(key, JSON.stringify([...ids]));
    } catch (_) { /* The bell remains usable when storage is unavailable. */ }
  }
  function open() {
    if (dialog.open) return;
    dialog.showModal();
    document.getElementById('faro-notification-title').focus();
    bell.setAttribute('aria-expanded', 'true');
    rememberShown();
  }
  function maybeOpen() {
    if (!data || dialog.dataset.autoOpen !== 'true' || !data.attention_count || document.hidden) return;
    if (document.querySelector('dialog[open], .modal.show, .offcanvas.show')) return;
    if (document.activeElement?.matches('input, textarea, select, [contenteditable="true"]')) return;
    try {
      const seen = new Set(JSON.parse(sessionStorage.getItem(`faro.notifications.${data.context_key}`) || '[]'));
      if (data.items.some(item => item.unread && !seen.has(item.id))) open();
    } catch (_) { /* Do not repeatedly interrupt when storage is unavailable. */ }
  }
  function render() {
    if (!data) return;
    // Keep expanded task details during a background refresh.
    const expanded = new Set([...list.querySelectorAll('details[open]')].map(node => node.dataset.id));
    list.replaceChildren();
    badge.hidden = data.attention_count === 0;
    badge.textContent = data.attention_count > 99 ? '99+' : data.attention_count;
    bell.setAttribute('aria-label', `Notificaciones: ${data.attention_count} por atender`);
    dialog.querySelector('[data-notification-total]').textContent = `(${data.items.length})`;
    const items = data.items.filter(item => filter === 'all' || item.type === filter);
    if (!items.length) {
      list.append(element('p', 'fn-message', filter === 'task' ? 'No tienes información pendiente de completar.' : 'No hay notificaciones en esta sección.'));
    }
    items.forEach(item => {
      const card = element('article', `fn-card${item.type === 'task' ? ' fn-card--task' : item.unread ? ' fn-card--unread' : ''}`);
      const meta = element('div', 'fn-meta');
      meta.append(element('span', '', item.type === 'task' ? 'Requiere acción' : 'Anuncio del programa'),
                  element('span', '', item.type === 'task' ? 'Pendiente' : item.unread ? 'Sin leer' : 'Leído'));
      card.append(meta, element('h3', '', item.title), element('p', 'fn-message', item.message));
      if (item.type === 'task') {
        card.append(element('p', 'fn-count', `${item.pending_count} asignaciones mensuales · ${item.residential_count} residencial${item.residential_count === 1 ? '' : 'es'}`));
        const details = element('details', 'fn-details');
        details.dataset.id = item.id;
        details.open = expanded.has(item.id) || item.groups.length === 1;
        details.append(element('summary', '', 'Ver residenciales y períodos'));
        item.groups.forEach(group => {
          const row = element('div', 'fn-group');
          row.append(element('strong', '', group.residential), element('p', '', `${group.period} · ${group.pending_count} pendiente${group.pending_count === 1 ? '' : 's'}`));
          const actions = element('div', 'fn-actions');
          group.actions.forEach(action => {
            const link = element('a', 'fn-button fn-button--primary', action.label);
            link.href = action.url;
            actions.append(link);
          });
          row.append(actions);
          if (group.needs_proposal) row.append(element('p', 'fn-note', 'Hay asistencias sin propuesta. Solicita revisar esos registros.'));
          details.append(row);
        });
        card.append(details, element('p', 'fn-note', 'Selecciona el curso en el reporte y guarda los cambios. Los períodos cerrados conservan sus restricciones.'));
      } else if (item.type === 'announcement') {
        card.append(element('p', 'fn-note', `Vigente desde ${item.published_on.split('-').reverse().join('/')}`));
        if (item.unread) {
          const read = element('button', 'fn-button', 'Marcar como leído');
          read.type = 'button';
          read.addEventListener('click', async () => {
            read.disabled = true;
            message();
            try {
              const response = await fetch('/ui/notifications/read', {
                method: 'POST', credentials: 'same-origin', redirect: 'error',
                headers: { 'X-CSRF-Token': data.csrf_token },
                body: new URLSearchParams({ announcement_id: item.announcement_id })
              });
              if (!response.ok) throw new Error('No se pudo marcar el anuncio. Actualiza las notificaciones e intenta otra vez.');
              await refreshAfterChange();
              if (data) message('Anuncio marcado como leído. Puedes volver a consultarlo aquí.');
              filters.find(button => button.dataset.notificationFilter === filter)?.focus();
            } catch (error) { message(error.message, true); read.disabled = false; }
          });
          card.append(read);
        }
      }
      list.append(card);
    });
  }
  async function refresh(auto = false) {
    if (loading) return loading;
    loading = (async () => {
      try {
        const response = await fetch('/ui/notifications', { credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
        if (!response.ok) throw new Error();
        const result = await response.json();
        if (!Array.isArray(result.items)) throw new Error();
        data = result;
        lastRefresh = Date.now();
        bell.removeAttribute('title');
        message(); render();
        if (auto) maybeOpen();
        if (dialog.open) rememberShown();
      } catch (_) {
        data = null;
        list.replaceChildren();
        dialog.querySelector('[data-notification-total]').textContent = '';
        bell.title = 'No se pudieron cargar las notificaciones. Pulsa para reintentar.';
        badge.hidden = true;
        bell.setAttribute('aria-label', 'Notificaciones no disponibles. Reintentar');
        message('No se pudieron actualizar las notificaciones. Cierra y vuelve a abrir para reintentar.', true);
      } finally { loading = null; }
    })();
    return loading;
  }
  async function refreshAfterChange() {
    // A request started before saving may contain the previous state.
    if (loading) await loading;
    await refresh(false);
  }
  bell.addEventListener('click', () => { if (!data) message('Cargando notificaciones…'); open(); refresh(false); });
  dialog.querySelectorAll('[data-notification-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('close', () => { bell.setAttribute('aria-expanded', 'false'); bell.focus(); });
  filters.forEach(button => button.addEventListener('click', () => {
    filter = button.dataset.notificationFilter;
    filters.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    render();
  }));
  document.addEventListener('faro:courses-saved', refreshAfterChange);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && Date.now() - lastRefresh > 60000) refresh(false);
  });
  setInterval(() => { if (!document.hidden && !dialog.open) refresh(false); }, 300000);
  refresh(true);
})();
