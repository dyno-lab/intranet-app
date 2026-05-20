/*
FASE 2 - Patch de Base de Datos (SQL Server)
Objetivo:
- Añadir columnas para expediente FE-YYYY-XX-####
- Enforzar unicidad de los 4 dígitos (exp_seq4) por empleado (created_by_user_id), sin importar el año.
- Mantener compatibilidad con FASE 1.

IMPORTANTE:
- Este script NO elimina ni renombra columnas existentes.
- Se recomienda correr primero en ambiente de prueba.

*/

-- 1) Añadir columnas nuevas (si no existen)
IF COL_LENGTH('dbo.participants', 'exp_year') IS NULL
BEGIN
    ALTER TABLE dbo.participants ADD exp_year INT NULL;
END;

IF COL_LENGTH('dbo.participants', 'exp_employee_initials') IS NULL
BEGIN
    ALTER TABLE dbo.participants ADD exp_employee_initials NVARCHAR(10) NULL;
END;

IF COL_LENGTH('dbo.participants', 'exp_seq4') IS NULL
BEGIN
    ALTER TABLE dbo.participants ADD exp_seq4 NVARCHAR(4) NULL;
END;

-- 2) Índice único (FILTRADO) para permitir múltiples NULL en exp_seq4 (registros viejos de FASE 1)
-- Regla: exp_seq4 único por created_by_user_id (empleado), sin importar el año.
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UX_participants_created_by_seq4'
      AND object_id = OBJECT_ID('dbo.participants')
)
BEGIN
    CREATE UNIQUE INDEX UX_participants_created_by_seq4
    ON dbo.participants (created_by_user_id, exp_seq4)
    WHERE exp_seq4 IS NOT NULL;
END;
