(() => {
  "use strict";

  const root = document.querySelector("[data-institutional-report]");
  if (!root) {
    return;
  }

  const mockRecords = [
    {
      proposal: "demo-a",
      date: "2025-04-15",
      duplicates: 9,
      grades: { Español: 81, Matemáticas: 77, Inglés: 79, Ciencias: 83 },
      pregnancy: { women: 3, men: 2, followups: 8 },
      towns: { "Pueblo Norte": 28, "Pueblo Central": 31, "Pueblo Sur": 15 },
    },
    {
      proposal: "demo-b",
      date: "2025-06-15",
      duplicates: 7,
      grades: { Español: 83, Matemáticas: 79, Inglés: 80, Ciencias: 82 },
      pregnancy: { women: 2, men: 2, followups: 6 },
      towns: { "Pueblo Central": 27, "Pueblo Este": 24, "Pueblo Sur": 18 },
    },
    {
      proposal: "demo-a",
      date: "2026-01-15",
      duplicates: 10,
      grades: { Español: 82, Matemáticas: 78, Inglés: 81, Ciencias: 84 },
      pregnancy: { women: 3, men: 2, followups: 7 },
      towns: { "Pueblo Norte": 29, "Pueblo Central": 34, "Pueblo Oeste": 19 },
    },
    {
      proposal: "demo-b",
      date: "2026-03-15",
      duplicates: 8,
      grades: { Español: 84, Matemáticas: 80, Inglés: 82, Ciencias: 85 },
      pregnancy: { women: 3, men: 1, followups: 8 },
      towns: { "Pueblo Central": 30, "Pueblo Este": 28, "Pueblo Sur": 19 },
    },
    {
      proposal: "demo-a",
      date: "2026-04-15",
      duplicates: 11,
      grades: { Español: 85, Matemáticas: 81, Inglés: 83, Ciencias: 86 },
      pregnancy: { women: 4, men: 2, followups: 10 },
      towns: { "Pueblo Norte": 32, "Pueblo Central": 36, "Pueblo Oeste": 23 },
    },
    {
      proposal: "demo-a",
      date: "2026-05-15",
      duplicates: 9,
      grades: { Español: 86, Matemáticas: 82, Inglés: 84, Ciencias: 87 },
      pregnancy: { women: 3, men: 3, followups: 9 },
      towns: { "Pueblo Norte": 30, "Pueblo Central": 35, "Pueblo Sur": 23 },
    },
    {
      proposal: "demo-b",
      date: "2026-06-15",
      duplicates: 12,
      grades: { Español: 84, Matemáticas: 83, Inglés: 85, Ciencias: 86 },
      pregnancy: { women: 5, men: 2, followups: 12 },
      towns: { "Pueblo Central": 37, "Pueblo Este": 34, "Pueblo Sur": 24 },
    },
    {
      proposal: "demo-b",
      date: "2026-07-15",
      duplicates: 13,
      grades: { Español: 86, Matemáticas: 84, Inglés: 85, Ciencias: 88 },
      pregnancy: { women: 4, men: 3, followups: 11 },
      towns: { "Pueblo Norte": 28, "Pueblo Central": 39, "Pueblo Este": 35 },
    },
  ];

  const form = root.querySelector("[data-report-filter-form]");
  const statusMessage = root.querySelector("[data-filter-status]");
  const emptyState = root.querySelector("[data-report-empty]");
  const emptyTitle = root.querySelector("[data-empty-title]");
  const emptyDescription = root.querySelector("[data-empty-description]");
  const reportContent = root.querySelector("[data-report-content]");
  const activityValue = root.querySelector('[data-kpi="activities"]');
  const peopleValue = root.querySelector('[data-kpi="people"]');
  const ageChart = root.querySelector('[data-chart="age"]');
  const educationChart = root.querySelector('[data-chart="education"]');
  const submitButton = form?.querySelector('button[type="submit"]');
  const dataUrl = root.dataset.reportDataUrl;
  const numberFormatter = new Intl.NumberFormat("es-PR");
  const ageBucketLabels = ["0 a 12", "13 a 18", "19 a 59", "60 o más", "No informado"];
  let activeRequest = null;

  if (!form || !activityValue || !peopleValue || !ageChart || !educationChart || !dataUrl) {
    return;
  }

  const addValues = (target, source) => {
    Object.entries(source).forEach(([label, value]) => {
      target[label] = (target[label] || 0) + value;
    });
  };

  const aggregateRecords = (records) => {
    const aggregate = {
      duplicates: 0,
      gradeTotals: {},
      gradeCounts: {},
      pregnancy: { women: 0, men: 0, followups: 0 },
      towns: {},
    };

    records.forEach((record) => {
      aggregate.duplicates += record.duplicates;
      addValues(aggregate.towns, record.towns);
      addValues(aggregate.pregnancy, record.pregnancy);

      Object.entries(record.grades).forEach(([subject, value]) => {
        aggregate.gradeTotals[subject] = (aggregate.gradeTotals[subject] || 0) + value;
        aggregate.gradeCounts[subject] = (aggregate.gradeCounts[subject] || 0) + 1;
      });
    });

    aggregate.grades = Object.fromEntries(
      Object.entries(aggregate.gradeTotals).map(([subject, total]) => [
        subject,
        Math.round(total / aggregate.gradeCounts[subject]),
      ]),
    );
    aggregate.townCount = Object.values(aggregate.towns).filter((value) => value > 0).length;
    return aggregate;
  };

  const renderBars = (container, values, options = {}) => {
    container.replaceChildren();
    const entries = Object.entries(values);
    if (!entries.length) {
      const message = document.createElement("p");
      message.className = "institutional-report-filter__empty";
      message.textContent = options.emptyMessage || "No hay datos para mostrar.";
      container.append(message);
      return;
    }

    const maximum = options.maximum || Math.max(...entries.map(([, value]) => value), 1);

    entries.forEach(([label, value]) => {
      const row = document.createElement("div");
      row.className = "institutional-report-bar";

      const heading = document.createElement("div");
      heading.className = "institutional-report-bar__heading";

      const labelElement = document.createElement("span");
      labelElement.textContent = label;
      const valueElement = document.createElement("strong");
      valueElement.textContent = options.suffix
        ? `${numberFormatter.format(value)}${options.suffix}`
        : numberFormatter.format(value);
      heading.append(labelElement, valueElement);

      const track = document.createElement("div");
      track.className = "institutional-report-bar__track";
      const bar = document.createElement("div");
      bar.className = "institutional-report-bar__value";
      const width = value === 0 ? 0 : Math.max(4, Math.min(100, (value / maximum) * 100));
      bar.style.setProperty("--institutional-report-bar-width", `${width}%`);
      bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", `${label}: ${valueElement.textContent}`);
      track.append(bar);

      row.append(heading, track);
      container.append(row);
    });
  };

  const renderTownTable = (towns, emptyMessage = "No hay datos para mostrar.") => {
    const tableBody = root.querySelector("[data-town-table]");
    tableBody.replaceChildren();

    const entries = Object.entries(towns);
    if (!entries.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 2;
      cell.textContent = emptyMessage;
      row.append(cell);
      tableBody.append(row);
      return;
    }

    entries
      .sort(([, firstValue], [, secondValue]) => secondValue - firstValue)
      .forEach(([town, value]) => {
        const row = document.createElement("tr");
        const townCell = document.createElement("th");
        townCell.scope = "row";
        townCell.textContent = town;
        const valueCell = document.createElement("td");
        valueCell.textContent = numberFormatter.format(value);
        row.append(townCell, valueCell);
        tableBody.append(row);
      });
  };

  const setStatus = (message, isError = false) => {
    statusMessage.textContent = message;
    statusMessage.classList.toggle("institutional-report-filter-status--error", isError);
  };

  const setLoading = (isLoading) => {
    if (submitButton) {
      submitButton.disabled = isLoading;
    }
    form.setAttribute("aria-busy", String(isLoading));
  };

  const showEmptyState = (title, description) => {
    emptyTitle.textContent = title;
    emptyDescription.textContent = description;
    emptyState.hidden = false;
    reportContent.hidden = true;
  };

  const renderDemoDashboard = (records) => {
    emptyState.hidden = true;
    reportContent.hidden = false;

    const hasRecords = records.length > 0;
    if (!hasRecords) {
      root.querySelector('[data-kpi="duplicates"]').textContent = "—";
      root.querySelector('[data-kpi="towns"]').textContent = "—";
      root.querySelector('[data-pregnancy="women"]').textContent = "—";
      root.querySelector('[data-pregnancy="men"]').textContent = "—";
      root.querySelector('[data-pregnancy="followups"]').textContent = "—";
      const demoEmptyMessage = "Sin datos demostrativos para este período.";
      renderBars(root.querySelector('[data-chart="grades"]'), {}, { emptyMessage: demoEmptyMessage });
      renderTownTable({}, demoEmptyMessage);
      return;
    }

    const aggregate = aggregateRecords(records);
    root.querySelector('[data-kpi="duplicates"]').textContent = numberFormatter.format(aggregate.duplicates);
    root.querySelector('[data-kpi="towns"]').textContent = numberFormatter.format(aggregate.townCount);
    root.querySelector('[data-pregnancy="women"]').textContent = numberFormatter.format(aggregate.pregnancy.women);
    root.querySelector('[data-pregnancy="men"]').textContent = numberFormatter.format(aggregate.pregnancy.men);
    root.querySelector('[data-pregnancy="followups"]').textContent = numberFormatter.format(
      aggregate.pregnancy.followups,
    );

    renderBars(root.querySelector('[data-chart="grades"]'), aggregate.grades, { maximum: 100, suffix: "%" });
    renderTownTable(aggregate.towns);
  };

  const filterDemoRecords = (selectedYear, startDate, endDate) => mockRecords.filter((record) => {
    const matchesYear = !selectedYear || record.date.startsWith(`${selectedYear}-`);
    const matchesStart = !startDate || record.date >= startDate;
    const matchesEnd = !endDate || record.date <= endDate;
    return matchesYear && matchesStart && matchesEnd;
  });

  const buildDataUrl = (proposalIds, selectedYear, startDate, endDate) => {
    const url = new URL(dataUrl, window.location.origin);
    proposalIds.forEach((proposalId) => url.searchParams.append("proposal_ids", proposalId));
    if (selectedYear) {
      url.searchParams.set("year", selectedYear);
    }
    if (startDate) {
      url.searchParams.set("start_date", startDate);
    }
    if (endDate) {
      url.searchParams.set("end_date", endDate);
    }
    return url;
  };

  const normalizeRealAgeBuckets = (payload) => {
    const source = payload.real?.age;
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("La distribución real por edad no tiene el formato esperado.");
    }

    const ageBuckets = {};
    ageBucketLabels.forEach((label) => {
      const value = Number(source[label]);
      if (!Number.isInteger(value) || value < 0) {
        throw new Error("La distribución real por edad no tiene el formato esperado.");
      }
      ageBuckets[label] = value;
    });
    return ageBuckets;
  };

  const normalizeRealEducation = (payload) => {
    const source = payload.real?.education;
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("La distribución real de escolaridad no tiene el formato esperado.");
    }

    const education = {};
    Object.entries(source).forEach(([rawLabel, rawValue]) => {
      const label = rawLabel.trim();
      const value = Number(rawValue);
      if (!label || !Number.isInteger(value) || value < 0) {
        throw new Error("La distribución real de escolaridad no tiene el formato esperado.");
      }
      education[label] = value;
    });
    return education;
  };

  const clearRealMetrics = () => {
    activityValue.textContent = "—";
    peopleValue.textContent = "—";
    ageChart.replaceChildren();
    ageChart.removeAttribute("aria-busy");
    educationChart.replaceChildren();
    educationChart.removeAttribute("aria-busy");
  };

  const applyFilters = async () => {
    if (activeRequest) {
      activeRequest.abort();
      activeRequest = null;
    }

    const proposalIds = Array.from(form.querySelectorAll('input[name="proposal"]:checked'))
      .map((input) => input.value);
    const selectedYear = form.elements.year.value;
    const startDate = form.elements.startDate.value;
    const endDate = form.elements.endDate.value;

    if (!proposalIds.length) {
      setLoading(false);
      clearRealMetrics();
      renderDemoDashboard([]);
      showEmptyState(
        "Seleccione al menos una propuesta",
        "Marque una o más propuestas y vuelva a aplicar los filtros.",
      );
      setStatus("Seleccione al menos una propuesta para consultar los indicadores reales.", true);
      return;
    }

    if (startDate && endDate && startDate > endDate) {
      setLoading(false);
      clearRealMetrics();
      renderDemoDashboard([]);
      showEmptyState(
        "Revise el rango de fechas",
        "La fecha inicial debe ser anterior o igual a la fecha final.",
      );
      setStatus("La fecha inicial no puede ser posterior a la fecha final.", true);
      return;
    }

    const filteredRecords = filterDemoRecords(selectedYear, startDate, endDate);
    renderDemoDashboard(filteredRecords);
    activityValue.textContent = "…";
    peopleValue.textContent = "…";
    renderBars(ageChart, {}, { emptyMessage: "Consultando distribución real…" });
    ageChart.setAttribute("aria-busy", "true");
    renderBars(educationChart, {}, { emptyMessage: "Consultando escolaridad real…" });
    educationChart.setAttribute("aria-busy", "true");
    setStatus("Consultando indicadores reales…");
    setLoading(true);

    const controller = new AbortController();
    activeRequest = controller;

    try {
      const response = await fetch(buildDataUrl(proposalIds, selectedYear, startDate, endDate), {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        const message = response.status === 403
          ? "La sesión del reporte expiró. Vuelva a ingresar el PIN."
          : payload.detail || "No fue posible consultar los indicadores reales.";
        throw new Error(message);
      }

      const activities = Number(payload.real?.activities);
      const people = Number(payload.real?.people);
      if (!Number.isInteger(activities) || activities < 0 || !Number.isInteger(people) || people < 0) {
        throw new Error("La respuesta de indicadores reales no tiene el formato esperado.");
      }
      const ageBuckets = normalizeRealAgeBuckets(payload);
      const peopleByAge = Object.values(ageBuckets).reduce((total, value) => total + value, 0);
      if (peopleByAge !== people) {
        throw new Error("La distribución real por edad no coincide con el total de personas.");
      }
      const education = normalizeRealEducation(payload);
      const peopleByEducation = Object.values(education).reduce((total, value) => total + value, 0);
      if (peopleByEducation !== people) {
        throw new Error("La distribución real de escolaridad no coincide con el total de personas.");
      }

      activityValue.textContent = numberFormatter.format(activities);
      peopleValue.textContent = numberFormatter.format(people);
      renderBars(ageChart, ageBuckets);
      renderBars(educationChart, education);
      const proposalLabel = proposalIds.length === 1 ? "1 propuesta" : `${proposalIds.length} propuestas`;
      const demoLabel = filteredRecords.length
        ? "Las métricas restantes son demostrativas y reflejan solo el período seleccionado."
        : "No hay visualización demostrativa para el período seleccionado.";
      setStatus(`Indicadores reales actualizados para ${proposalLabel}. ${demoLabel}`);
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      clearRealMetrics();
      setStatus(error.message || "No fue posible consultar los indicadores reales.", true);
    } finally {
      if (activeRequest === controller) {
        activeRequest = null;
        ageChart.removeAttribute("aria-busy");
        educationChart.removeAttribute("aria-busy");
        setLoading(false);
      }
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void applyFilters();
  });

  form.addEventListener("reset", () => {
    window.setTimeout(() => void applyFilters(), 0);
  });

  void applyFilters();
})();
