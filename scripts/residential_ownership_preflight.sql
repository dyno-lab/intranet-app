/*
Preflight de propiedad residencial para Faro.

Este script es de solo lectura. Ejecútelo antes de promover la migración a
producción y revise manualmente cualquier fila devuelta.
*/

SET NOCOUNT ON;

/* 1. Snapshots que no pudieron reconstruirse. */
SELECT 'participants' AS table_name, COUNT(*) AS records_without_residential
FROM dbo.participants WHERE residential_id IS NULL
UNION ALL
SELECT 'activity_sessions', COUNT(*)
FROM dbo.activity_sessions WHERE residential_id IS NULL
UNION ALL
SELECT 'proposal_participants', COUNT(*)
FROM dbo.proposal_participants WHERE residential_id IS NULL
UNION ALL
SELECT 'school_grade_reports', COUNT(*)
FROM dbo.school_grade_reports WHERE residential_id IS NULL
UNION ALL
SELECT 'school_dropout_reports', COUNT(*)
FROM dbo.school_dropout_reports WHERE residential_id IS NULL
UNION ALL
SELECT 'pregnancy_reports', COUNT(*)
FROM dbo.pregnancy_reports WHERE residential_id IS NULL
UNION ALL
SELECT 'visit_reports', COUNT(*)
FROM dbo.visit_reports WHERE residential_id IS NULL;

/* 2. Expedientes que colisionarían con la secuencia única por residencial. */
SELECT
    residential_id,
    exp_seq4,
    COUNT(*) AS record_count,
    STRING_AGG(CONVERT(varchar(max), participant_id), ',') AS participant_ids,
    STRING_AGG(CONVERT(varchar(max), expediente_num), ',') AS expediente_numbers
FROM dbo.participants
WHERE residential_id IS NOT NULL
  AND exp_seq4 IS NOT NULL
GROUP BY residential_id, exp_seq4
HAVING COUNT(*) > 1;

/* 3. Informes legacy duplicados bajo la nueva propiedad residencial. */
SELECT
    'school_grade_reports' AS table_name,
    proposal_id,
    report_month,
    report_year,
    residential_id,
    COUNT(*) AS report_count,
    STRING_AGG(CONVERT(varchar(max), report_id), ',') AS report_ids
FROM dbo.school_grade_reports
WHERE residential_id IS NOT NULL
GROUP BY proposal_id, report_month, report_year, residential_id
HAVING COUNT(*) > 1
UNION ALL
SELECT
    'school_dropout_reports',
    proposal_id,
    report_month,
    report_year,
    residential_id,
    COUNT(*),
    STRING_AGG(CONVERT(varchar(max), report_id), ',')
FROM dbo.school_dropout_reports
WHERE residential_id IS NOT NULL
GROUP BY proposal_id, report_month, report_year, residential_id
HAVING COUNT(*) > 1
UNION ALL
SELECT
    'pregnancy_reports',
    proposal_id,
    report_month,
    report_year,
    residential_id,
    COUNT(*),
    STRING_AGG(CONVERT(varchar(max), report_id), ',')
FROM dbo.pregnancy_reports
WHERE residential_id IS NOT NULL
GROUP BY proposal_id, report_month, report_year, residential_id
HAVING COUNT(*) > 1
UNION ALL
SELECT
    'visit_reports',
    proposal_id,
    report_month,
    report_year,
    residential_id,
    COUNT(*),
    STRING_AGG(CONVERT(varchar(max), report_id), ',')
FROM dbo.visit_reports
WHERE residential_id IS NOT NULL
GROUP BY proposal_id, report_month, report_year, residential_id
HAVING COUNT(*) > 1;

/* 4. Informes globales legacy sin residencial; requieren decisión manual. */
SELECT
    vr.report_id,
    vr.proposal_id,
    vr.report_month,
    vr.report_year,
    vr.created_by_user_id,
    COUNT(vrr.referral_id) AS referral_count
FROM dbo.visit_reports AS vr
LEFT JOIN dbo.visit_report_referrals AS vrr ON vrr.report_id = vr.report_id
WHERE vr.residential_id IS NULL
GROUP BY
    vr.report_id,
    vr.proposal_id,
    vr.report_month,
    vr.report_year,
    vr.created_by_user_id;

/* 5. Expedientes cuyo código almacenado difiere del residencial snapshot. */
SELECT
    p.participant_id,
    p.expediente_num,
    p.exp_employee_initials AS stored_code,
    r.code AS residential_code,
    p.residential_id,
    p.created_by_user_id
FROM dbo.participants AS p
INNER JOIN dbo.residentials AS r ON r.residential_id = p.residential_id
WHERE p.exp_employee_initials IS NOT NULL
  AND UPPER(LTRIM(RTRIM(p.exp_employee_initials))) <> UPPER(LTRIM(RTRIM(r.code)));

/* 6. Registros cuyo actor ya no existe; la propiedad no debe inferirse de ellos. */
SELECT 'participants' AS table_name, COUNT(*) AS missing_actor_count
FROM dbo.participants AS records
LEFT JOIN dbo.users AS users ON users.user_id = records.created_by_user_id
WHERE records.created_by_user_id IS NOT NULL AND users.user_id IS NULL
UNION ALL
SELECT 'activity_sessions', COUNT(*)
FROM dbo.activity_sessions AS records
LEFT JOIN dbo.users AS users ON users.user_id = records.created_by_user_id
WHERE records.created_by_user_id IS NOT NULL AND users.user_id IS NULL
UNION ALL
SELECT 'proposal_participants', COUNT(*)
FROM dbo.proposal_participants AS records
LEFT JOIN dbo.users AS users ON users.user_id = records.created_by_user_id
WHERE records.created_by_user_id IS NOT NULL AND users.user_id IS NULL;
