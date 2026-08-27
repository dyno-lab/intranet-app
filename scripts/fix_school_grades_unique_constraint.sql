/*
Migra la unicidad de school_grade_reports a propiedad por residencial.

Regla final:
- residential_id define el informe compartido del residencial.
- created_by_user_id conserva únicamente el actor que creó el informe.

El script se detiene sin modificar constraints si existen duplicados bajo la
nueva clave. Revise primero scripts/residential_ownership_preflight.sql.
*/

USE IntranetApp;
GO

IF EXISTS (
    SELECT 1
    FROM dbo.school_grade_reports
    WHERE residential_id IS NOT NULL
    GROUP BY proposal_id, report_month, report_year, residential_id
    HAVING COUNT(*) > 1
)
BEGIN
    THROW 50001, 'Existen informes de notas duplicados por residencial; resuélvalos antes de cambiar la unicidad.', 1;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.school_grade_reports')
      AND name = N'UX_school_grade_reports_period_residential'
)
BEGIN
    CREATE UNIQUE INDEX UX_school_grade_reports_period_residential
    ON dbo.school_grade_reports(proposal_id, report_month, report_year, residential_id)
    WHERE residential_id IS NOT NULL;
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.school_grade_reports')
      AND name = N'UQ_school_grade_reports_period'
)
BEGIN
    ALTER TABLE dbo.school_grade_reports
    DROP CONSTRAINT UQ_school_grade_reports_period;
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.school_grade_reports')
      AND name = N'UQ_school_grade_reports_period_user'
)
BEGIN
    ALTER TABLE dbo.school_grade_reports
    DROP CONSTRAINT UQ_school_grade_reports_period_user;
END;
GO
