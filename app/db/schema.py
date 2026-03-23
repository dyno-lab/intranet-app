from app.db.session import engine


PHASE1_PROPOSALS_SQL = """
IF OBJECT_ID(N'dbo.proposals', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.proposals (
        proposal_id INT IDENTITY(1,1) PRIMARY KEY,
        code VARCHAR(50) NOT NULL UNIQUE,
        name VARCHAR(150) NOT NULL,
        description VARCHAR(255) NULL,
        is_active BIT NOT NULL CONSTRAINT DF_proposals_is_active DEFAULT 1
    );
END;

IF COL_LENGTH('dbo.activity_sessions', 'proposal_id') IS NULL
BEGIN
    ALTER TABLE dbo.activity_sessions
    ADD proposal_id INT NULL;
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_activity_sessions_proposals'
)
BEGIN
    ALTER TABLE dbo.activity_sessions
    ADD CONSTRAINT FK_activity_sessions_proposals
    FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id);
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_activity_sessions_proposal_id'
      AND object_id = OBJECT_ID('dbo.activity_sessions')
)
BEGIN
    CREATE INDEX IX_activity_sessions_proposal_id
    ON dbo.activity_sessions(proposal_id);
END;

IF COL_LENGTH('dbo.participants', 'is_active') IS NULL
BEGIN
    ALTER TABLE dbo.participants
    ADD is_active BIT NOT NULL CONSTRAINT DF_participants_is_active DEFAULT 1;
END;

UPDATE dbo.participants
SET is_active = CASE
    WHEN LTRIM(RTRIM(LOWER(ISNULL(estatus, '')))) IN ('activo', 'active') THEN 1
    ELSE 0
END
WHERE is_active IS NULL
   OR is_active <> CASE
        WHEN LTRIM(RTRIM(LOWER(ISNULL(estatus, '')))) IN ('activo', 'active') THEN 1
        ELSE 0
      END;

IF COL_LENGTH('dbo.activity_codes', 'proposal_id') IS NULL
BEGIN
    ALTER TABLE dbo.activity_codes
    ADD proposal_id INT NULL;
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_activity_codes_proposals'
)
BEGIN
    ALTER TABLE dbo.activity_codes
    ADD CONSTRAINT FK_activity_codes_proposals
    FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id);
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_activity_codes_proposal_id'
      AND object_id = OBJECT_ID('dbo.activity_codes')
)
BEGIN
    CREATE INDEX IX_activity_codes_proposal_id
    ON dbo.activity_codes(proposal_id);
END;

IF OBJECT_ID(N'dbo.catalog_types', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.catalog_types (
        catalog_type_id INT IDENTITY(1,1) PRIMARY KEY,
        [key] VARCHAR(100) NOT NULL UNIQUE,
        [name] VARCHAR(150) NOT NULL,
        [description] VARCHAR(255) NULL,
        is_active BIT NOT NULL CONSTRAINT DF_catalog_types_is_active DEFAULT 1
    );
END;

IF OBJECT_ID(N'dbo.catalog_options', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.catalog_options (
        catalog_option_id INT IDENTITY(1,1) PRIMARY KEY,
        catalog_type_id INT NOT NULL,
        [value] VARCHAR(150) NOT NULL,
        [label] VARCHAR(150) NOT NULL,
        sort_order INT NOT NULL CONSTRAINT DF_catalog_options_sort_order DEFAULT 0,
        is_active BIT NOT NULL CONSTRAINT DF_catalog_options_is_active DEFAULT 1,
        CONSTRAINT FK_catalog_options_catalog_types FOREIGN KEY (catalog_type_id) REFERENCES dbo.catalog_types(catalog_type_id)
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_catalog_options_catalog_type_id'
      AND object_id = OBJECT_ID('dbo.catalog_options')
)
BEGIN
    CREATE INDEX IX_catalog_options_catalog_type_id
    ON dbo.catalog_options(catalog_type_id);
END;

IF NOT EXISTS (SELECT 1 FROM dbo.catalog_types WHERE [key] = 'composicion_familiar')
BEGIN
    INSERT INTO dbo.catalog_types ([key], [name], [description])
    VALUES ('composicion_familiar', 'Composición Familiar', 'Opciones del campo composición familiar');
END;

IF NOT EXISTS (SELECT 1 FROM dbo.catalog_types WHERE [key] = 'grupo_familiar')
BEGIN
    INSERT INTO dbo.catalog_types ([key], [name], [description])
    VALUES ('grupo_familiar', 'Grupo Familiar', 'Opciones del campo grupo familiar');
END;

IF NOT EXISTS (SELECT 1 FROM dbo.catalog_types WHERE [key] = 'fuente_ingreso_principal')
BEGIN
    INSERT INTO dbo.catalog_types ([key], [name], [description])
    VALUES ('fuente_ingreso_principal', 'Fuente de Ingreso Principal', 'Opciones del campo fuente de ingreso principal');
END;

IF NOT EXISTS (SELECT 1 FROM dbo.catalog_types WHERE [key] = 'rango_ingreso')
BEGIN
    INSERT INTO dbo.catalog_types ([key], [name], [description])
    VALUES ('rango_ingreso', 'Rango de Ingreso', 'Opciones del campo rango de ingreso');
END;

IF NOT EXISTS (SELECT 1 FROM dbo.catalog_types WHERE [key] = 'estatus_participante')
BEGIN
    INSERT INTO dbo.catalog_types ([key], [name], [description])
    VALUES ('estatus_participante', 'Estatus del Participante', 'Opciones del campo estatus');
END;
"""


def ensure_schema_updates() -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(PHASE1_PROPOSALS_SQL)
