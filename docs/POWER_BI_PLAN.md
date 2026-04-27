# POWER_BI_PLAN.md

## Objetivo
Definir una capa analítica BI estable para `IntranetApp` que permita construir el dashboard ejecutivo en Power BI sobre SQL Server, sin depender de tablas operativas crudas ni de exports manuales.

## Regla operativa
- Power BI debe consumir **vistas BI `bi_*`**.
- No conectar el PBIX directo a tablas operativas para lógica ejecutiva compleja.
- La lógica productiva sensible debe salir de SQL estable o de vistas puente controladas.
- Cualquier cambio de modelo BI debe versionarse en `scripts/power_bi_views.sql`.

## PBIX actual
Archivo principal validado:
- `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbix`

Modelo base ya detectado en el PBIX:
- `dbo.bi_dim_residential`
- `dbo.bi_dim_proposal`
- `dbo.bi_dim_activity`
- `dbo.bi_dim_participant`
- `dbo.bi_fact_sessions`
- `dbo.bi_fact_attendance`

## Estrategia recomendada
1. Power BI conecta a SQL Server Express (`localhost\SQLEXPRESS`, DB `IntranetApp`).
2. La fuente principal para BI son las vistas `bi_*`.
3. Las vistas BI encapsulan:
   - joins operativos
   - nombres amigables
   - mapeos de programa y población
   - base de productividad FASE 2
   - detalle operacional ejecutivo
4. El PBIX reutiliza el modelo existente y se extiende con nuevas vistas; no se crea PBIX nuevo.

---

## Vistas BI existentes

### Dimensiones base
- `dbo.bi_dim_residential`
- `dbo.bi_dim_proposal`
- `dbo.bi_dim_activity`
- `dbo.bi_dim_participant`

### Hechos base
- `dbo.bi_fact_sessions`
- `dbo.bi_fact_attendance`

### Qué cubren hoy
- sesiones realizadas
- participaciones
- personas únicas (no duplicado)
- actividad por propuesta
- actividad por residencial
- base operacional para tendencia mensual

---

## Vistas BI nuevas para dashboard ejecutivo

### 1. `dbo.bi_dim_program`
**Propósito:**
Dimensión de programas por propuesta usando `proposal_report_programs`, respetando:
- `formal_name`
- nombre operativo
- población por defecto
- orden
- estado activo
- indicador de si el programa usa estructura poblacional explícita

**Uso en Power BI:**
- slicer de Programa
- eje de participación por programa
- tablas ejecutivas

---

### 2. `dbo.bi_bridge_program_activity`
**Propósito:**
Puente efectivo entre programa y actividad, respetando las dos formas reales del backend:
- estructura legacy por `proposal_report_program_activities` + `proposal_report_program_activity_codes`
- estructura poblacional por `proposal_report_program_populations` + `proposal_report_program_population_activity_codes`

**Uso en Power BI:**
- participación por programa
- top actividades por programa
- tooltips de programa
- filtros cruzados programa ↔ actividad

---

### 3. `dbo.bi_dim_population`
**Propósito:**
Dimensión de población por propuesta usando `proposal_population_groups`.

**Uso en Power BI:**
- slicer de población
- donut de distribución poblacional
- análisis de programa por población

---

### 4. `dbo.bi_bridge_program_population`
**Propósito:**
Puente entre programa y población, respetando:
- estructura explícita por `proposal_report_program_populations`
- fallback legacy al `population_group_id` del programa cuando no exista estructura poblacional activa

**Uso en Power BI:**
- filtros cruzados programa ↔ población
- segmentación por programa/población
- tooltips ejecutivos

---

### 5. `dbo.bi_fact_productivity_compliance`
**Propósito:**
Base mensual de productividad FASE 2 para Power BI, respetando:
- `activity_productivity_goals`
- `goal_type`
- `goal_value`
- `period_goal_value`
- residencial operativo derivado del usuario dueño
- ejecución mensual por actividad/propuesta/residencial
- ejecución global mensual por actividad/propuesta

**Importante:**
Esta vista no modifica la lógica backend. Expone una base BI segura para calcular en Power BI:
- cumplimiento por actividad
- cumplimiento por residencial
- meta global vs ejecutado
- estados ejecutivos de productividad

**Goal types contemplados:**
- `per_residential_min_1`
- `per_residential_fixed`
- `global_fixed`
- `per_residential_period_fixed`

---

### 6. `dbo.bi_fact_operational_detail`
**Propósito:**
Detalle operacional ejecutivo al nivel de asistencia/sesión, respetando:
- `attendance.proposal_participant_id`
- `proposal_participants`
- `persons`
- `participants`
- sesión, propuesta, actividad, residencial, responsable y participante resuelto

**Uso en Power BI:**
- tabla o matrix de detalle operacional
- drill-down por propuesta / actividad / residencial / fecha
- soporte para análisis ejecutivo sin tocar tablas crudas

---

## Relaciones recomendadas en Power BI

