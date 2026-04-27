/*
Power BI reporting layer (MVP)
Base de datos objetivo: IntranetApp
Motor: SQL Server

Este script crea una primera capa de vistas BI para Power BI.
Si alguna tabla/campo cambia, actualizar estas vistas primero y luego el modelo Power BI.
*/

/* ============================================================
   DIMENSIONES
   ============================================================ */

CREATE OR ALTER VIEW dbo.bi_dim_residential
AS
SELECT
    r.residential_id,
    r.code AS residential_code,
    r.name AS residential_name,
    r.municipality,
    r.rq_code,
    r.is_active,
    r.created_at
FROM dbo.residentials r;
GO

CREATE OR ALTER VIEW dbo.bi_dim_proposal
AS
SELECT
    p.proposal_id,
    p.code AS proposal_code,
    p.name AS proposal_name,
    p.description,
    p.status,
    p.is_active,
    p.finalized_at,
    p.finalized_by_user_id,
    p.finalization_note,
    p.updated_at
FROM dbo.proposals p;
GO

CREATE OR ALTER VIEW dbo.bi_dim_activity
AS
SELECT
    ac.activity_code_id,
    ac.code AS activity_code,
    ac.description AS activity_description,
    ac.proposal_id,
    p.code AS proposal_code,
    p.name AS proposal_name,
    ac.is_active
FROM dbo.activity_codes ac
LEFT JOIN dbo.proposals p
    ON p.proposal_id = ac.proposal_id;
GO

CREATE OR ALTER VIEW dbo.bi_dim_participant
AS
SELECT
    pt.participant_id,
    pt.created_by_user_id,
    u.username AS created_by_username,
    u.role AS created_by_role,
    u.residential_id,
    r.code AS residential_code,
    r.name AS residential_name,
    r.municipality,
    r.rq_code,
    pt.expediente_num,
    LTRIM(RTRIM(
        CONCAT(
            COALESCE(pt.nombre, ''), ' ',
            COALESCE(pt.inicial + ' ', ''),
            COALESCE(pt.apellido_paterno, ''), ' ',
            COALESCE(pt.apellido_materno, '')
        )
    )) AS participant_full_name,
    pt.nombre,
    pt.inicial,
    pt.apellido_paterno,
    pt.apellido_materno,
    pt.genero,
    pt.fecha_nacimiento,
    CASE
        WHEN pt.fecha_nacimiento IS NULL THEN NULL
        ELSE DATEDIFF(YEAR, pt.fecha_nacimiento, CAST(GETDATE() AS date))
             - CASE
                 WHEN DATEADD(YEAR, DATEDIFF(YEAR, pt.fecha_nacimiento, CAST(GETDATE() AS date)), pt.fecha_nacimiento) > CAST(GETDATE() AS date)
                 THEN 1 ELSE 0
               END
    END AS edad_actual,
    pt.edificio,
    pt.apart,
    pt.vca,
    pt.primera_vez,
    pt.escolaridad_participante,
    pt.composicion_familiar,
    pt.estatus,
    pt.grupo_familiar,
    pt.fuente_ingreso_principal,
    pt.rango_ingreso,
    pt.is_active,
    pt.created_at,
    pt.updated_at
FROM dbo.participants pt
LEFT JOIN dbo.users u
    ON u.user_id = pt.created_by_user_id
LEFT JOIN dbo.residentials r
    ON r.residential_id = u.residential_id;
GO

/* ============================================================
   HECHOS
   ============================================================ */

