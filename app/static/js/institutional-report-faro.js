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
  const householdRing = root.querySelector("[data-household-ring]");
  const householdRingValue = root.querySelector("[data-household-ring-value]");
  const householdRingLabel = root.querySelector("[data-household-ring-label]");
  const pregnancyWomenValue = root.querySelector('[data-pregnancy="women"]');
  const pregnancyMenValue = root.querySelector('[data-pregnancy="men"]');
  const pregnancyWorkshopValue = root.querySelector('[data-pregnancy="followups"]');
  const townTable = root.querySelector("[data-town-table]");
  const townHighlight = root.querySelector("[data-town-highlight]");
  const townHighlightValue = root.querySelector("[data-town-highlight-value]");
  const municipalityMap = root.querySelector("[data-municipality-map]");
  const municipalityMapStage = root.querySelector("[data-municipality-map-stage]");
  const municipalityMapTooltip = root.querySelector("[data-municipality-map-tooltip]");
  const municipalityMapUrl = "/static/img/maps/puerto-rico-municipalities.svg";
  const admSummaryFields = ["service_types", "services", "duplicates", "unique_participants"];
  const admVisibleSummaryFields = ["services", "duplicates", "unique_participants"];
  const admSummaryValues = Object.fromEntries(
    admVisibleSummaryFields.map((field) => [field, root.querySelector(`[data-adm-summary="${field}"]`)]),
  );
  const admServiceTable = root.querySelector("[data-adm-service-table]");
  const admSociodemographicTable = root.querySelector("[data-adm-sociodemographic-table]");
  const admFamilyTable = root.querySelector("[data-adm-family-table]");
  const submitButton = form?.querySelector('button[type="submit"]');
  const dataUrl = root.dataset.reportDataUrl;
  const numberFormatter = new Intl.NumberFormat("es-PR");
  const percentFormatter = new Intl.NumberFormat("es-PR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  const ageBucketLabels = ["0 a 12", "13 a 18", "19 a 59", "60 o más", "No informado"];
  const gradeSubjectLabels = ["Español", "Matemáticas", "Ciencias", "Inglés"];
  let activeRequest = null;
  let municipalityMapSvgPromise = null;
  let municipalityMapRenderToken = 0;

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
    || !householdRing
    || !householdRingValue
    || !householdRingLabel
    || !pregnancyWomenValue
    || !pregnancyMenValue
    || !pregnancyWorkshopValue
    || !townTable
    || admVisibleSummaryFields.some((field) => !admSummaryValues[field])
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
    const total = Number.isFinite(options.total)
      ? options.total
      : entries.reduce((sum, [, value]) => sum + value, 0);

    entries.forEach(([label, value]) => {
      const row = document.createElement("div");
      row.className = "institutional-report-bar";

      const heading = document.createElement("div");
      heading.className = "institutional-report-bar__heading";

      const labelElement = document.createElement("span");
      labelElement.textContent = label;
      const valueElement = document.createElement("strong");
      const formattedValue = options.suffix
        ? `${numberFormatter.format(value)}${options.suffix}`
        : numberFormatter.format(value);
      const percent = total > 0 ? (value / total) * 100 : 0;
      valueElement.textContent = options.showPercent
        ? `${formattedValue} · ${percentFormatter.format(percent)}%`
        : formattedValue;
      heading.append(labelElement, valueElement);

      const track = document.createElement("div");
      track.className = "institutional-report-bar__track";
      const bar = document.createElement("div");
      bar.className = "institutional-report-bar__value";
      if (options.tone) {
        bar.classList.add(`institutional-report-bar__value--${options.tone}`);
      }
      const width = value === 0 ? 0 : Math.max(4, Math.min(100, (value / maximum) * 100));
      bar.style.setProperty("--institutional-report-bar-width", `${width}%`);
      bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", `${label}: ${valueElement.textContent}`);
      track.append(bar);

      row.append(heading, track);
      container.append(row);
    });
  };

  const renderEducationChart = (values, emptyMessage = "No hay datos para mostrar.") => {
    educationChart.replaceChildren();
    const entries = Object.entries(values);
    if (!entries.length) {
      const message = document.createElement("p");
      message.className = "institutional-report-filter__empty";
      message.textContent = emptyMessage;
      educationChart.append(message);
      return;
    }

    const palette = ["#0d3b66", "#2a9d8f", "#67b7ab", "#b9822b", "#7c8fa3", "#b5c5d3"];
    const total = entries.reduce((sum, [, value]) => sum + value, 0);
    let cursor = 0;
    const segments = entries.map(([, value], index) => {
      const start = cursor;
      cursor += total > 0 ? (value / total) * 100 : 0;
      return `${palette[index % palette.length]} ${start}% ${cursor}%`;
    });

    const chartLayout = document.createElement("div");
    chartLayout.className = "institutional-report-donut-layout";
    const donut = document.createElement("div");
    donut.className = "institutional-report-donut";
    donut.style.background = total > 0
      ? `conic-gradient(${segments.join(", ")})`
      : "#e7eef4";
    donut.setAttribute("role", "img");
    donut.setAttribute("aria-label", `Escolaridad: ${numberFormatter.format(total)} personas`);
    const center = document.createElement("div");
    center.className = "institutional-report-donut__center";
    const totalValue = document.createElement("strong");
    totalValue.textContent = numberFormatter.format(total);
    const totalLabel = document.createElement("span");
    totalLabel.textContent = "personas";
    center.append(totalValue, totalLabel);
    donut.append(center);

    const legend = document.createElement("div");
    legend.className = "institutional-report-donut-legend";
    entries.forEach(([label, value], index) => {
      const item = document.createElement("div");
      item.className = "institutional-report-donut-legend__item";
      const name = document.createElement("span");
      const swatch = document.createElement("i");
      swatch.style.backgroundColor = palette[index % palette.length];
      const text = document.createElement("span");
      text.textContent = label;
      name.append(swatch, text);
      const amount = document.createElement("strong");
      const percent = total > 0 ? (value / total) * 100 : 0;
      amount.textContent = `${numberFormatter.format(value)} · ${percentFormatter.format(percent)}%`;
      item.append(name, amount);
      legend.append(item);
    });

    chartLayout.append(donut, legend);
    educationChart.append(chartLayout);
  };

  const renderGradesChart = (values, emptyMessage = "No hay datos para mostrar.") => {
    gradesChart.replaceChildren();
    const entries = Object.entries(values);
    if (!entries.length) {
      const message = document.createElement("p");
      message.className = "institutional-report-filter__empty";
      message.textContent = emptyMessage;
      gradesChart.append(message);
      return;
    }

    const target = document.createElement("p");
    target.className = "institutional-report-grade-target";
    target.innerHTML = '<span aria-hidden="true"></span> Referencia visual: 70 puntos';
    gradesChart.append(target);
    entries.forEach(([label, value]) => {
      const item = document.createElement("div");
      item.className = "institutional-report-grade";
      const heading = document.createElement("div");
      heading.className = "institutional-report-grade__heading";
      const name = document.createElement("span");
      name.textContent = label;
      const score = document.createElement("strong");
      score.textContent = `${numberFormatter.format(value)}%`;
      heading.append(name, score);
      const track = document.createElement("div");
      track.className = "institutional-report-grade__track";
      const marker = document.createElement("span");
      marker.className = "institutional-report-grade__target";
      marker.setAttribute("aria-hidden", "true");
      const bar = document.createElement("span");
      bar.className = "institutional-report-grade__value";
      bar.style.setProperty("--institutional-report-grade-width", `${value}%`);
      track.append(bar, marker);
      item.append(heading, track);
      gradesChart.append(item);
    });
  };

  const updateHouseholdRing = (householdHeads, people) => {
    const percent = people > 0 ? (householdHeads / people) * 100 : 0;
    householdRing.style.setProperty("--institutional-report-ring-percent", `${percent}%`);
    householdRingValue.textContent = `${percentFormatter.format(percent)}%`;
    householdRingLabel.textContent = `${numberFormatter.format(householdHeads)} de ${numberFormatter.format(people)} personas únicas`;
    householdRing.setAttribute(
      "aria-label",
      `Jefes de familia: ${numberFormatter.format(householdHeads)} de ${numberFormatter.format(people)}, ${percentFormatter.format(percent)} por ciento`,
    );
  };

  const setHouseholdRingMessage = (value, message) => {
    householdRing.style.setProperty("--institutional-report-ring-percent", "0%");
    householdRingValue.textContent = value;
    householdRingLabel.textContent = message;
    householdRing.setAttribute("aria-label", message);
  };

  function normalizeMunicipality(value = "") {
    return String(value)
      .trim()
      .toLocaleLowerCase("es-PR")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ");
  }

  const municipalityMapIsAvailable = () => Boolean(
    municipalityMap && municipalityMapStage && municipalityMapTooltip
  );

  const hideMunicipalityMapTooltip = () => {
    if (!municipalityMapTooltip) {
      return;
    }
    municipalityMapTooltip.hidden = true;
    municipalityMapTooltip.textContent = "";
    municipalityMapTooltip.style.removeProperty("left");
    municipalityMapTooltip.style.removeProperty("top");
  };

  const replaceMunicipalityMapWithStatus = (message, isError = false) => {
    if (!municipalityMapIsAvailable()) {
      return;
    }
    hideMunicipalityMapTooltip();
    const status = document.createElement("p");
    status.className = "institutional-report-map__status";
    if (isError) {
      status.classList.add("institutional-report-map__status--error");
    }
    status.setAttribute("role", "status");
    status.textContent = message;
    municipalityMapStage.replaceChildren(status);
  };

  const setMunicipalityMapStatus = (message, isError = false) => {
    municipalityMapRenderToken += 1;
    replaceMunicipalityMapWithStatus(message, isError);
  };

  const loadMunicipalityMapSvg = () => {
    if (!municipalityMapIsAvailable()) {
      return Promise.resolve(null);
    }
    if (!municipalityMapSvgPromise) {
      municipalityMapSvgPromise = (async () => {
        const response = await fetch(municipalityMapUrl, { credentials: "same-origin" });
        if (!response.ok) {
          throw new Error(`No fue posible consultar el SVG municipal (${response.status}).`);
        }
        const svgText = await response.text();
        const parsedDocument = new DOMParser().parseFromString(svgText, "image/svg+xml");
        if (parsedDocument.querySelector("parsererror")) {
          throw new Error("El SVG municipal no tiene un formato válido.");
        }
        const svg = parsedDocument.querySelector("svg");
        if (!svg || !svg.querySelector("[data-municipality]")) {
          throw new Error("El SVG municipal no contiene municipios identificables.");
        }
        return svg;
      })();
    }
    return municipalityMapSvgPromise;
  };

  const positionMunicipalityMapTooltip = (municipalityPath, event) => {
    if (!municipalityMapIsAvailable() || municipalityMapTooltip.hidden) {
      return;
    }
    const mapRect = municipalityMap.getBoundingClientRect();
    const pathRect = municipalityPath.getBoundingClientRect();
    const clientX = Number.isFinite(event?.clientX)
      ? event.clientX
      : pathRect.left + (pathRect.width / 2);
    const clientY = Number.isFinite(event?.clientY)
      ? event.clientY
      : pathRect.top + (pathRect.height / 2);
    const tooltipRect = municipalityMapTooltip.getBoundingClientRect();
    const margin = 8;
    const maximumLeft = Math.max(margin, mapRect.width - tooltipRect.width - margin);
    const left = Math.min(
      maximumLeft,
      Math.max(margin, clientX - mapRect.left - (tooltipRect.width / 2)),
    );
    let top = clientY - mapRect.top - tooltipRect.height - 12;
    if (top < margin) {
      top = clientY - mapRect.top + 12;
    }
    municipalityMapTooltip.style.left = `${left}px`;
    municipalityMapTooltip.style.top = `${top}px`;
  };

  const showMunicipalityMapTooltip = (municipalityPath, event) => {
    if (!municipalityMapIsAvailable()) {
      return;
    }
    municipalityMapTooltip.textContent = municipalityPath.dataset.mapTooltip || "";
    municipalityMapTooltip.hidden = false;
    positionMunicipalityMapTooltip(municipalityPath, event);
  };

  const renderMunicipalityMap = async (townsByMunicipality) => {
    if (!municipalityMapIsAvailable()) {
      return;
    }
    const renderToken = ++municipalityMapRenderToken;
    replaceMunicipalityMapWithStatus("Consultando mapa municipal…");

    try {
      const svgTemplate = await loadMunicipalityMapSvg();
      if (renderToken !== municipalityMapRenderToken || !svgTemplate) {
        return;
      }

      const normalizedCounts = new Map();
      Object.entries(townsByMunicipality || {}).forEach(([municipality, value]) => {
        const normalizedName = normalizeMunicipality(municipality);
        if (!normalizedName || normalizedName === normalizeMunicipality("No informado")) {
          return;
        }
        const numericValue = Number(value);
        const count = Number.isFinite(numericValue) ? Math.max(0, Math.trunc(numericValue)) : 0;
        normalizedCounts.set(normalizedName, (normalizedCounts.get(normalizedName) || 0) + count);
      });

      const svg = document.importNode(svgTemplate, true);
      const municipalityPaths = svg.querySelectorAll("[data-municipality]");
      if (!municipalityPaths.length) {
        throw new Error("El SVG municipal no contiene municipios identificables.");
      }

      svg.setAttribute("role", "group");
      svg.setAttribute("aria-label", "Mapa de Puerto Rico por municipios");
      municipalityPaths.forEach((municipalityPath) => {
        const municipalityName = String(municipalityPath.dataset.municipality || "").trim();
        const count = normalizedCounts.get(normalizeMunicipality(municipalityName)) || 0;
        const isActive = count > 0;
        const countLabel = count === 1 ? "1 persona única" : `${numberFormatter.format(count)} personas únicas`;
        const tooltipText = isActive
          ? `${municipalityName}: ${countLabel}`
          : `${municipalityName}: sin participación registrada`;

        municipalityPath.classList.add("institutional-report-map__municipality");
        municipalityPath.classList.toggle("institutional-report-map__municipality--active", isActive);
        municipalityPath.classList.toggle("institutional-report-map__municipality--inactive", !isActive);
        municipalityPath.setAttribute("tabindex", "0");
        municipalityPath.setAttribute("role", "img");
        municipalityPath.setAttribute("aria-label", tooltipText);
        municipalityPath.dataset.mapTooltip = tooltipText;
        municipalityPath.addEventListener("pointerenter", (event) => {
          showMunicipalityMapTooltip(municipalityPath, event);
        });
        municipalityPath.addEventListener("pointermove", (event) => {
          positionMunicipalityMapTooltip(municipalityPath, event);
        });
        municipalityPath.addEventListener("pointerleave", () => {
          if (document.activeElement !== municipalityPath) {
            hideMunicipalityMapTooltip();
          }
        });
        municipalityPath.addEventListener("focus", () => {
          showMunicipalityMapTooltip(municipalityPath);
        });
        municipalityPath.addEventListener("blur", hideMunicipalityMapTooltip);
        municipalityPath.addEventListener("click", () => {
          municipalityPath.focus();
          showMunicipalityMapTooltip(municipalityPath);
        });
        municipalityPath.addEventListener("keydown", (event) => {
          if (event.key === "Escape") {
            hideMunicipalityMapTooltip();
            municipalityPath.blur();
          }
        });
      });

      municipalityMapStage.replaceChildren(svg);
    } catch (_error) {
      if (renderToken === municipalityMapRenderToken) {
        replaceMunicipalityMapWithStatus(
          "No fue posible cargar el mapa municipal. El ranking permanece disponible.",
          true,
        );
      }
    }
  };

  const renderTownTable = (towns, emptyMessage = "No hay datos para mostrar.") => {
    townTable.replaceChildren();
    if (townHighlight) {
      townHighlight.hidden = true;
    }

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

    const sortedEntries = entries
      .sort(([firstLabel, firstValue], [secondLabel, secondValue]) => {
        if (firstLabel === "No informado") return 1;
        if (secondLabel === "No informado") return -1;
        return secondValue - firstValue || firstLabel.localeCompare(secondLabel, "es");
      });
    const maximum = Math.max(...sortedEntries.map(([, value]) => value), 1);
    const topTown = sortedEntries.find(([label, value]) => label !== "No informado" && value > 0);
    if (townHighlight && townHighlightValue && topTown) {
      townHighlightValue.textContent = `${topTown[0]} · ${numberFormatter.format(topTown[1])} personas`;
      townHighlight.hidden = false;
    }

    sortedEntries.forEach(([town, value]) => {
        const row = document.createElement("tr");
        const townCell = document.createElement("th");
        townCell.scope = "row";
        townCell.textContent = town;
        const valueCell = document.createElement("td");
        const visual = document.createElement("div");
        visual.className = "institutional-report-town-value";
        const track = document.createElement("span");
        track.className = "institutional-report-town-value__track";
        const bar = document.createElement("span");
        bar.className = "institutional-report-town-value__bar";
        bar.style.setProperty("--institutional-report-town-width", `${(value / maximum) * 100}%`);
        const amount = document.createElement("strong");
        amount.textContent = numberFormatter.format(value);
        track.append(bar);
        visual.append(track, amount);
        valueCell.append(visual);
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
    return cell;
  };

  const renderAdmServiceTable = (rows) => {
    admServiceTable.replaceChildren();
    if (!rows.length) {
      renderTableMessage(
        admServiceTable,
        4,
        "No hay tipos de servicio administrativo configurados para los filtros seleccionados.",
      );
      return;
    }

    const maximum = Math.max(...rows.map((item) => item.services_count), 1);
    rows.forEach((item) => {
      const row = document.createElement("tr");
      const serviceCell = appendTextCell(row, item.service_type_name, { heading: true });
      const visual = document.createElement("span");
      visual.className = "institutional-report-adm-inline-bar";
      visual.style.setProperty(
        "--institutional-report-adm-bar-width",
        `${(item.services_count / maximum) * 100}%`,
      );
      serviceCell.append(visual);
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
        "No hay datos socio-demográficos administrativos para los filtros seleccionados.",
      );
      return;
    }

    rows.forEach((item) => {
      const row = document.createElement("tr");
      const labelCell = appendTextCell(row, item.label, { heading: true });
      const genderTotal = item.f + item.m;
      const stack = document.createElement("span");
      stack.className = "institutional-report-adm-gender-stack";
      const female = document.createElement("i");
      female.className = "institutional-report-adm-gender-stack__f";
      female.style.width = `${genderTotal ? (item.f / genderTotal) * 100 : 0}%`;
      const male = document.createElement("i");
      male.className = "institutional-report-adm-gender-stack__m";
      male.style.width = `${genderTotal ? (item.m / genderTotal) * 100 : 0}%`;
      stack.append(female, male);
      labelCell.append(stack);
      appendTextCell(row, numberFormatter.format(item.f));
      appendTextCell(row, numberFormatter.format(item.m));
      appendTextCell(row, `${item.percent.toFixed(2)}%`);
      appendTextCell(row, numberFormatter.format(item.vca));
      admSociodemographicTable.append(row);
    });

    const totalRow = document.createElement("tr");
    totalRow.className = "institutional-report-table__total";
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
        "No hay datos de composición familiar administrativa para los filtros seleccionados.",
      );
      return;
    }

    const maximum = Math.max(...rows.map((item) => item.count), 1);
    rows.forEach((item) => {
      const row = document.createElement("tr");
      const familyCell = appendTextCell(row, item.label, { heading: true });
      const visual = document.createElement("span");
      visual.className = "institutional-report-adm-inline-bar institutional-report-adm-inline-bar--gold";
      visual.style.setProperty(
        "--institutional-report-adm-bar-width",
        `${(item.count / maximum) * 100}%`,
      );
      familyCell.append(visual);
      appendTextCell(row, numberFormatter.format(item.count));
      admFamilyTable.append(row);
    });

    const totalRow = document.createElement("tr");
    totalRow.className = "institutional-report-table__total";
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
    admVisibleSummaryFields.forEach((field) => {
      admSummaryValues[field].textContent = "…";
    });
    renderTableMessage(admServiceTable, 4, "Consultando datos administrativos…");
    renderTableMessage(admSociodemographicTable, 5, "Consultando datos administrativos…");
    renderTableMessage(admFamilyTable, 2, "Consultando datos administrativos…");
    setAdmBusy(true);
  };

  const clearAdmMetrics = () => {
    admVisibleSummaryFields.forEach((field) => {
      admSummaryValues[field].textContent = "—";
    });
    renderTableMessage(admServiceTable, 4, "No fue posible cargar datos administrativos.");
    renderTableMessage(admSociodemographicTable, 5, "No fue posible cargar datos administrativos.");
    renderTableMessage(admFamilyTable, 2, "No fue posible cargar datos administrativos.");
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
      throw new Error("La respuesta administrativa no tiene el formato esperado.");
    }

    const summarySource = source.summary;
    if (!summarySource || typeof summarySource !== "object" || Array.isArray(summarySource)) {
      throw new Error("El resumen administrativo no tiene el formato esperado.");
    }
    const summary = {};
    admSummaryFields.forEach((field) => {
      const value = summarySource[field];
      if (!Number.isInteger(value) || value < 0) {
        throw new Error("El resumen administrativo no tiene el formato esperado.");
      }
      summary[field] = value;
    });

    if (!Array.isArray(source.service_rows)) {
      throw new Error("Las filas de servicios administrativos no tienen el formato esperado.");
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
        throw new Error("Las filas de servicios administrativos no tienen el formato esperado.");
      }
      return {
        service_type_name: serviceTypeName,
        services_count: item.services_count,
        duplicates: item.duplicates,
        unique_participants: item.unique_participants,
      };
    });

    if (!Array.isArray(source.sociodemographic_rows)) {
      throw new Error("Las filas socio-demográficas administrativas no tienen el formato esperado.");
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
        throw new Error("Las filas socio-demográficas administrativas no tienen el formato esperado.");
      }
      return { label, f: item.f, m: item.m, total: item.total, percent: item.percent, vca: item.vca };
    });

    const totalSource = source.sociodemographic_total;
    if (!totalSource || typeof totalSource !== "object" || Array.isArray(totalSource)) {
      throw new Error("El total socio-demográfico administrativo no tiene el formato esperado.");
    }
    const sociodemographicTotal = {};
    ["f", "m", "total", "vca"].forEach((field) => {
      const value = totalSource[field];
      if (!Number.isInteger(value) || value < 0) {
        throw new Error("El total socio-demográfico administrativo no tiene el formato esperado.");
      }
      sociodemographicTotal[field] = value;
    });

    if (!Array.isArray(source.family_rows)) {
      throw new Error("Las filas de composición familiar administrativas no tienen el formato esperado.");
    }
    const familyRows = source.family_rows.map((item) => {
      const label = typeof item?.label === "string" ? item.label.trim() : "";
      if (!label || !Number.isInteger(item?.count) || item.count < 0) {
        throw new Error("Las filas de composición familiar administrativas no tienen el formato esperado.");
      }
      return { label, count: item.count };
    });
    if (!Number.isInteger(source.family_total) || source.family_total < 0) {
      throw new Error("El total de composición familiar administrativo no tiene el formato esperado.");
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
    setHouseholdRingMessage("—", "No fue posible calcular la proporción real.");
    renderBars(ageChart, {}, { emptyMessage: "No fue posible cargar la distribución por edad." });
    ageChart.removeAttribute("aria-busy");
    renderEducationChart({}, "No fue posible cargar la escolaridad real.");
    educationChart.removeAttribute("aria-busy");
    renderGradesChart({}, "No fue posible cargar las notas reales.");
    gradesChart.removeAttribute("aria-busy");
    pregnancyWomenValue.textContent = "—";
    pregnancyMenValue.textContent = "—";
    pregnancyWorkshopValue.textContent = "—";
    renderTownTable({}, "No fue posible cargar los municipios reales.");
    townTable.removeAttribute("aria-busy");
    setMunicipalityMapStatus(
      "No fue posible cargar el mapa municipal. El ranking permanece disponible.",
      true,
    );
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
    setHouseholdRingMessage("…", "Consultando proporción real…");
    renderBars(ageChart, {}, { emptyMessage: "Consultando distribución real…" });
    ageChart.setAttribute("aria-busy", "true");
    renderEducationChart({}, "Consultando escolaridad real…");
    educationChart.setAttribute("aria-busy", "true");
    renderGradesChart({}, "Consultando notas reales…");
    gradesChart.setAttribute("aria-busy", "true");
    renderTownTable({}, "Consultando municipios reales…");
    townTable.setAttribute("aria-busy", "true");
    setMunicipalityMapStatus("Consultando mapa municipal…");
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
      updateHouseholdRing(householdHeads, people);
      renderBars(ageChart, ageBuckets, { total: people, showPercent: true });
      renderEducationChart(education);
      renderGradesChart(grades);
      pregnancyWomenValue.textContent = numberFormatter.format(pregnancy.women);
      pregnancyMenValue.textContent = numberFormatter.format(pregnancy.men);
      pregnancyWorkshopValue.textContent = numberFormatter.format(pregnancy.followups);
      renderTownTable(municipalities);
      void renderMunicipalityMap(municipalities);
      admVisibleSummaryFields.forEach((field) => {
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
