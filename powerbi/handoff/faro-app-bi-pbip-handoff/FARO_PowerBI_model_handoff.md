# FARO Power BI — Handoff para Codex

## Archivo objetivo
Proyecto PBIP actual:
- `faro-app-bi.pbip`
- Report: `FaroPowerBi.Report`
- Semantic model: `FaroPowerBi.SemanticModel`

> No tocar ni modificar `Powerbi.pbix`. Ese PBIX viejo es solo referencia visual/histórica.

## Objetivo del dashboard
Dashboard Ejecutivo FARO con páginas:
1. Dashboard Ejecutivo FARO
2. Perfil Demográfico
3. Programas y Actividades
4. VCA y Autosuficiencia

El diseño debe usar datos reales del modelo `bi_*`, no valores fijos del mockup HTML.

## Modelo semántico principal
El PBIP consume vistas SQL Server `dbo.bi_*` desde `IntranetApp`.

### Dimensiones
- `bi_dim_proposal`
  - `proposal_id`
  - `proposal_code`
  - `Propuesta`
  - `status`, `is_active`

- `bi_dim_residential`
  - `residential_id`
  - `residential_code`
  - `Residencial`
  - `municipality`
  - `rq_code`
  - `is_active`

- `bi_dim_activity`
  - `activity_code_id`
  - `Actividad`
  - `activity_description`
  - `proposal_id`
  - `proposal_activity_key`
  - `is_active`

- `bi_dim_participant`
  - `participant_id`
  - `participant_full_name`
  - `genero`
  - `Rango Edad`
  - `edad_actual`
  - `vca`
  - `escolaridad_participante`
  - `composicion_familiar`
  - `fuente_ingreso_principal`
  - `rango_ingreso`
  - `residential_id`, `residential_name`
  - `is_active`

- `bi_dim_program`
  - `program_id`
  - `Programa`
  - `program_code`
  - `proposal_id`
  - `is_active`

- `bi_dim_population`
  - `population_group_id`
  - `Poblacion`
  - `proposal_id`
  - `proposal_population_key`

- `Dim_Fecha`
  - `Date`
  - `Ano`
  - `MesN`
  - `Mes`
  - `AnoMes`
  - `Periodo`
  - `MesCorto`

### Hechos
- `bi_fact_attendance`
  - nivel asistencia/participación
  - claves: `attendance_id`, `session_id`, `participant_id`, `proposal_id`, `activity_code_id`, `residential_id`
  - fecha: `session_date`, `session_year`, `session_month`, `session_year_month`
  - medidas principales:
    - `Total Personas Unicas`
    - `Total Participaciones`
    - `Participaciones Duplicadas`
    - `Total Personas Unicas F`
    - `Total Personas Unicas M`
    - `Personas Unicas VCA Si`
    - `Participaciones VCA Si`
    - `Personas Unicas VCA Si F`
    - `Personas Unicas VCA Si M`
    - `Grupo Edad Principal`
    - `Escolaridad Principal`
    - `Fuente Ingreso Principal`
    - `Tipo Familia Principal`
    - `Actividad Principal`

- `bi_fact_sessions`
  - nivel sesión/actividad realizada
  - claves: `session_id`, `proposal_id`, `activity_code_id`, `residential_id`, `employee_id`
  - medidas principales:
    - `Total Actividades Realizadas`
    - `Total Residenciales Impactados`
    - `Total Horas`
    - `Actividades Realizadas`
    - `Residenciales Impactados`

- `bi_fact_productivity_compliance`
  - cumplimiento/productividad mensual por propuesta/actividad/residencial
  - medidas principales:
    - `Meta Total`
    - `Ejecutado Total`
    - `Cumplimiento General`
    - `Estado Cumplimiento`
    - `Cumplimiento Residencial`
    - `Actividades Cumplen`
    - `% Cumplimiento`

- `bi_fact_operational_detail`
  - detalle operacional a nivel asistencia/sesión/participante resuelto

### Puentes
- `bi_bridge_program_activity`
  - puente programa ↔ actividad
  - usa `proposal_activity_key`

- `bi_bridge_program_population`
  - puente programa ↔ población
  - usa `proposal_population_key`

## Reglas de negocio importantes

### Personas únicas
`Personas únicas` debe contar participantes con al menos 1 asistencia dentro del contexto filtrado:
- propuesta
- período/mes
- programa/actividad cuando aplique
- residencial
- población cuando aplique

Medida actual: `bi_fact_attendance[Total Personas Unicas]`.

### Participaciones duplicadas
No usar “firmas” como label principal. Usar:
- `Participaciones duplicadas`

Equivale al conteo total de asistencias/participaciones en el contexto filtrado.
Medida actual: `bi_fact_attendance[Participaciones Duplicadas]`, alias de `[Total Participaciones]`.

### Actividades realizadas
Usar sesiones/actividades realizadas, no participantes.
Medida actual: `bi_fact_sessions[Total Actividades Realizadas]`.

### VCA
VCA debe contar solo participantes con:
- `vca = Sí` (también se contemplan variantes Si/SÍ/TRUE/1)
- al menos 1 asistencia en el contexto filtrado

Medidas actuales:
- `Personas Unicas VCA Si`
- `Participaciones VCA Si`
- `Personas Unicas VCA Si F`
- `Personas Unicas VCA Si M`

### Actividades activas
Las medidas base de asistencia usan filtro sobre `bi_dim_activity[is_active] = TRUE()` cuando aplica. No mostrar actividades desactivadas.

## Relaciones relevantes
- `bi_fact_attendance[participant_id]` → `bi_dim_participant[participant_id]`
- `bi_fact_attendance[proposal_id]` → `bi_dim_proposal[proposal_id]`
- `bi_fact_attendance[residential_id]` → `bi_dim_residential[residential_id]`
- `bi_fact_attendance[proposal_activity_key]` → `bi_dim_activity[proposal_activity_key]`
- `bi_fact_sessions[proposal_id]` → `bi_dim_proposal[proposal_id]`
- `bi_fact_sessions[residential_id]` → `bi_dim_residential[residential_id]`
- `bi_fact_sessions[proposal_activity_key]` → `bi_dim_activity[proposal_activity_key]`
- facts date fields → `Dim_Fecha[Date]`
- program/population filtering via bridge tables

## Páginas actuales del PBIP
1. `Dashboard Ejecutivo FARO`
   - resumen por programa/servicio
   - tendencia mensual
   - productividad por actividad
   - cumplimiento por residencial

2. `Perfil Demográfico`
   - edad/sexo
   - tipo de familia
   - rango/fuente de ingresos
   - escolaridad
   - resumen demográfico por residencial

3. `Programas y Actividades`
   - tendencia mensual
   - ranking por programa
   - resumen programa/actividad
   - productividad

4. `VCA y Autosuficiencia`
   - personas/participaciones VCA
   - VCA por residencial
   - VCA por edad/género
   - detalle participantes VCA

## Campos faltantes / pendientes detectados
No se confirmó en el modelo actual un campo separado para:
- autosuficiencia social
- autosuficiencia económica
- tipo de servicio VCA

Por ahora VCA está basado en `vca = Sí` + asistencias/participaciones. Si se necesita separar social/económica, hay que extender vistas SQL/modelo.

## Archivos incluidos en ZIP
- `faro-app-bi.pbip`
- `FaroPowerBi.Report/`
- `FaroPowerBi.SemanticModel/`
- este documento de handoff

## No incluido
- `Powerbi.pbix` viejo de referencia
- backups
- `DataEstructurada`