CREATE OR ALTER VIEW dbo.bi_fact_sessions
AS
WITH attendance_summary AS (
    SELECT
        a.session_id,
        COUNT(*) AS attendance_count,
        COUNT(DISTINCT a.participant_id) AS distinct_participant_count
    FROM dbo.attendance a
    WHERE ISNULL(a.attended, 1) = 1
    GROUP BY a.session_id
)
SELECT
    s.session_id,
    s.session_date,
    YEAR(s.session_date) AS session_year,
    MONTH(s.session_date) AS session_month,
    CONVERT(char(7), s.session_date, 120) AS session_year_month,
    s.created_by_user_id,
    u.username AS created_by_username,
    u.role AS created_by_role,
    u.residential_id,
    r.code AS residential_code,
    r.name AS residential_name,
    r.municipality,
    r.rq_code,
    s.proposal_id,
    p.code AS proposal_code,
    p.name AS proposal_name,
    s.activity_code_id,
    ac.code AS activity_code,
    ac.description AS activity_description,
    s.employee_id,
    e.full_name AS employee_name,
    CAST(ISNULL(s.hours, 0) AS decimal(10,2)) AS hours,
    ISNULL(att.attendance_count, 0) AS attendance_count,
    ISNULL(att.distinct_participant_count, 0) AS distinct_participant_count,
    s.created_at
FROM dbo.activity_sessions s
LEFT JOIN dbo.users u
    ON u.user_id = s.created_by_user_id
LEFT JOIN dbo.residentials r
    ON r.residential_id = u.residential_id
LEFT JOIN dbo.proposals p
    ON p.proposal_id = s.proposal_id
LEFT JOIN dbo.activity_codes ac
    ON ac.activity_code_id = s.activity_code_id
LEFT JOIN dbo.employees e
    ON e.employee_id = s.employee_id
LEFT JOIN attendance_summary att
    ON att.session_id = s.session_id;
GO

CREATE OR ALTER VIEW dbo.bi_fact_attendance
AS
SELECT
    a.attendance_id,
    a.session_id,
    s.session_date,
    YEAR(s.session_date) AS session_year,
    MONTH(s.session_date) AS session_month,
    CONVERT(char(7), s.session_date, 120) AS session_year_month,
    a.participant_id,
    a.proposal_participant_id,
    a.attended,
    a.marked_at,
    a.marked_by,
    s.proposal_id,
    p.code AS proposal_code,
    p.name AS proposal_name,
    s.activity_code_id,
    ac.code AS activity_code,
    ac.description AS activity_description,
    s.employee_id,
    e.full_name AS employee_name,
    s.created_by_user_id,
    u.username AS created_by_username,
    u.role AS created_by_role,
    u.residential_id,
    r.code AS residential_code,
    r.name AS residential_name,
    r.municipality,
    r.rq_code,
    pt.expediente_num AS participant_expediente,
    LTRIM(RTRIM(
        CONCAT(
            COALESCE(pt.nombre, ''), ' ',
            COALESCE(pt.inicial + ' ', ''),
            COALESCE(pt.apellido_paterno, ''), ' ',
            COALESCE(pt.apellido_materno, '')
        )
    )) AS participant_full_name,
    pt.genero AS participant_genero,
    pt.is_active AS participant_is_active,
    CAST(ISNULL(s.hours, 0) AS decimal(10,2)) AS session_hours
FROM dbo.attendance a
INNER JOIN dbo.activity_sessions s
    ON s.session_id = a.session_id
LEFT JOIN dbo.participants pt
    ON pt.participant_id = a.participant_id
LEFT JOIN dbo.users u
    ON u.user_id = s.created_by_user_id
LEFT JOIN dbo.residentials r
    ON r.residential_id = u.residential_id
LEFT JOIN dbo.proposals p
    ON p.proposal_id = s.proposal_id
LEFT JOIN dbo.activity_codes ac
    ON ac.activity_code_id = s.activity_code_id
LEFT JOIN dbo.employees e
    ON e.employee_id = s.employee_id;
GO

/* ============================================================
   EXTENSIONES BI — PROGRAMAS / POBLACIONES / PRODUCTIVIDAD / DETALLE
   ============================================================ */

CREATE OR ALTER VIEW dbo.bi_dim_program
AS
SELECT
    prp.program_id,
    prp.proposal_id,
    p.code AS proposal_code,
    p.name AS proposal_name,
    prp.code AS program_code,
    prp.name AS program_name,
    prp.formal_name,
    COALESCE(NULLIF(LTRIM(RTRIM(prp.formal_name)), ''), NULLIF(LTRIM(RTRIM(prp.name)), ''), prp.code) AS program_display_name,
    prp.population_group_id AS default_population_group_id,
    pg.code AS default_population_code,
    pg.label AS default_population_label,
    prp.sort_order,
    prp.is_active,
    CAST(
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM dbo.proposal_report_program_populations prpp
                WHERE prpp.program_id = prp.program_id
                  AND prpp.is_active = 1
            ) THEN 1 ELSE 0
        END
        AS bit
    ) AS uses_population_structure,
    prp.created_at
