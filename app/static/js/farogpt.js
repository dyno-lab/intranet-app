(() => {
  'use strict';
  const root = document.querySelector('[data-farogpt]');
  if (!root) return;
  document.body.append(root);
  const find = (name) => root.querySelector(`[data-fg-${name}]`);
  const panel = root.querySelector('#farogpt-chat');
  const launcher = find('launcher');
  const invitation = find('invitation');
  const messages = find('messages');
  const body = find('body');
  const suggestions = find('suggestions');
  const input = find('input');
  const send = find('send');
  const format = new Intl.NumberFormat('es-PR');
  let csrf = '';
  let context = {};
  let initialized = false;
  let busy = false;
  let visited = false;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function bubble(kind, text) {
    const row = element('div', `farogpt__message farogpt__message--${kind}`);
    if (kind !== 'user') {
      const avatar = element('img', 'farogpt__message-avatar');
      avatar.src = '/static/img/farogpt-mascot.png';
      avatar.alt = '';
      row.append(avatar);
    }
    const content = element('div', 'farogpt__bubble');
    if (text) content.append(element('p', '', text));
    row.append(content);
    messages.append(row);
    while (messages.children.length > 40) messages.firstElementChild.remove();
    return { row, content };
  }

  function scrollToLatest() {
    const latest = messages.lastElementChild;
    if (latest) body.scrollTop += latest.getBoundingClientRect().top - body.getBoundingClientRect().top - 12;
  }

  function setBusy(value) {
    busy = value;
    send.disabled = value;
    input.setAttribute('aria-busy', String(value));
    suggestions.querySelectorAll('button').forEach(button => { button.disabled = value; });
  }

  function showSuggestions(items) {
    suggestions.replaceChildren();
    (items || []).slice(0, 3).forEach(text => {
      const button = element('button', '', text);
      button.type = 'button';
      button.disabled = busy;
      button.addEventListener('click', () => ask(text));
      suggestions.append(button);
    });
  }

  function reportLink(url, label = 'Ver informe') {
    if (typeof url !== 'string' || !/^\/(?:ui\/(?:farogpt\/informe|monthly-attendance|reports\/(?:no-duplicado|duplicado|adm|vca|hoja-cotejo|por-programa|productividad|notas|embarazo|desercion-escolar|visitas|cursos|bonafide|certificacion|completo))|automatizaciones\/faro\/validacion)\?/.test(url)) return null;
    const link = element('a', 'farogpt__report-link', label);
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.setAttribute('aria-label', `${label} (abre en otra pestaña)`);
    const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    icon.setAttribute('viewBox', '0 0 24 24');
    icon.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M14 3h7v7M21 3 11 13M10 5H4v15h15v-6');
    icon.append(path);
    link.append(icon);
    return link;
  }

  function render(result) {
    if ((result.type === 'result' && Number.isFinite(result.value)) || result.type === 'series') {
      const { content } = bubble('result');
      content.append(element('h3', 'farogpt__result-title', result.title));
      if (Number.isFinite(result.value)) content.append(element('strong', 'farogpt__value', `${format.format(result.value)}${result.unit ? ' ' + result.unit : ''}`));
      const filters = element('div', 'farogpt__filters');
      filters.append(element('p', '', `${result.residential} · ${result.period}`));
      filters.append(element('p', '', `Propuesta: ${result.proposal}`));
      if (result.activity) filters.append(element('p', '', `Actividad: ${result.activity}`));
      content.append(filters, element('p', 'farogpt__definition', result.definition));
      if ((result.cards || []).length > 1) {
        const metrics = element('dl', 'farogpt__metrics');
        result.cards.slice(0, 6).forEach(item => {
          const row = element('div');
          row.append(element('dt', '', item.label), element('dd', '', `${format.format(item.value)}${item.unit ? ' ' + item.unit : ''}`));
          metrics.append(row);
        });
        content.append(metrics);
      }
      if ((result.tables || []).length) {
        const details = element('details', 'farogpt__details');
        details.open = result.type === 'series' || result.show_details === true;
        details.append(element('summary', '', result.details_label || 'Ver desgloses del reporte'));
        result.tables.forEach(item => {
          const wrap = element('div', 'farogpt__table-wrap');
          wrap.tabIndex = 0;
          wrap.setAttribute('role', 'region');
          wrap.setAttribute('aria-label', item.title);
          const table = element('table', 'farogpt__table');
          table.append(element('caption', '', item.title));
          const head = element('thead');
          const header = element('tr');
          item.columns.forEach(text => { const cell = element('th', '', text); cell.scope = 'col'; header.append(cell); });
          head.append(header);
          table.append(head);
          const rows = element('tbody');
          item.rows.slice(0, 12).forEach(values => {
            const row = element('tr');
            values.forEach(value => {
              const cell = element('td');
              if (value && typeof value === 'object') {
                const link = reportLink(value.url, value.text || 'Ver seguimiento');
                if (link) cell.append(link);
                else cell.textContent = value.text || '—';
              } else cell.textContent = typeof value === 'number' ? format.format(value) : value ?? '—';
              row.append(cell);
            });
            rows.append(row);
          });
          table.append(rows);
          wrap.append(table);
          details.append(wrap);
          if (item.rows.length > 12) details.append(element('p', 'farogpt__note', 'Se muestran 12 filas. Abre el informe de consulta para ver el desglose completo.'));
        });
        content.append(details);
      }
      const link = reportLink(result.report_url);
      if (link) content.append(link);
      if (result.source_title) content.append(element('p', 'farogpt__note', `Fuente: ${result.source_title}`));
      const source = reportLink(result.source_url, result.source_label || 'Abrir reporte original');
      if (source) content.append(source);
      (result.source_links || []).forEach(item => {
        const sourceLink = reportLink(item.url, item.label);
        if (sourceLink) content.append(sourceLink);
      });
      (result.monthly_results || []).forEach(month => {
        const monthlyLink = reportLink(month.report_url, `Ver ${month.period.toLowerCase()}`);
        if (monthlyLink) content.append(monthlyLink);
      });
      if (result.note) content.append(element('p', 'farogpt__note', result.note));
      if (result.comparison) {
        const other = result.comparison;
        const comparison = element('div', 'farogpt__comparison');
        comparison.append(element('p', '', `En ${other.period.toLowerCase()}`));
        comparison.append(element('strong', '', `${format.format(other.value)}${result.unit ? ' ' + result.unit : ''}`));
        const difference = other.difference === 0 ? 'La misma cantidad en ambos meses.' :
          `${format.format(Math.abs(other.difference))} ${other.difference > 0 ? 'más' : 'menos'} en ${result.period.toLowerCase()}.`;
        comparison.append(element('p', '', difference));
        const comparisonLink = reportLink(other.report_url, 'Ver mes comparado');
        if (comparisonLink) comparison.append(comparisonLink);
        content.append(comparison);
      }
    } else {
      bubble('assistant', result.message || 'No pude interpretar esa consulta. Indica el indicador, residencial, mes y año.');
    }
    context = result.context || {};
    showSuggestions(result.suggestions);
    scrollToLatest();
  }

  async function request(url, options = {}, timeoutMs = 25000) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...options, signal: controller.signal });
      if (response.redirected || response.status === 401) throw new Error('Tu sesión terminó. Vuelve a iniciar sesión para consultar.');
      if (response.status === 403) {
        const error = await response.json().catch(() => ({}));
        throw new Error(typeof error.detail === 'string' ? error.detail : 'No se pudo validar tu acceso. Actualiza la página y revisa tu sesión.');
      }
      if (response.status === 422) throw new Error('Revisa la pregunta y sus filtros antes de volver a consultar.');
      if (!response.ok) throw new Error('No pude consultar los datos en este momento. Inténtalo nuevamente.');
      return await response.json();
    } catch (error) {
      if (error.name === 'AbortError' || error instanceof TypeError) throw new Error('No hubo respuesta del servidor. Revisa tu conexión e inténtalo nuevamente.');
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function errorMessage(error, retry) {
    const { content } = bubble('assistant', error.message || 'No pude consultar los datos. Inténtalo nuevamente.');
    const button = element('button', 'farogpt__retry', 'Reintentar');
    button.type = 'button';
    button.addEventListener('click', () => { if (!busy) retry(); });
    content.append(button);
    scrollToLatest();
  }

  async function initialize() {
    if (initialized || busy) return;
    setBusy(true);
    const loading = bubble('loading', 'Preparando FaroGPT…');
    try {
      const data = await request('/ui/farogpt/inicio');
      csrf = data.csrf_token;
      initialized = true;
      bubble('assistant', data.message);
      bubble('assistant', data.help);
      showSuggestions(data.suggestions);
    } catch (error) {
      errorMessage(error, initialize);
    } finally {
      loading.row.remove();
      setBusy(false);
      scrollToLatest();
    }
  }

  async function ask(raw, retrying = false, retryContext = null) {
    const question = raw.trim();
    if (!question || busy) return;
    if (!initialized) { await initialize(); if (!initialized) return; }
    if (question.length > 800) return;
    const requestContext = { ...(retryContext || context) };
    if (!retrying) bubble('user', question);
    input.value = '';
    suggestions.replaceChildren();
    setBusy(true);
    const loading = bubble('loading', 'Consultando los registros del programa…');
    scrollToLatest();
    try {
      const result = await request('/ui/farogpt/consulta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-FaroGPT-CSRF': csrf },
        body: JSON.stringify({ question, context: requestContext }),
      }, 120000);
      render(result);
    } catch (error) {
      errorMessage(error, () => ask(question, true, requestContext));
    } finally {
      loading.row.remove();
      setBusy(false);
      scrollToLatest();
      if (!panel.hidden) input.focus({ preventScroll: true });
    }
  }

  function open() {
    panel.hidden = false;
    invitation.hidden = true;
    visited = true;
    launcher.setAttribute('aria-expanded', 'true');
    launcher.setAttribute('aria-label', 'Minimizar FaroGPT');
    input.focus({ preventScroll: true });
    initialize();
  }

  function close() {
    panel.hidden = true;
    launcher.setAttribute('aria-expanded', 'false');
    launcher.setAttribute('aria-label', 'Abrir FaroGPT');
    invitation.hidden = visited;
    launcher.focus({ preventScroll: true });
  }

  launcher.addEventListener('click', () => panel.hidden ? open() : close());
  invitation.addEventListener('click', open);
  find('minimize').addEventListener('click', close);
  find('close').addEventListener('click', close);
  root.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); close(); } });
  find('form').addEventListener('submit', event => { event.preventDefault(); ask(input.value); });
  root.hidden = false;
  if (window.location.hash === '#farogpt') open();
})();
