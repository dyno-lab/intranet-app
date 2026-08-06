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
      pregnancy: { women: 3, men: 2, followups: 8 },
    },
    {
      proposal: "demo-b",
      date: "2025-06-15",
      pregnancy: { women: 2, men: 2, followups: 6 },
    },
    {
      proposal: "demo-a",
      date: "2026-01-15",
      pregnancy: { women: 3, men: 2, followups: 7 },
    },
    {
      proposal: "demo-b",
      date: "2026-03-15",
      pregnancy: { women: 3, men: 1, followups: 8 },
    },
    {
      proposal: "demo-a",
      date: "2026-04-15",
      pregnancy: { women: 4, men: 2, followups: 10 },
    },
    {
      proposal: "demo-a",
      date: "2026-05-15",
      pregnancy: { women: 3, men: 3, followups: 9 },
    },
    {
      proposal: "demo-b",
      date: "2026-06-15",
      pregnancy: { women: 5, men: 2, followups: 12 },
    },
    {
      proposal: "demo-b",
      date: "2026-07-15",
      pregnancy: { women: 4, men: 3, followups: 11 },
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
  const duplicateValue = root.querySelector('[data-kpi="duplicates"]');
  const townValue = root.querySelector('[data-kpi="towns"]');
  const ageChart = root.querySelector('[data-chart="age"]');
  const educationChart = root.querySelector('[data-chart="education"]');
  const gradesChart = root.querySelector('[data-chart="grades"]');
  const townTable = root.querySelector("[data-town-table]");
  const submitButton = form?.querySelector('button[type="submit"]');
  const dataUrl = root.dataset.reportDataUrl;
  const numberFormatter = new Intl.NumberFormat("es-PR");
  const ageBucketLabels = ["0 a 12", "13 a 18", "19 a 59", "60 o más", "No informado"];
  const gradeSubjectLabels = ["Español", "Matemáticas", "Ciencias", "Inglés"];
  let activeRequest = null;

  if (
    !form
    || !activityValue
    || !peopleValue
    || !duplicateValue
    || !townValue
    || !ageChart
    || !educationChart
    || !gradesChart
    || !townTable
    || !dataUrl
  ) {
    return;
  }

  const addValues = (target, source) => {
    Object.entries(source).forEach(([label, value]) => {
      target[label] = (target[label] || 0) + value;
    });
  };

  const aggregateRecords = (records) => {
    const aggregate = {
      pregnancy: { women: 0, men: 0, followups: 0 },
    };

    records.forEach((record) => {
      addValues(aggregate.pregnancy, record.pregnancy);
    });
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
    townTable.replaceChildren();

    const entries = Object.entries(towns);
    if (!entries.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 2;
      cell.textContent = emptyMessage;
      row.append(cell);
      townTable.append(row);
      return;
    }

    entries
      .sort(([firstLabel, firstValue], [secondLabel, secondValue]) => {
        if (firstLabel === "No informado") return 1;
        if (secondLabel === "No informado") return -1;
        return secondValue - firstValue || firstLabel.localeCompare(secondLabel, "es");
      })
      .forEach(([town, value]) => {
        const row = document.createElement("tr");
        const townCell = document.createElement("th");
        townCell.scope = "row";
        townCell.textContent = town;
        const valueCell = document.createElement("td");
        valueCell.textContent = numberFormatter.format(value);
        row.append(townCell, valueCell);
        townTable.append(row);
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
      root.querySelector('[data-pregnancy="women"]').textContent = "—";
      root.querySelector('[data-pregnancy="men"]').textContent = "—";
      root.querySelector('[data-pregnancy="followups"]').textContent = "—";
      return;
    }

    const aggregate = aggregateRecords(records);
    root.querySelector('[data-pregnancy="women"]').textContent = numberFormatter.format(aggregate.pregnancy.women);
    root.querySelector('[data-pregnancy="men"]').textContent = numberFormatter.format(aggregate.pregnancy.men);
    root.querySelector('[data-pregnancy="followups"]').textContent = numberFormatter.format(
      aggregate.pregnancy.followups,
    );
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
    const source = payload?.real?.age;
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("La distribución real por edad no tiene el formato esperado.");
    }

    const ageBuckets = {};
    ageBucketLabels.forEach((label) => {
      const value = source[label];
      if (!Number.isInteger(value) || value < 0) {
        throw new Error("La distribución real por edad no tiene el formato esperado.");
      }
      ageBuckets[label] = value;
    });
    return ageBuckets;
  };

  const normalizeRealEducation = (payload) => {
    const source = payload?.real?.education;
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("La distribución real de escolaridad no tiene el formato esperado.");
    }

    const education = {};
    Object.entries(source).forEach(([rawLabel, rawValue]) => {
      const label = rawLabel.trim();
      const value = rawValue;
      if (!label || !Number.isInteger(value) || value < 0) {
        throw new Error("La distribución real de escolaridad no tiene el formato esperado.");
      }
      education[label] = value;
    });
    return education;
  };

  const normalizeRealGrades = (payload) => {
    const source = payload?.real?.grades;
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("Las notas reales por materia no tienen el formato esperado.");
    }

    const grades = {};
    gradeSubjectLabels.forEach((label) => {
      const value = source[label];
      if (!Number.isInteger(value) || value < 0 || value > 100) {
        throw new Error("Las notas reales por materia no tienen el formato esperado.");
      }
      grades[label] = value;
    });
    return grades;
  };

  const normalizeRealMunicipalities = (payload) => {
    const source = payload?.real?.towns_by_municipality;
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("La distribución real por municipio no tiene el formato esperado.");
    }

    const municipalities = {};
    Object.entries(source).forEach(([rawLabel, rawValue]) => {
      const label = rawLabel.trim();
      const value = rawValue;
      if (
        !label
        || !Number.isInteger(value)
        || value < 0
        || Object.prototype.hasOwnProperty.call(municipalities, label)
      ) {
        throw new Error("La distribución real por municipio no tiene el formato esperado.");
      }
      municipalities[label] = value;
    });

    if (!Object.prototype.hasOwnProperty.call(municipalities, "No informado")) {
      throw new Error("La distribución real por municipio no incluye los datos no informados.");
    }
    return municipalities;
  };

  const clearRealMetrics = () => {
    activityValue.textContent = "—";
    peopleValue.textContent = "—";
    duplicateValue.textContent = "—";
    townValue.textContent = "—";
    ageChart.replaceChildren();
    ageChart.removeAttribute("aria-busy");
    educationChart.replaceChildren();
    educationChart.removeAttribute("aria-busy");
    gradesChart.replaceChildren();
    gradesChart.removeAttribute("aria-busy");
    renderTownTable({}, "No fue posible cargar los municipios reales.");
    townTable.removeAttribute("aria-busy");
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
    duplicateValue.textContent = "…";
    townValue.textContent = "…";
    renderBars(ageChart, {}, { emptyMessage: "Consultando distribución real…" });
    ageChart.setAttribute("aria-busy", "true");
    renderBars(educationChart, {}, { emptyMessage: "Consultando escolaridad real…" });
    educationChart.setAttribute("aria-busy", "true");
    renderBars(gradesChart, {}, { emptyMessage: "Consultando notas reales…" });
    gradesChart.setAttribute("aria-busy", "true");
    renderTownTable({}, "Consultando municipios reales…");
    townTable.setAttribute("aria-busy", "true");
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

      const activities = payload?.real?.activities;
      const people = payload?.real?.people;
      const duplicates = payload?.real?.duplicates;
      const towns = payload?.real?.towns;
      if (
        !Number.isInteger(activities)
        || activities < 0
        || !Number.isInteger(people)
        || people < 0
        || !Number.isInteger(duplicates)
        || duplicates < 0
        || !Number.isInteger(towns)
        || towns < 0
      ) {
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
      const grades = normalizeRealGrades(payload);
      const municipalities = normalizeRealMunicipalities(payload);
      const peopleByMunicipality = Object.values(municipalities)
        .reduce((total, value) => total + value, 0);
      if (peopleByMunicipality !== people) {
        throw new Error("La distribución real por municipio no coincide con el total de personas.");
      }
      const informedMunicipalities = Object.entries(municipalities)
        .filter(([label, value]) => label !== "No informado" && value > 0)
        .length;
      if (informedMunicipalities !== towns) {
        throw new Error("La cantidad de municipios no coincide con la distribución real.");
      }

      activityValue.textContent = numberFormatter.format(activities);
      peopleValue.textContent = numberFormatter.format(people);
      duplicateValue.textContent = numberFormatter.format(duplicates);
      townValue.textContent = numberFormatter.format(towns);
      renderBars(ageChart, ageBuckets);
      renderBars(educationChart, education);
      renderBars(gradesChart, grades, { maximum: 100, suffix: "%" });
      renderTownTable(municipalities);
      const proposalLabel = proposalIds.length === 1 ? "1 propuesta" : `${proposalIds.length} propuestas`;
      setStatus(
        `Indicadores reales actualizados para ${proposalLabel}. `
        + "El indicador de embarazo permanece demostrativo.",
      );
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
        gradesChart.removeAttribute("aria-busy");
        townTable.removeAttribute("aria-busy");
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