FROM dbo.proposal_report_programs prp
INNER JOIN dbo.proposals p
    ON p.proposal_id = prp.proposal_id
LEFT JOIN dbo.proposal_population_groups pg
    ON pg.population_group_id = prp.population_group_id;
GO

CREATE OR ALTER VIEW dbo.bi_bridge_program_activity
AS
WITH population_mappings AS (
    SELECT DISTINCT
        prp.program_id,
        prp.proposal_id,
        prpp.program_population_id,
        prpp.population_group_id,
        pg.code AS population_code,
        pg.label AS population_label,
        prppac.activity_code_id,
        ac.code AS activity_code,
        ac.description AS activity_description,
        CAST('population' AS varchar(20)) AS assignment_source
    FROM dbo.proposal_report_programs prp
    INNER JOIN dbo.proposal_report_program_populations prpp
        ON prpp.program_id = prp.program_id
    INNER JOIN dbo.proposal_report_program_population_activity_codes prppac
        ON prppac.program_population_id = prpp.program_population_id
    INNER JOIN dbo.activity_codes ac
        ON ac.activity_code_id = prppac.activity_code_id
    LEFT JOIN dbo.proposal_population_groups pg
        ON pg.population_group_id = prpp.population_group_id
    WHERE prp.is_active = 1
      AND prpp.is_active = 1
),
legacy_mappings AS (
    SELECT DISTINCT
        prp.program_id,
        prp.proposal_id,
        CAST(NULL AS int) AS program_population_id,
        prp.population_group_id,
        pg.code AS population_code,
        pg.label AS population_label,
        prpac.activity_code_id,
        ac.code AS activity_code,
        ac.description AS activity_description,
        CAST('legacy' AS varchar(20)) AS assignment_source
    FROM dbo.proposal_report_programs prp
    INNER JOIN dbo.proposal_report_program_activities prpa
        ON prpa.program_id = prp.program_id
    INNER JOIN dbo.proposal_report_program_activity_codes prpac
        ON prpac.program_activity_id = prpa.program_activity_id
    INNER JOIN dbo.activity_codes ac
        ON ac.activity_code_id = prpac.activity_code_id
    LEFT JOIN dbo.proposal_population_groups pg
        ON pg.population_group_id = prp.population_group_id
    WHERE prp.is_active = 1
      AND prpa.is_active = 1
      AND NOT EXISTS (
          SELECT 1
          FROM dbo.proposal_report_program_populations prpp
          WHERE prpp.program_id = prp.program_id
            AND prpp.is_active = 1
      )
)
SELECT *
FROM population_mappings
UNION ALL
SELECT *
FROM legacy_mappings;
GO

CREATE OR ALTER VIEW dbo.bi_dim_population
AS
SELECT
    pg.population_group_id,
    pg.proposal_id,
    p.code AS proposal_code,
    p.name AS proposal_name,
    pg.code AS population_code,
    pg.label AS population_label,
    pg.age_min,
    pg.age_max,
    pg.sort_order,
    pg.is_active,
    pg.created_at
FROM dbo.proposal_population_groups pg
INNER JOIN dbo.proposals p
    ON p.proposal_id = pg.proposal_id;
GO

