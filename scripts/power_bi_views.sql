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
   SUGERENCIAS DE USO EN POWER BI
   ============================================================
   - Importar primero:
     * dbo.bi_dim_residential
     * dbo.bi_dim_proposal
     * dbo.bi_dim_activity
     * dbo.bi_dim_participant
     * dbo.bi_fact_sessions
     * dbo.bi_fact_attendance

   - Crear tabla calendario en Power BI o en SQL si luego se desea.
   - Relacionar por:
     * residential_id
     * proposal_id
     * activity_code_id
     * participant_id
     * session_date
*/
GO
