/* Read-only counter; notice targeting stays on the server. */
(() => {
  const badge = document.getElementById('community-alert-count');
  const link = document.getElementById('community-alert-link');
  let loading = false;
  let lastRefresh = 0;
  const refresh = async () => {
    if (!badge || loading || document.hidden) return;
    loading = true;
    lastRefresh = Date.now();
    try {
      const response = await fetch('/community/alerts/summary', {credentials: 'same-origin', cache: 'no-store', redirect: 'error'});
      if (!response.ok) throw new Error('alerts');
      const data = await response.json();
      if (!Number.isInteger(data.attention_count) || data.attention_count < 0) throw new Error('count');
      const count = data.attention_count;
      badge.textContent = count > 99 ? '99+' : String(count);
      badge.hidden = count === 0;
      link.setAttribute('aria-label', count ? 'Alertas: ' + count + ' pendientes' : 'Alertas');
      link.removeAttribute('title');
    } catch (_) {
      badge.hidden = true;
      link?.setAttribute('aria-label', 'Alertas');
      link?.setAttribute('title', 'No se pudo actualizar el contador. Abra Alertas para consultar.');
    } finally { loading = false; }
  };
  if (badge?.hasAttribute('data-count')) lastRefresh = Date.now();
  else refresh();
  window.setInterval(refresh, 60000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && Date.now() - lastRefresh >= 60000) refresh();
  });
  document.querySelectorAll('[data-notice-scope]').forEach(select => {
    const group = document.getElementById(select.dataset.noticeScope);
    if (!group) return;
    const sync = () => {
      const enabled = select.value === 'selected';
      group.hidden = !enabled;
      group.querySelectorAll('input').forEach(input => { input.disabled = !enabled; });
    };
    select.addEventListener('change', sync);
    sync();
  });
})();