CREATE OR ALTER VIEW dbo.bi_bridge_program_population
AS
WITH explicit_population AS (
    SELECT
        prp.program_id,
        prp.proposal_id,
        prpp.program_population_id,
        prpp.population_group_id,
        pg.code AS population_code,
        pg.label AS population_label,
        prpp.sort_order,
        prpp.is_active,
        CAST('population' AS varchar(20)) AS mapping_source
    FROM dbo.proposal_report_programs prp
    INNER JOIN dbo.proposal_report_program_populations prpp
        ON prpp.program_id = prp.program_id
    INNER JOIN dbo.proposal_population_groups pg
        ON pg.population_group_id = prpp.population_group_id
    WHERE prp.is_active = 1
      AND prpp.is_active = 1
),
legacy_default_population AS (
    SELECT
        prp.program_id,
        prp.proposal_id,
        CAST(NULL AS int) AS program_population_id,
        prp.population_group_id,
        pg.code AS population_code,
        pg.label AS population_label,
        prp.sort_order,
        prp.is_active,
        CAST('legacy_default' AS varchar(20)) AS mapping_source
    FROM dbo.proposal_report_programs prp
    INNER JOIN dbo.proposal_population_groups pg
        ON pg.population_group_id = prp.population_group_id
    WHERE prp.is_active = 1
      AND NOT EXISTS (
          SELECT 1
          FROM dbo.proposal_report_program_populations prpp
          WHERE prpp.program_id = prp.program_id
            AND prpp.is_active = 1
      )
)
SELECT *
FROM explicit_population
UNION ALL
SELECT *
FROM legacy_default_population;
GO

