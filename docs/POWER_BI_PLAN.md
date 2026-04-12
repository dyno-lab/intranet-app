# POWER_BI_PLAN.md

## Objetivo
Definir una primera capa analítica estable para conectar `IntranetApp` con Power BI sin depender de tablas operativas crudas ni de exports manuales en Excel.

## Estrategia recomendada
1. **Power BI conecta a SQL Server Express** (`localhost\\SQLEXPRESS`, DB `IntranetApp`).
2. La fuente principal para BI serán **vistas SQL `bi_*`**.
3. Las vistas encapsulan joins, nombres amigables y campos derivados.
4. Power BI consume esas vistas como dataset base.

## Primera fase (MVP BI)
Crear y validar estas vistas:

### Dimensiones
- `dbo.bi_dim_residential`
- `dbo.bi_dim_proposal`
- `dbo.bi_dim_activity`
- `dbo.bi_dim_participant`

### Hechos
- `dbo.bi_fact_sessions`
- `dbo.bi_fact_attendance`

## Preguntas que este MVP responde
- ¿Cuántas sesiones se realizaron por mes?
- ¿Cuántas participaciones y participantes únicos hubo?
- ¿Cuántas horas contacto se ofrecieron?
- ¿Qué propuestas y actividades tienen más movimiento?
- ¿Qué residenciales concentran más actividad?
- ¿Qué empleados/facilitadores acumulan más sesiones y horas?

## Dimensiones sugeridas en Power BI
- Fecha
- Residencial
- Propuesta
- Actividad
- Participante
- Empleado
- Usuario creador

## Hechos sugeridos en Power BI
- Asistencia (`bi_fact_attendance`)
- Sesiones (`bi_fact_sessions`)

## Relación recomendada en Power BI
- `bi_dim_residential[residential_id]` -> hechos por `residential_id`
- `bi_dim_proposal[proposal_id]` -> hechos por `proposal_id`
- `bi_dim_activity[activity_code_id]` -> hechos por `activity_code_id`
- `bi_dim_participant[participant_id]` -> `bi_fact_attendance[participant_id]`
- Tabla calendario -> `session_date`

## Medidas DAX iniciales sugeridas
- Total Participaciones = `COUNTROWS(bi_fact_attendance)`
- Participantes Únicos = `DISTINCTCOUNT(bi_fact_attendance[participant_id])`
- Total Sesiones = `DISTINCTCOUNT(bi_fact_sessions[session_id])`
- Total Horas = `SUM(bi_fact_sessions[hours])`
- Promedio Horas por Sesión = `DIVIDE([Total Horas], [Total Sesiones])`

## Dashboards iniciales recomendados
### Dashboard Operacional
- KPIs: sesiones, participaciones, participantes únicos, horas
- Tendencia mensual de sesiones
- Horas por propuesta
- Actividad por residencial
- Top actividades
- Top empleados

### Dashboard Poblacional
- Participantes activos por residencial
- Distribución por género
- Distribución por edad
- Participantes por propuesta

## Fase 2 sugerida
Extender con vistas para módulos específicos:
- `bi_fact_school_grades`
- `bi_fact_school_dropout`
- `bi_fact_pregnancy`
- `bi_fact_visits`
- `bi_fact_vca`
- `bi_fact_adm`

## Buenas prácticas
- No conectar Power BI directo a todas las tablas operativas.
- No replicar lógica compleja del backend en DAX si puede vivir en SQL.
- Mantener nombres consistentes `bi_dim_*` y `bi_fact_*`.
- Preferir vistas estables sobre queries sueltas en Power BI.
- Versionar cualquier cambio en las vistas dentro de `scripts/power_bi_views.sql`.

## Próximo paso técnico
Ejecutar `scripts/power_bi_views.sql` en SQL Server y luego probar conexión desde Power BI Desktop.