### Relaciones base
- `bi_dim_residential[residential_id]` →
  - `bi_fact_sessions[residential_id]`
  - `bi_fact_attendance[residential_id]`
  - `bi_fact_productivity_compliance[residential_id]`
  - `bi_fact_operational_detail[residential_id]`

- `bi_dim_proposal[proposal_id]` →
  - `bi_fact_sessions[proposal_id]`
  - `bi_fact_attendance[proposal_id]`
  - `bi_dim_program[proposal_id]`
  - `bi_dim_population[proposal_id]`
  - `bi_fact_productivity_compliance[proposal_id]`
  - `bi_fact_operational_detail[proposal_id]`

- `bi_dim_activity[activity_code_id]` →
  - `bi_fact_sessions[activity_code_id]`
  - `bi_fact_attendance[activity_code_id]`
  - `bi_bridge_program_activity[activity_code_id]`
  - `bi_fact_productivity_compliance[activity_code_id]`
  - `bi_fact_operational_detail[activity_code_id]`

- `bi_dim_program[program_id]` →
  - `bi_bridge_program_activity[program_id]`
  - `bi_bridge_program_population[program_id]`

- `bi_dim_population[population_group_id]` →
  - `bi_bridge_program_population[population_group_id]`
  - `bi_bridge_program_activity[population_group_id]`

### Fecha
Crear una sola tabla calendario en Power BI:
- `Dim Fecha[Date]` → `bi_fact_sessions[session_date]`
- `Dim Fecha[Date]` → `bi_fact_attendance[session_date]`
- `Dim Fecha[Date]` → `bi_fact_operational_detail[session_date]`
- `Dim Fecha[Date]` ↔ `bi_fact_productivity_compliance[month_start]` *(usar nivel mensual; si hace falta, relación específica o campo de primer día del mes)*

### Recomendación de modelado
- Mantener **single direction** por defecto.
- Usar las vistas puente para slicing de programa y población.
- Evitar relaciones ambiguas entre facts; preferir dimensiones comunes.

---

## Medidas DAX que dependen de estas vistas

### Medidas base
- `Personas Únicas`
- `Participaciones Totales`
- `Actividades Realizadas`
- `Residenciales Impactados`

### Medidas que dependen de la extensión de programas/población
- `Programas Activos`
- `Personas Únicas por Programa`
- `Participaciones por Programa`
- `Actividades por Programa`
- distribución por población

### Medidas que dependen de productividad FASE 2
- `Actividades Evaluadas`
- `Actividades Cumplen`
- `% Cumplimiento`
- `Meta Total`
- `Ejecutado Total`
- `Estado Cumplimiento`
- `Cumplimiento por Residencial %`

### Medidas que dependen de detalle operacional
- drill ejecutivo por propuesta
- detalle operacional por sesión/asistencia
- tabla ejecutiva con responsable, fecha, actividad y participante

---

## Medidas DAX mínimas finales sugeridas

### Base
- `Personas Únicas = CALCULATE(DISTINCTCOUNT('bi_fact_attendance'[participant_id]), 'bi_fact_attendance'[attended] = TRUE())`
- `Participaciones Totales = CALCULATE(COUNTROWS('bi_fact_attendance'), 'bi_fact_attendance'[attended] = TRUE())`
- `Actividades Realizadas = DISTINCTCOUNT('bi_fact_sessions'[session_id])`
- `Residenciales Impactados = CALCULATE(DISTINCTCOUNT('bi_fact_sessions'[residential_id]), NOT ISBLANK('bi_fact_sessions'[residential_id]))`

### Programas
- `Programas Activos = CALCULATE(DISTINCTCOUNT('bi_dim_program'[program_id]), 'bi_dim_program'[is_active] = TRUE())`
- medidas por programa usando `TREATAS` desde `bi_bridge_program_activity`

### Productividad
- medidas sobre `bi_fact_productivity_compliance` usando `executed_residential_count`, `executed_global_count`, `goal_type`, `goal_value`, `period_goal_value`
- evitar reescribir toda la lógica del backend en DAX si la medida puede salir de agregaciones sobre esta vista

---

## Riesgos conocidos

### 1. Programa y población son many-to-many
- Requieren puentes BI.
- Si se relacionan mal, pueden duplicar conteos.

### 2. Productividad FASE 2 no debe rehacerse con lógica libre en DAX
- La lógica real depende de `goal_type`.
- Si se simplifica, Power BI se desviará del backend.

### 3. Tablas fact grandes con demasiados slicers cruzados
- `bi_fact_operational_detail` puede crecer rápido.
- Recomendado usar filtros por período y propuesta antes de abrir detalle completo.

### 4. Relación de fecha mensual con productividad
- `bi_fact_productivity_compliance` está a grano mensual (`month_start`).
- Conviene usar la tabla calendario y cuidar que el slicing mensual no genere ambigüedad con otras facts.

---

## Próximo paso técnico
1. Ejecutar `scripts/power_bi_views.sql` en SQL Server.
2. Refrescar el modelo del PBIX existente.
3. Crear relaciones nuevas en Power BI.
4. Cargar medidas DAX finales.
5. Construir la página ejecutiva sobre el PBIX actual.
