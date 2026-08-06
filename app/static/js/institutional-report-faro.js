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
      people: 74,
      duplicates: 9,
      activities: 18,
      age: { "0 a 12": 18, "13 a 18": 21, "19 a 59": 29, "60 o más": 6 },
      education: { Elemental: 22, Intermedia: 18, Superior: 13, "No informado": 21 },
      grades: { Español: 81, Matemáticas: 77, Inglés: 79, Ciencias: 83 },
      pregnancy: { women: 3, men: 2, followups: 8 },
      towns: { "Pueblo Norte": 28, "Pueblo Central": 31, "Pueblo Sur": 15 },
    },
    {
      proposal: "demo-b",
      date: "2025-06-15",
      people: 69,
      duplicates: 7,
      activities: 16,
      age: { "0 a 12": 15, "13 a 18": 19, "19 a 59": 28, "60 o más": 7 },
      education: { Elemental: 19, Intermedia: 17, Superior: 14, "No informado": 19 },
      grades: { Español: 83, Matemáticas: 79, Inglés: 80, Ciencias: 82 },
      pregnancy: { women: 2, men: 2, followups: 6 },
      towns: { "Pueblo Central": 27, "Pueblo Este": 24, "Pueblo Sur": 18 },
    },
    {
      proposal: "demo-a",
      date: "2026-01-15",
      people: 82,
      duplicates: 10,
      activities: 20,
      age: { "0 a 12": 20, "13 a 18": 24, "19 a 59": 31, "60 o más": 7 },
      education: { Elemental: 25, Intermedia: 20, Superior: 15, "No informado": 22 },
      grades: { Español: 82, Matemáticas: 78, Inglés: 81, Ciencias: 84 },
      pregnancy: { women: 3, men: 2, followups: 7 },
      towns: { "Pueblo Norte": 29, "Pueblo Central": 34, "Pueblo Oeste": 19 },
    },
    {
      proposal: "demo-b",
      date: "2026-03-15",
      people: 77,
      duplicates: 8,
      activities: 19,
      age: { "0 a 12": 17, "13 a 18": 22, "19 a 59": 32, "60 o más": 6 },
      education: { Elemental: 21, Intermedia: 19, Superior: 17, "No informado": 20 },
      grades: { Español: 84, Matemáticas: 80, Inglés: 82, Ciencias: 85 },
      pregnancy: { women: 3, men: 1, followups: 8 },
      towns: { "Pueblo Central": 30, "Pueblo Este": 28, "Pueblo Sur": 19 },
    },
    {
      proposal: "demo-a",
      date: "2026-04-15",
      people: 91,
      duplicates: 11,
      activities: 23,
      age: { "0 a 12": 23, "13 a 18": 25, "19 a 59": 35, "60 o más": 8 },
      education: { Elemental: 27, Intermedia: 22, Superior: 18, "No informado": 24 },
      grades: { Español: 85, Matemáticas: 81, Inglés: 83, Ciencias: 86 },
      pregnancy: { women: 4, men: 2, followups: 10 },
      towns: { "Pueblo Norte": 32, "Pueblo Central": 36, "Pueblo Oeste": 23 },
    },
    {
      proposal: "demo-a",
      date: "2026-05-15",
      people: 88,
      duplicates: 9,
      activities: 21,
      age: { "0 a 12": 21, "13 a 18": 24, "19 a 59": 36, "60 o más": 7 },
      education: { Elemental: 24, Intermedia: 23, Superior: 18, "No informado": 23 },
      grades: { Español: 86, Matemáticas: 82, Inglés: 84, Ciencias: 87 },
      pregnancy: { women: 3, men: 3, followups: 9 },
      towns: { "Pueblo Norte": 30, "Pueblo Central": 35, "Pueblo Sur": 23 },
    },
    {
      proposal: "demo-b",
      date: "2026-06-15",
      people: 95,
      duplicates: 12,
      activities: 24,
      age: { "0 a 12": 24, "13 a 18": 27, "19 a 59": 37, "60 o más": 7 },
      education: { Elemental: 28, Intermedia: 24, Superior: 20, "No informado": 23 },
      grades: { Español: 84, Matemáticas: 83, Inglés: 85, Ciencias: 86 },
      pregnancy: { women: 5, men: 2, followups: 12 },
      towns: { "Pueblo Central": 37, "Pueblo Este": 34, "Pueblo Sur": 24 },
    },
    {
      proposal: "demo-b",
      date: "2026-07-15",
      people: 102,
      duplicates: 13,
      activities: 26,
      age: { "0 a 12": 25, "13 a 18": 29, "19 a 59": 40, "60 o más": 8 },
      education: { Elemental: 29, Intermedia: 26, Superior: 21, "No informado": 26 },
      grades: { Español: 86, Matemáticas: 84, Inglés: 85, Ciencias: 88 },
      pregnancy: { women: 4, men: 3, followups: 11 },
      towns: { "Pueblo Norte": 28, "Pueblo Central": 39, "Pueblo Este": 35 },
    },
  ];

  const form = root.querySelector("[data-report-filter-form]");
  const statusMessage = root.querySelector("[data-filter-status]");
  const emptyState = root.querySelector("[data-report-empty]");
  const reportContent = root.querySelector("[data-report-content]");
  const numberFormatter = new Intl.NumberFormat("es-PR");

  const addValues = (target, source) => {
    Object.entries(source).forEach(([label, value]) => {
      target[label] = (target[label] || 0) + value;
    });
  };

  const aggregateRecords = (records) => {
    const aggregate = {
      people: 0,
      duplicates: 0,
      activities: 0,
      age: {},
      education: {},
      gradeTotals: {},
      gradeCounts: {},
      pregnancy: { women: 0, men: 0, followups: 0 },
      towns: {},
    };

    records.forEach((record) => {
      aggregate.people += record.people;
      aggregate.duplicates += record.duplicates;
      aggregate.activities += record.activities;
      addValues(aggregate.age, record.age);
      addValues(aggregate.education, record.education);
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
      const width = Math.max(4, Math.min(100, (value / maximum) * 100));
      bar.style.setProperty("--institutional-report-bar-width", `${width}%`);
      bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", `${label}: ${valueElement.textContent}`);
      track.append(bar);

      row.append(heading, track);
      container.append(row);
    });
  };

  const renderTownTable = (towns) => {
    const tableBody = root.querySelector("[data-town-table]");
    tableBody.replaceChildren();

    Object.entries(towns)
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

  const renderDashboard = (records) => {
    const hasRecords = records.length > 0;
    emptyState.hidden = hasRecords;
    reportContent.hidden = !hasRecords;

    const aggregate = aggregateRecords(records);
    root.querySelector('[data-kpi="people"]').textContent = numberFormatter.format(aggregate.people);
    root.querySelector('[data-kpi="duplicates"]').textContent = numberFormatter.format(aggregate.duplicates);
    root.querySelector('[data-kpi="activities"]').textContent = numberFormatter.format(aggregate.activities);
    root.querySelector('[data-kpi="towns"]').textContent = numberFormatter.format(aggregate.townCount);

    root.querySelector('[data-pregnancy="women"]').textContent = numberFormatter.format(aggregate.pregnancy.women);
    root.querySelector('[data-pregnancy="men"]').textContent = numberFormatter.format(aggregate.pregnancy.men);
    root.querySelector('[data-pregnancy="followups"]').textContent = numberFormatter.format(
      aggregate.pregnancy.followups,
    );

    if (!hasRecords) {
      return;
    }

    renderBars(root.querySelector('[data-chart="age"]'), aggregate.age);
    renderBars(root.querySelector('[data-chart="education"]'), aggregate.education);
    renderBars(root.querySelector('[data-chart="grades"]'), aggregate.grades, { maximum: 100, suffix: "%" });
    renderTownTable(aggregate.towns);
  };

  const applyFilters = () => {
    const selectedProposals = new Set(
      Array.from(form.querySelectorAll('input[name="proposal"]:checked')).map((input) => input.value),
    );
    const selectedYear = form.elements.year.value;
    const startDate = form.elements.startDate.value;
    const endDate = form.elements.endDate.value;

    if (startDate && endDate && startDate > endDate) {
      statusMessage.textContent = "La fecha inicial no puede ser posterior a la fecha final.";
      statusMessage.classList.add("institutional-report-filter-status--error");
      return;
    }

    statusMessage.classList.remove("institutional-report-filter-status--error");
    const filteredRecords = mockRecords.filter((record) => {
      const matchesProposal = selectedProposals.has(record.proposal);
      const matchesYear = !selectedYear || record.date.startsWith(`${selectedYear}-`);
      const matchesStart = !startDate || record.date >= startDate;
      const matchesEnd = !endDate || record.date <= endDate;
      return matchesProposal && matchesYear && matchesStart && matchesEnd;
    });

    statusMessage.textContent = filteredRecords.length
      ? `Mostrando ${filteredRecords.length} períodos demostrativos según los filtros seleccionados.`
      : "No se encontraron períodos demostrativos para la selección actual.";
    renderDashboard(filteredRecords);
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    applyFilters();
  });

  form.addEventListener("reset", () => {
    window.setTimeout(applyFilters, 0);
  });

  applyFilters();
})();