CREATE OR ALTER VIEW dbo.bi_fact_productivity_compliance
AS
WITH active_reporting_residentials AS (
    SELECT
        u.user_id AS owner_user_id,
        u.username AS owner_username,
        u.role AS owner_role,
        u.residential_id,
        r.code AS residential_code,
        r.name AS residential_name,
        r.municipality,
        r.rq_code
    FROM dbo.users u
    LEFT JOIN dbo.residentials r
        ON r.residential_id = u.residential_id
    WHERE u.is_active = 1
      AND u.role = 'user'
),
month_spine AS (
    SELECT DISTINCT
        DATEFROMPARTS(YEAR(s.session_date), MONTH(s.session_date), 1) AS month_start
    FROM dbo.activity_sessions s
),
goal_base AS (
    SELECT
        apg.productivity_goal_id,
        apg.proposal_id,
        p.code AS proposal_code,
        p.name AS proposal_name,
        apg.activity_code_id,
        ac.code AS activity_code,
        ac.description AS activity_description,
        apg.goal_type,
        apg.goal_value,
        apg.period_goal_value,
        apg.is_active,
        apg.created_at,
        apg.updated_at
    FROM dbo.activity_productivity_goals apg
    INNER JOIN dbo.proposals p
        ON p.proposal_id = apg.proposal_id
    INNER JOIN dbo.activity_codes ac
        ON ac.activity_code_id = apg.activity_code_id
    WHERE apg.is_active = 1
),
goal_month_grid AS (
    SELECT
        gb.productivity_goal_id,
        gb.proposal_id,
        gb.proposal_code,
        gb.proposal_name,
        gb.activity_code_id,
        gb.activity_code,
        gb.activity_description,
        gb.goal_type,
        gb.goal_value,
        gb.period_goal_value,
        gb.is_active,
        gb.created_at,
        gb.updated_at,
        arr.owner_user_id,
        arr.owner_username,
        arr.owner_role,
        arr.residential_id,
        arr.residential_code,
        arr.residential_name,
        arr.municipality,
        arr.rq_code,
        ms.month_start,
        YEAR(ms.month_start) AS session_year,
        MONTH(ms.month_start) AS session_month,
        CONVERT(char(7), ms.month_start, 120) AS session_year_month
    FROM goal_base gb
    CROSS JOIN active_reporting_residentials arr
    CROSS JOIN month_spine ms
),
session_counts AS (
    SELECT
        s.proposal_id,
        s.activity_code_id,
        s.created_by_user_id AS owner_user_id,
        DATEFROMPARTS(YEAR(s.session_date), MONTH(s.session_date), 1) AS month_start,
        COUNT(s.session_id) AS executed_residential_count
    FROM dbo.activity_sessions s
    WHERE s.proposal_id IS NOT NULL
    GROUP BY
        s.proposal_id,
        s.activity_code_id,
        s.created_by_user_id,
        DATEFROMPARTS(YEAR(s.session_date), MONTH(s.session_date), 1)
),
global_counts AS (
    SELECT
        s.proposal_id,
        s.activity_code_id,
        DATEFROMPARTS(YEAR(s.session_date), MONTH(s.session_date), 1) AS month_start,
        COUNT(s.session_id) AS executed_global_count
    FROM dbo.activity_sessions s
    WHERE s.proposal_id IS NOT NULL
    GROUP BY
        s.proposal_id,
        s.activity_code_id,
        DATEFROMPARTS(YEAR(s.session_date), MONTH(s.session_date), 1)
)
SELECT
    gmg.productivity_goal_id,
    gmg.proposal_id,
    gmg.proposal_code,
    gmg.proposal_name,
    gmg.activity_code_id,
    gmg.activity_code,
    gmg.activity_description,
    gmg.owner_user_id,
    gmg.owner_username,
    gmg.owner_role,
    gmg.residential_id,
    gmg.residential_code,
    gmg.residential_name,
    gmg.municipality,
    gmg.rq_code,
    gmg.month_start,
    gmg.session_year,
    gmg.session_month,
    gmg.session_year_month,
    gmg.goal_type,
    gmg.goal_value,
    gmg.period_goal_value,
    ISNULL(sc.executed_residential_count, 0) AS executed_residential_count,
    ISNULL(gc.executed_global_count, 0) AS executed_global_count,
    CASE
        WHEN gmg.goal_type = 'per_residential_min_1' THEN 1
        WHEN gmg.goal_type IN ('per_residential_fixed', 'per_residential_period_fixed') THEN ISNULL(gmg.goal_value, 0)
        ELSE NULL
    END AS residential_target_value,
    CASE
        WHEN gmg.goal_type = 'global_fixed' THEN ISNULL(gmg.goal_value, 0)
        ELSE NULL
    END AS global_target_value,
    CASE
        WHEN gmg.goal_type = 'per_residential_min_1' THEN CASE WHEN ISNULL(sc.executed_residential_count, 0) >= 1 THEN 1 ELSE 0 END
        WHEN gmg.goal_type IN ('per_residential_fixed', 'per_residential_period_fixed') THEN CASE WHEN ISNULL(sc.executed_residential_count, 0) >= ISNULL(gmg.goal_value, 0) THEN 1 ELSE 0 END
        WHEN gmg.goal_type = 'global_fixed' THEN CASE WHEN ISNULL(gc.executed_global_count, 0) >= ISNULL(gmg.goal_value, 0) THEN 1 ELSE 0 END
        ELSE NULL
    END AS monthly_met_flag,
    CASE
        WHEN gmg.goal_type = 'per_residential_min_1' AND ISNULL(sc.executed_residential_count, 0) >= 1 THEN 'Cumple'
        WHEN gmg.goal_type = 'per_residential_min_1' AND ISNULL(sc.executed_residential_count, 0) < 1 THEN 'No cumple'
        WHEN gmg.goal_type IN ('per_residential_fixed', 'per_residential_period_fixed') AND ISNULL(sc.executed_residential_count, 0) >= ISNULL(gmg.goal_value, 0) THEN 'Cumple'
        WHEN gmg.goal_type = 'global_fixed' AND ISNULL(gc.executed_global_count, 0) >= ISNULL(gmg.goal_value, 0) THEN 'Cumple'
        WHEN gmg.goal_type IN ('per_residential_fixed', 'per_residential_period_fixed', 'global_fixed') THEN 'No cumple'
        ELSE 'No aplica'
    END AS monthly_compliance_label,
    CONCAT(gmg.proposal_id, ':', gmg.activity_code_id) AS goal_activity_key,
    CONCAT(gmg.proposal_id, ':', gmg.activity_code_id, ':', ISNULL(CONVERT(varchar(20), gmg.owner_user_id), '0')) AS goal_residential_key,
    gmg.created_at,
    gmg.updated_at
FROM goal_month_grid gmg
LEFT JOIN session_counts sc
    ON sc.proposal_id = gmg.proposal_id
   AND sc.activity_code_id = gmg.activity_code_id
   AND ISNULL(sc.owner_user_id, -1) = ISNULL(gmg.owner_user_id, -1)
   AND sc.month_start = gmg.month_start
LEFT JOIN global_counts gc
    ON gc.proposal_id = gmg.proposal_id
   AND gc.activity_code_id = gmg.activity_code_id
   AND gc.month_start = gmg.month_start;
