(() => {
  "use strict";

  const root = document.querySelector("[data-institutional-report]");
  if (!root) {
    return;
  }

  const form = root.querySelector("[data-report-filter-form]");
  const statusMessage = root.querySelector("[data-filter-status]");
  const emptyState = root.querySelector("[data-report-empty]");
  const emptyTitle = root.querySelector("[data-empty-title]");
  const emptyDescription = root.querySelector("[data-empty-description]");
  const reportContent = root.querySelector("[data-report-content]");
  const activityValue = root.querySelector('[data-kpi="activities"]');
  const peopleValue = root.querySelector('[data-kpi="people"]');
  const householdHeadsValue = root.querySelector('[data-kpi="household-heads"]');
  const duplicateValue = root.querySelector('[data-kpi="duplicates"]');
  const townValue = root.querySelector('[data-kpi="towns"]');
  const ageChart = root.querySelector('[data-chart="age"]');
  const educationChart = root.querySelector('[data-chart="education"]');
  const gradesChart = root.querySelector('[data-chart="grades"]');
  const pregnancyWomenValue = root.querySelector('[data-pregnancy="women"]');
  const pregnancyMenValue = root.querySelector('[data-pregnancy="men"]');
  const pregnancyWorkshopValue = root.querySelector('[data-pregnancy="followups"]');
  const townTable = root.querySelector("[data-town-table]");
  const admSummaryFields = ["service_types", "services", "duplicates", "unique_participants"];
  const admSummaryValues = Object.fromEntries(
    admSummaryFields.map((field) => [field, root.querySelector(`[data-adm-summary="${field}"]`)]),
  );
  const admServiceTable = root.querySelector("[data-adm-service-table]");
  const admSociodemographicTable = root.querySelector("[data-adm-sociodemographic-table]");
  const admFamilyTable = root.querySelector("[data-adm-family-table]");
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
    || !householdHeadsValue
    || !duplicateValue
    || !townValue
    || !ageChart
    || !educationChart
    || !gradesChart
    || !pregnancyWomenValue
    || !pregnancyMenValue
    || !pregnancyWorkshopValue
    || !townTable
    || admSummaryFields.some((field) => !admSummaryValues[field])
    || !admServiceTable
    || !admSociodemographicTable
    || !admFamilyTable
    || !dataUrl
  ) {
    return;
  }

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

  const renderTableMessage = (tableBody, columnCount, message) => {
    tableBody.replaceChildren();
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = columnCount;
    cell.textContent = message;
    row.append(cell);
    tableBody.append(row);
  };

  const appendTextCell = (row, value, { heading = false } = {}) => {
    const cell = document.createElement(heading ? "th" : "td");
    if (heading) {
      cell.scope = "row";
    }
    cell.textContent = value;
    row.append(cell);
  };

  const renderAdmServiceTable = (rows) => {
    admServiceTable.replaceChildren();
    if (!rows.length) {
      renderTableMessage(
        admServiceTable,
        4,
        "No hay tipos de servicio ADM configurados para los filtros seleccionados.",
      );
      return;
    }

    rows.forEach((item) => {
      const row = document.createElement("tr");
      appendTextCell(row, item.service_type_name, { heading: true });
      appendTextCell(row, numberFormatter.format(item.services_count));
      appendTextCell(row, numberFormatter.format(item.duplicates));
      appendTextCell(row, numberFormatter.format(item.unique_participants));
      admServiceTable.append(row);
    });
  };

  const renderAdmSociodemographicTable = (rows, total) => {
    admSociodemographicTable.replaceChildren();
    if (!rows.length) {
      renderTableMessage(
        admSociodemographicTable,
        5,
        "No hay datos socio-demográficos ADM para los filtros seleccionados.",
      );
      return;
    }

    rows.forEach((item) => {
      const row = document.createElement("tr");
      appendTextCell(row, item.label, { heading: true });
      appendTextCell(row, numberFormatter.format(item.f));
      appendTextCell(row, numberFormatter.format(item.m));
      appendTextCell(row, `${item.percent.toFixed(2)}%`);
      appendTextCell(row, numberFormatter.format(item.vca));
      admSociodemographicTable.append(row);
    });

    const totalRow = document.createElement("tr");
    appendTextCell(totalRow, "TOTAL", { heading: true });
    appendTextCell(totalRow, numberFormatter.format(total.f));
    appendTextCell(totalRow, numberFormatter.format(total.m));
    appendTextCell(totalRow, `${total.total ? "100.00" : "0.00"}%`);
    appendTextCell(totalRow, numberFormatter.format(total.vca));
    admSociodemographicTable.append(totalRow);
  };

  const renderAdmFamilyTable = (rows, total) => {
    admFamilyTable.replaceChildren();
    if (!rows.length) {
      renderTableMessage(
        admFamilyTable,
        2,
        "No hay datos de composición familiar ADM para los filtros seleccionados.",
      );
      return;
    }

    rows.forEach((item) => {
      const row = document.createElement("tr");
      appendTextCell(row, item.label, { heading: true });
      appendTextCell(row, numberFormatter.format(item.count));
      admFamilyTable.append(row);
    });

    const totalRow = document.createElement("tr");
    appendTextCell(totalRow, "TOTAL", { heading: true });
    appendTextCell(totalRow, numberFormatter.format(total));
    admFamilyTable.append(totalRow);
  };

  const setAdmBusy = (isBusy) => {
    [admServiceTable, admSociodemographicTable, admFamilyTable].forEach((tableBody) => {
      if (isBusy) {
        tableBody.setAttribute("aria-busy", "true");
      } else {
        tableBody.removeAttribute("aria-busy");
      }
    });
  };

  const setAdmLoading = () => {
    admSummaryFields.forEach((field) => {
      admSummaryValues[field].textContent = "…";
    });
    renderTableMessage(admServiceTable, 4, "Consultando datos ADM reales…");
    renderTableMessage(admSociodemographicTable, 5, "Consultando datos ADM reales…");
    renderTableMessage(admFamilyTable, 2, "Consultando datos ADM reales…");
    setAdmBusy(true);
  };

  const clearAdmMetrics = () => {
    admSummaryFields.forEach((field) => {
      admSummaryValues[field].textContent = "—";
    });
    renderTableMessage(admServiceTable, 4, "No fue posible cargar datos ADM.");
    renderTableMessage(admSociodemographicTable, 5, "No fue posible cargar datos ADM.");
    renderTableMessage(admFamilyTable, 2, "No fue posible cargar datos ADM.");
    setAdmBusy(false);
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

  const showReportContent = () => {
    emptyState.hidden = true;
    reportContent.hidden = false;
  };

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

  const normalizeRealPregnancy = (payload) => {
    const source = payload?.real?.pregnancy;
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("La respuesta real de embarazo no tiene el formato esperado.");
    }

    const pregnancy = {};
    ["women", "men", "followups"].forEach((field) => {
      const value = source[field];
      if (!Number.isInteger(value) || value < 0) {
        throw new Error("La respuesta real de embarazo no tiene el formato esperado.");
      }
      pregnancy[field] = value;
    });
    return pregnancy;
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

  const normalizeRealAdm = (payload) => {
    const source = payload?.real?.adm;
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("La respuesta real ADM no tiene el formato esperado.");
    }

    const summarySource = source.summary;
    if (!summarySource || typeof summarySource !== "object" || Array.isArray(summarySource)) {
      throw new Error("El resumen real ADM no tiene el formato esperado.");
    }
    const summary = {};
    admSummaryFields.forEach((field) => {
      const value = summarySource[field];
      if (!Number.isInteger(value) || value < 0) {
        throw new Error("El resumen real ADM no tiene el formato esperado.");
      }
      summary[field] = value;
    });

    if (!Array.isArray(source.service_rows)) {
      throw new Error("Las filas de servicios ADM no tienen el formato esperado.");
    }
    const serviceRows = source.service_rows.map((item) => {
      const serviceTypeName = typeof item?.service_type_name === "string"
        ? item.service_type_name.trim()
        : "";
      if (
        !serviceTypeName
        || !Number.isInteger(item?.services_count)
        || item.services_count < 0
        || !Number.isInteger(item?.duplicates)
        || item.duplicates < 0
        || !Number.isInteger(item?.unique_participants)
        || item.unique_participants < 0
      ) {
        throw new Error("Las filas de servicios ADM no tienen el formato esperado.");
      }
      return {
        service_type_name: serviceTypeName,
        services_count: item.services_count,
        duplicates: item.duplicates,
        unique_participants: item.unique_participants,
      };
    });

    if (!Array.isArray(source.sociodemographic_rows)) {
      throw new Error("Las filas socio-demográficas ADM no tienen el formato esperado.");
    }
    const sociodemographicRows = source.sociodemographic_rows.map((item) => {
      const label = typeof item?.label === "string" ? item.label.trim() : "";
      if (
        !label
        || !Number.isInteger(item?.f)
        || item.f < 0
        || !Number.isInteger(item?.m)
        || item.m < 0
        || !Number.isInteger(item?.total)
        || item.total < 0
        || typeof item?.percent !== "number"
        || !Number.isFinite(item.percent)
        || item.percent < 0
        || !Number.isInteger(item?.vca)
        || item.vca < 0
      ) {
        throw new Error("Las filas socio-demográficas ADM no tienen el formato esperado.");
      }
      return { label, f: item.f, m: item.m, total: item.total, percent: item.percent, vca: item.vca };
    });

    const totalSource = source.sociodemographic_total;
    if (!totalSource || typeof totalSource !== "object" || Array.isArray(totalSource)) {
      throw new Error("El total socio-demográfico ADM no tiene el formato esperado.");
    }
    const sociodemographicTotal = {};
    ["f", "m", "total", "vca"].forEach((field) => {
      const value = totalSource[field];
      if (!Number.isInteger(value) || value < 0) {
        throw new Error("El total socio-demográfico ADM no tiene el formato esperado.");
      }
      sociodemographicTotal[field] = value;
    });

    if (!Array.isArray(source.family_rows)) {
      throw new Error("Las filas de composición familiar ADM no tienen el formato esperado.");
    }
    const familyRows = source.family_rows.map((item) => {
      const label = typeof item?.label === "string" ? item.label.trim() : "";
      if (!label || !Number.isInteger(item?.count) || item.count < 0) {
        throw new Error("Las filas de composición familiar ADM no tienen el formato esperado.");
      }
      return { label, count: item.count };
    });
    if (!Number.isInteger(source.family_total) || source.family_total < 0) {
      throw new Error("El total de composición familiar ADM no tiene el formato esperado.");
    }

    return {
      summary,
      serviceRows,
      sociodemographicRows,
      sociodemographicTotal,
      familyRows,
      familyTotal: source.family_total,
    };
  };

  const clearRealMetrics = () => {
    activityValue.textContent = "—";
    peopleValue.textContent = "—";
    householdHeadsValue.textContent = "—";
    duplicateValue.textContent = "—";
    townValue.textContent = "—";
    ageChart.replaceChildren();
    ageChart.removeAttribute("aria-busy");
    educationChart.replaceChildren();
    educationChart.removeAttribute("aria-busy");
    gradesChart.replaceChildren();
    gradesChart.removeAttribute("aria-busy");
    pregnancyWomenValue.textContent = "—";
    pregnancyMenValue.textContent = "—";
    pregnancyWorkshopValue.textContent = "—";
    renderTownTable({}, "No fue posible cargar los municipios reales.");
    townTable.removeAttribute("aria-busy");
    clearAdmMetrics();
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
      showEmptyState(
        "Revise el rango de fechas",
        "La fecha inicial debe ser anterior o igual a la fecha final.",
      );
      setStatus("La fecha inicial no puede ser posterior a la fecha final.", true);
      return;
    }

    showReportContent();
    activityValue.textContent = "…";
    peopleValue.textContent = "…";
    householdHeadsValue.textContent = "…";
    duplicateValue.textContent = "…";
    townValue.textContent = "…";
    pregnancyWomenValue.textContent = "…";
    pregnancyMenValue.textContent = "…";
    pregnancyWorkshopValue.textContent = "…";
    renderBars(ageChart, {}, { emptyMessage: "Consultando distribución real…" });
    ageChart.setAttribute("aria-busy", "true");
    renderBars(educationChart, {}, { emptyMessage: "Consultando escolaridad real…" });
    educationChart.setAttribute("aria-busy", "true");
    renderBars(gradesChart, {}, { emptyMessage: "Consultando notas reales…" });
    gradesChart.setAttribute("aria-busy", "true");
    renderTownTable({}, "Consultando municipios reales…");
    townTable.setAttribute("aria-busy", "true");
    setAdmLoading();
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
      const householdHeads = payload?.real?.household_heads;
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
      if (
        !Number.isInteger(householdHeads)
        || householdHeads < 0
        || householdHeads > people
      ) {
        throw new Error("La cantidad real de jefes de familia no tiene el formato esperado.");
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
      const pregnancy = normalizeRealPregnancy(payload);
      const municipalities = normalizeRealMunicipalities(payload);
      const adm = normalizeRealAdm(payload);
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
      householdHeadsValue.textContent = numberFormatter.format(householdHeads);
      duplicateValue.textContent = numberFormatter.format(duplicates);
      townValue.textContent = numberFormatter.format(towns);
      renderBars(ageChart, ageBuckets);
      renderBars(educationChart, education);
      renderBars(gradesChart, grades, { maximum: 100, suffix: "%" });
      pregnancyWomenValue.textContent = numberFormatter.format(pregnancy.women);
      pregnancyMenValue.textContent = numberFormatter.format(pregnancy.men);
      pregnancyWorkshopValue.textContent = numberFormatter.format(pregnancy.followups);
      renderTownTable(municipalities);
      admSummaryFields.forEach((field) => {
        admSummaryValues[field].textContent = numberFormatter.format(adm.summary[field]);
      });
      renderAdmServiceTable(adm.serviceRows);
      renderAdmSociodemographicTable(adm.sociodemographicRows, adm.sociodemographicTotal);
      renderAdmFamilyTable(adm.familyRows, adm.familyTotal);
      const proposalLabel = proposalIds.length === 1 ? "1 propuesta" : `${proposalIds.length} propuestas`;
      setStatus(`Indicadores reales actualizados para ${proposalLabel}.`);
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
        setAdmBusy(false);
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
