/*
Corrige la unicidad de school_grade_reports para permitir un informe por:
- propuesta
- mes
- año
- usuario creador

Antes estaba global por propuesta/mes/año y bloqueaba que AC y BDM
crearan sus informes del mismo período.
*/

USE IntranetApp;
GO

IF EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'UQ'
      AND [name] = 'uq_school_grade_reports_period'
)
BEGIN
    ALTER TABLE dbo.school_grade_reports
    DROP CONSTRAINT uq_school_grade_reports_period;
END
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'UQ'
      AND [name] = 'uq_school_grade_reports_period_user'
)
BEGIN
    ALTER TABLE dbo.school_grade_reports
    ADD CONSTRAINT uq_school_grade_reports_period_user
    UNIQUE (proposal_id, report_month, report_year, created_by_user_id);
END
GO