GO

CREATE OR ALTER VIEW dbo.bi_fact_operational_detail
AS
SELECT
    a.attendance_id,
    a.session_id,
    s.session_date,
    YEAR(s.session_date) AS session_year,
    MONTH(s.session_date) AS session_month,
    CONVERT(char(7), s.session_date, 120) AS session_year_month,
    s.proposal_id,
    p.code AS proposal_code,
    p.name AS proposal_name,
    s.activity_code_id,
    ac.code AS activity_code,
    ac.description AS activity_description,
    s.employee_id,
    e.employee_code,
    e.full_name AS employee_name,
    s.created_by_user_id,
    u.username AS created_by_username,
    u.role AS created_by_role,
    u.residential_id,
    r.code AS residential_code,
    r.name AS residential_name,
    r.municipality,
    r.rq_code,
    a.participant_id,
    a.proposal_participant_id,
    pp.person_id,
    prs.legacy_participant_id,
    COALESCE(pp.expediente_num, pt.expediente_num) AS expediente_num,
    COALESCE(
        NULLIF(LTRIM(RTRIM(CONCAT(
            COALESCE(prs.nombre, ''), ' ',
            COALESCE(prs.inicial + ' ', ''),
            COALESCE(prs.apellido_paterno, ''), ' ',
            COALESCE(prs.apellido_materno, '')
        ))), ''),
        NULLIF(LTRIM(RTRIM(CONCAT(
            COALESCE(pt.nombre, ''), ' ',
            COALESCE(pt.inicial + ' ', ''),
            COALESCE(pt.apellido_paterno, ''), ' ',
            COALESCE(pt.apellido_materno, '')
        ))), '')
    ) AS participant_full_name,
    COALESCE(prs.genero, pt.genero) AS participant_genero,
    COALESCE(prs.fecha_nacimiento, pt.fecha_nacimiento) AS participant_birth_date,
    pp.edificio AS proposal_participant_building,
    pp.apart AS proposal_participant_apartment,
    pt.edificio AS participant_building,
    pt.apart AS participant_apartment,
    pp.is_active AS proposal_participant_is_active,
    pt.is_active AS participant_is_active,
    a.attended,
    a.marked_at,
    a.marked_by,
    CAST(ISNULL(s.hours, 0) AS decimal(10,2)) AS session_hours,
    s.created_at AS session_created_at
FROM dbo.attendance a
INNER JOIN dbo.activity_sessions s
    ON s.session_id = a.session_id
LEFT JOIN dbo.proposals p
    ON p.proposal_id = s.proposal_id
LEFT JOIN dbo.activity_codes ac
    ON ac.activity_code_id = s.activity_code_id
LEFT JOIN dbo.employees e
    ON e.employee_id = s.employee_id
LEFT JOIN dbo.users u
    ON u.user_id = s.created_by_user_id
LEFT JOIN dbo.residentials r
    ON r.residential_id = u.residential_id
LEFT JOIN dbo.proposal_participants pp
    ON pp.proposal_participant_id = a.proposal_participant_id
LEFT JOIN dbo.persons prs
    ON prs.person_id = pp.person_id
LEFT JOIN dbo.participants pt
    ON pt.participant_id = a.participant_id;
GO

/* ============================================================
   SUGERENCIAS DE USO EN POWER BI
   ============================================================
   - Importar primero:
     * dbo.bi_dim_residential
     * dbo.bi_dim_proposal
     * dbo.bi_dim_activity
     * dbo.bi_dim_participant
     * dbo.bi_fact_sessions
     * dbo.bi_fact_attendance
     * dbo.bi_dim_program
     * dbo.bi_bridge_program_activity
     * dbo.bi_dim_population
     * dbo.bi_bridge_program_population
     * dbo.bi_fact_productivity_compliance
     * dbo.bi_fact_operational_detail

   - Crear tabla calendario en Power BI o en SQL si luego se desea.
   - Relacionar por:
     * residential_id
     * proposal_id
     * activity_code_id
     * participant_id
     * session_date
     * program_id
     * population_group_id
*/
GO
