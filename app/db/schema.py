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

IF NOT EXISTS (
    SELECT 1
    FROM dbo.catalog_options co
    INNER JOIN dbo.catalog_types ct ON ct.catalog_type_id = co.catalog_type_id
    WHERE ct.[key] = 'composicion_familiar'
)
BEGIN
    INSERT INTO dbo.catalog_options (catalog_type_id, [value], [label], sort_order, is_active)
    SELECT ct.catalog_type_id, v.[value], v.[label], v.sort_order, 1
    FROM dbo.catalog_types ct
    CROSS APPLY (VALUES
        ('Solo(a)', 'Solo(a)', 1),
        ('Madre soltera', 'Madre soltera', 2),
        ('Padre soltero', 'Padre soltero', 3),
        ('Adulto Mayor (60+) con niños', 'Adulto Mayor (60+) con niños', 4),
        ('2 adultos con menores', '2 adultos con menores', 5),
        ('2 adultos sin menores', '2 adultos sin menores', 6),
        ('Ambos padres', 'Ambos padres', 7),
        ('Encargado con menor', 'Encargado con menor', 8)
    ) v([value], [label], sort_order)
    WHERE ct.[key] = 'composicion_familiar';
END;

IF NOT EXISTS (
    SELECT 1
    FROM dbo.catalog_options co
    INNER JOIN dbo.catalog_types ct ON ct.catalog_type_id = co.catalog_type_id
    WHERE ct.[key] = 'grupo_familiar'
)
BEGIN
    INSERT INTO dbo.catalog_options (catalog_type_id, [value], [label], sort_order, is_active)
    SELECT ct.catalog_type_id, v.[value], v.[label], v.sort_order, 1
    FROM dbo.catalog_types ct
    CROSS APPLY (VALUES
        ('1', '1', 1),
        ('2', '2', 2),
        ('3', '3', 3),
        ('4', '4', 4),
        ('5', '5', 5),
        ('6', '6', 6),
        ('7', '7', 7),
        ('8', '8', 8),
        ('9 ó +', '9 ó +', 9)
    ) v([value], [label], sort_order)
    WHERE ct.[key] = 'grupo_familiar';
END;

IF NOT EXISTS (
    SELECT 1
    FROM dbo.catalog_options co
    INNER JOIN dbo.catalog_types ct ON ct.catalog_type_id = co.catalog_type_id
    WHERE ct.[key] = 'fuente_ingreso_principal'
)
BEGIN
    INSERT INTO dbo.catalog_options (catalog_type_id, [value], [label], sort_order, is_active)
    SELECT ct.catalog_type_id, v.[value], v.[label], v.sort_order, 1
    FROM dbo.catalog_types ct
    CROSS APPLY (VALUES
        ('PAN', 'PAN', 1),
        ('TANF', 'TANF', 2),
        ('Seguro social', 'Seguro social', 3),
        ('Beneficio por desempleo', 'Beneficio por desempleo', 4),
        ('Empleado', 'Empleado', 5),
        ('Negocio propio', 'Negocio propio', 6),
        ('Pensión alimentaria', 'Pensión alimentaria', 7),
        ('Pensión por retiro', 'Pensión por retiro', 8),
        ('No formal (trabajo independiente-cuenta propia)', 'No formal (trabajo independiente-cuenta propia)', 9),
        ('No respondió', 'No respondió', 10),
        ('Desempleado', 'Desempleado', 11)
    ) v([value], [label], sort_order)
    WHERE ct.[key] = 'fuente_ingreso_principal';
END;

IF NOT EXISTS (
    SELECT 1
    FROM dbo.catalog_options co
    INNER JOIN dbo.catalog_types ct ON ct.catalog_type_id = co.catalog_type_id
    WHERE ct.[key] = 'rango_ingreso'
)
BEGIN
    INSERT INTO dbo.catalog_options (catalog_type_id, [value], [label], sort_order, is_active)
    SELECT ct.catalog_type_id, v.[value], v.[label], v.sort_order, 1
    FROM dbo.catalog_types ct
    CROSS APPLY (VALUES
        ('0 - 100', '0 - 100', 1),
        ('101 - 500', '101 - 500', 2),
        ('501 - 1000', '501 - 1000', 3),
        ('1001 - 2000', '1001 - 2000', 4),
        ('2001 o más', '2001 o más', 5)
    ) v([value], [label], sort_order)
    WHERE ct.[key] = 'rango_ingreso';
END;

IF NOT EXISTS (
    SELECT 1
    FROM dbo.catalog_options co
    INNER JOIN dbo.catalog_types ct ON ct.catalog_type_id = co.catalog_type_id
    WHERE ct.[key] = 'estatus_participante'
)
BEGIN
    INSERT INTO dbo.catalog_options (catalog_type_id, [value], [label], sort_order, is_active)
    SELECT ct.catalog_type_id, v.[value], v.[label], v.sort_order, 1
    FROM dbo.catalog_types ct
    CROSS APPLY (VALUES
        ('Activo', 'Activo', 1),
        ('No Activo', 'No Activo', 2),
        ('Deceso', 'Deceso', 3),
        ('Transferencia', 'Transferencia', 4),
        ('Baja', 'Baja', 5)
    ) v([value], [label], sort_order)
    WHERE ct.[key] = 'estatus_participante';
END;

IF OBJECT_ID(N'dbo.school_grade_reports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.school_grade_reports (
        report_id INT IDENTITY(1,1) PRIMARY KEY,
        proposal_id INT NOT NULL,
        report_month INT NOT NULL,
        report_year INT NOT NULL,
        notes VARCHAR(500) NULL,
        created_by_user_id INT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_school_grade_reports_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_school_grade_reports_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_school_grade_reports_proposals FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id),
        CONSTRAINT UQ_school_grade_reports_period_user UNIQUE (proposal_id, report_month, report_year, created_by_user_id)
    );
END;

IF EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'UQ'
      AND [name] = 'UQ_school_grade_reports_period'
      AND [parent_object_id] = OBJECT_ID(N'dbo.school_grade_reports')
)
BEGIN
    ALTER TABLE dbo.school_grade_reports
    DROP CONSTRAINT UQ_school_grade_reports_period;
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.key_constraints
    WHERE [type] = 'UQ'
      AND [name] = 'UQ_school_grade_reports_period_user'
      AND [parent_object_id] = OBJECT_ID(N'dbo.school_grade_reports')
)
BEGIN
    ALTER TABLE dbo.school_grade_reports
    ADD CONSTRAINT UQ_school_grade_reports_period_user
    UNIQUE (proposal_id, report_month, report_year, created_by_user_id);
END;

IF OBJECT_ID(N'dbo.school_grade_report_items', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.school_grade_report_items (
        report_item_id INT IDENTITY(1,1) PRIMARY KEY,
        report_id INT NOT NULL,
        participant_id INT NOT NULL,
        grade_level VARCHAR(20) NULL,
        is_content_room BIT NOT NULL CONSTRAINT DF_school_grade_report_items_is_content_room DEFAULT 0,
        spanish_grade DECIMAL(5,2) NULL,
        english_grade DECIMAL(5,2) NULL,
        math_grade DECIMAL(5,2) NULL,
        science_grade DECIMAL(5,2) NULL,
        social_studies_grade DECIMAL(5,2) NULL,
        elective_1_grade DECIMAL(5,2) NULL,
        elective_2_grade DECIMAL(5,2) NULL,
        elective_3_grade DECIMAL(5,2) NULL,
        elective_4_grade DECIMAL(5,2) NULL,
        average_grade DECIMAL(5,2) NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_school_grade_report_items_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_school_grade_report_items_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_school_grade_report_items_reports FOREIGN KEY (report_id) REFERENCES dbo.school_grade_reports(report_id),
        CONSTRAINT FK_school_grade_report_items_participants FOREIGN KEY (participant_id) REFERENCES dbo.participants(participant_id),
        CONSTRAINT UQ_school_grade_report_items_participant UNIQUE (report_id, participant_id)
    );
END;

IF OBJECT_ID(N'dbo.school_dropout_reports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.school_dropout_reports (
        report_id INT IDENTITY(1,1) PRIMARY KEY,
        proposal_id INT NOT NULL,
        report_month INT NOT NULL,
        report_year INT NOT NULL,
        notes VARCHAR(500) NULL,
        created_by_user_id INT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_school_dropout_reports_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_school_dropout_reports_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_school_dropout_reports_proposals FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id),
        CONSTRAINT UQ_school_dropout_reports_period_user UNIQUE (proposal_id, report_month, report_year, created_by_user_id)
    );
END;

IF OBJECT_ID(N'dbo.school_dropout_report_items', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.school_dropout_report_items (
        report_item_id INT IDENTITY(1,1) PRIMARY KEY,
        report_id INT NOT NULL,
        participant_id INT NOT NULL,
        attended_tutoring BIT NOT NULL CONSTRAINT DF_school_dropout_report_items_attended_tutoring DEFAULT 0,
        current_grade VARCHAR(20) NULL,
        attended_school BIT NOT NULL CONSTRAINT DF_school_dropout_report_items_attended_school DEFAULT 0,
        report_10_weeks BIT NOT NULL CONSTRAINT DF_school_dropout_report_items_report_10_weeks DEFAULT 0,
        report_20_weeks BIT NOT NULL CONSTRAINT DF_school_dropout_report_items_report_20_weeks DEFAULT 0,
        report_30_weeks BIT NOT NULL CONSTRAINT DF_school_dropout_report_items_report_30_weeks DEFAULT 0,
        report_40_weeks BIT NOT NULL CONSTRAINT DF_school_dropout_report_items_report_40_weeks DEFAULT 0,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_school_dropout_report_items_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_school_dropout_report_items_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_school_dropout_report_items_reports FOREIGN KEY (report_id) REFERENCES dbo.school_dropout_reports(report_id),
        CONSTRAINT FK_school_dropout_report_items_participants FOREIGN KEY (participant_id) REFERENCES dbo.participants(participant_id),
        CONSTRAINT UQ_school_dropout_report_items_participant UNIQUE (report_id, participant_id)
    );
END;

IF OBJECT_ID(N'dbo.pregnancy_reports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.pregnancy_reports (
        report_id INT IDENTITY(1,1) PRIMARY KEY,
        proposal_id INT NOT NULL,
        report_month INT NOT NULL,
        report_year INT NOT NULL,
        notes VARCHAR(500) NULL,
        created_by_user_id INT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_pregnancy_reports_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_pregnancy_reports_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_pregnancy_reports_proposals FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id),
        CONSTRAINT UQ_pregnancy_reports_period_user UNIQUE (proposal_id, report_month, report_year, created_by_user_id)
    );
END;

IF OBJECT_ID(N'dbo.pregnancy_report_items', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.pregnancy_report_items (
        report_item_id INT IDENTITY(1,1) PRIMARY KEY,
        report_id INT NOT NULL,
        participant_id INT NOT NULL,
        participated_workshops BIT NOT NULL CONSTRAINT DF_pregnancy_report_items_participated_workshops DEFAULT 0,
        is_pregnant BIT NOT NULL CONSTRAINT DF_pregnancy_report_items_is_pregnant DEFAULT 0,
        gestation_time VARCHAR(50) NULL,
        has_children BIT NOT NULL CONSTRAINT DF_pregnancy_report_items_has_children DEFAULT 0,
        children_count INT NULL,
        children_ages VARCHAR(100) NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_pregnancy_report_items_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_pregnancy_report_items_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_pregnancy_report_items_reports FOREIGN KEY (report_id) REFERENCES dbo.pregnancy_reports(report_id),
        CONSTRAINT FK_pregnancy_report_items_participants FOREIGN KEY (participant_id) REFERENCES dbo.participants(participant_id),
        CONSTRAINT UQ_pregnancy_report_items_participant UNIQUE (report_id, participant_id)
    );
END;
"""


PHASE3_RESIDENTIALS_SQL = """
IF OBJECT_ID(N'dbo.residentials', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.residentials (
        residential_id INT IDENTITY(1,1) PRIMARY KEY,
        code VARCHAR(20) NOT NULL,
        name VARCHAR(150) NOT NULL,
        municipality VARCHAR(100) NOT NULL,
        rq_code VARCHAR(50) NOT NULL,
        is_active BIT NOT NULL CONSTRAINT DF_residentials_is_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_residentials_created_at DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_residentials_code'
      AND object_id = OBJECT_ID('dbo.residentials')
)
BEGIN
    CREATE UNIQUE INDEX UQ_residentials_code ON dbo.residentials(code);
END;

IF COL_LENGTH('dbo.users', 'residential_id') IS NULL
BEGIN
    ALTER TABLE dbo.users ADD residential_id INT NULL;
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_users_residentials'
)
BEGIN
    ALTER TABLE dbo.users
    ADD CONSTRAINT FK_users_residentials
    FOREIGN KEY (residential_id) REFERENCES dbo.residentials(residential_id);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_users_residential_id'
      AND object_id = OBJECT_ID('dbo.users')
)
BEGIN
    CREATE INDEX IX_users_residential_id ON dbo.users(residential_id);
END;

MERGE dbo.residentials AS target
USING (VALUES
    ('AC', 'Aristides Chavier', 'Ponce', 'RQ1014'),
    ('PJR', 'Pedro J. Rosaly', 'Ponce', 'RQ1009'),
    ('JPDL', 'Juan Ponce de León', 'Ponce', 'RQ1001'),
    ('ERA', 'Ernesto Ramos Antonini', 'Ponce', 'RQ1017'),
    ('RLN', 'Rafael Lopez Nussa', 'Ponce', 'RQ1016'),
    ('LC', 'La Ceiba', 'Ponce', 'RQ5022'),
    ('LS', 'Leónardo Santiago', 'Juana Díaz', 'RQ5148'),
    ('VDP', 'Villa del Parque', 'Juana Díaz', 'RQ3089'),
    ('BDM', 'Brisas del Mar', 'Salinas', 'RQ5045'),
    ('BV', 'Bella Vista', 'Salinas', 'RQ3090'),
    ('VDG', 'Valles de Guayama', 'Guayama', 'RQ5266'),
    ('JDG', 'Jardines de Guamani', 'Guayama', 'RQ5184'),
    ('FC', 'Fernando Calimano', 'Guayama', 'RQ5314'),
    ('SAC', 'San Antonio Carioca', 'Guayama', 'RQ5048'),
    ('EC', 'El Carmen', 'Mayagüez', 'RQ4010'),
    ('MH', 'Manuel Hernandez Rosa', 'Mayagüez', 'RQ4009'),
    ('RH', 'Rafael Hernandez', 'Mayagüez', 'RQ4011'),
    ('CL', 'Columbus Landing', 'Mayagüez', 'RQ4001')
) AS source(code, name, municipality, rq_code)
ON target.code = source.code
WHEN MATCHED THEN
    UPDATE SET
        target.name = source.name,
        target.municipality = source.municipality,
        target.rq_code = source.rq_code,
        target.is_active = 1
WHEN NOT MATCHED THEN
    INSERT (code, name, municipality, rq_code, is_active)
    VALUES (source.code, source.name, source.municipality, source.rq_code, 1);

UPDATE u
SET u.residential_id = r.residential_id
FROM dbo.users u
INNER JOIN dbo.residentials r ON r.code = UPPER(LTRIM(RTRIM(u.username)))
WHERE u.residential_id IS NULL;
"""

PHASE5_VISITS_SQL = """
IF OBJECT_ID(N'dbo.visit_activity_mappings', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.visit_activity_mappings (
        mapping_id INT IDENTITY(1,1) PRIMARY KEY,
        proposal_id INT NOT NULL,
        activity_code_id INT NOT NULL,
        is_active BIT NOT NULL CONSTRAINT DF_visit_activity_mappings_is_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_visit_activity_mappings_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_visit_activity_mappings_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_visit_activity_mappings_proposals FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id),
        CONSTRAINT FK_visit_activity_mappings_activity_codes FOREIGN KEY (activity_code_id) REFERENCES dbo.activity_codes(activity_code_id),
        CONSTRAINT UQ_visit_activity_mappings_proposal_activity UNIQUE (proposal_id, activity_code_id)
    );
END;

IF OBJECT_ID(N'dbo.visit_reports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.visit_reports (
        report_id INT IDENTITY(1,1) PRIMARY KEY,
        proposal_id INT NOT NULL,
        report_month INT NOT NULL,
        report_year INT NOT NULL,
        notes VARCHAR(500) NULL,
        created_by_user_id INT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_visit_reports_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_visit_reports_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_visit_reports_proposals FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id),
        CONSTRAINT UQ_visit_reports_period_user UNIQUE (proposal_id, report_month, report_year, created_by_user_id)
    );
END;

IF OBJECT_ID(N'dbo.visit_report_referrals', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.visit_report_referrals (
        referral_id INT IDENTITY(1,1) PRIMARY KEY,
        report_id INT NOT NULL,
        referral_type VARCHAR(20) NOT NULL,
        agency VARCHAR(255) NULL,
        reference_or_purpose VARCHAR(500) NULL,
        sort_order INT NOT NULL CONSTRAINT DF_visit_report_referrals_sort_order DEFAULT 0,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_visit_report_referrals_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_visit_report_referrals_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_visit_report_referrals_reports FOREIGN KEY (report_id) REFERENCES dbo.visit_reports(report_id)
    );
END;

IF COL_LENGTH('dbo.visit_report_referrals', 'agency') IS NULL
BEGIN
    ALTER TABLE dbo.visit_report_referrals ADD agency VARCHAR(255) NULL;
END;

IF COL_LENGTH('dbo.visit_report_referrals', 'reference_or_purpose') IS NULL
BEGIN
    ALTER TABLE dbo.visit_report_referrals ADD reference_or_purpose VARCHAR(500) NULL;
END;

IF COL_LENGTH('dbo.visit_report_referrals', 'description') IS NULL
BEGIN
    ALTER TABLE dbo.visit_report_referrals ADD description VARCHAR(500) NULL;
END;
"""


PHASE4_VCA_SQL = """
IF OBJECT_ID(N'dbo.vca_columns', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.vca_columns (
        vca_column_id INT IDENTITY(1,1) PRIMARY KEY,
        proposal_id INT NOT NULL,
        [name] VARCHAR(150) NOT NULL,
        sort_order INT NOT NULL CONSTRAINT DF_vca_columns_sort_order DEFAULT 0,
        is_active BIT NOT NULL CONSTRAINT DF_vca_columns_is_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_vca_columns_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_vca_columns_proposals FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id)
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_vca_columns_proposal_id'
      AND object_id = OBJECT_ID('dbo.vca_columns')
)
BEGIN
    CREATE INDEX IX_vca_columns_proposal_id ON dbo.vca_columns(proposal_id);
END;

IF OBJECT_ID(N'dbo.vca_column_activity_codes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.vca_column_activity_codes (
        id INT IDENTITY(1,1) PRIMARY KEY,
        vca_column_id INT NOT NULL,
        activity_code_id INT NOT NULL,
        CONSTRAINT FK_vca_column_activity_codes_vca_columns FOREIGN KEY (vca_column_id) REFERENCES dbo.vca_columns(vca_column_id),
        CONSTRAINT FK_vca_column_activity_codes_activity_codes FOREIGN KEY (activity_code_id) REFERENCES dbo.activity_codes(activity_code_id),
        CONSTRAINT UQ_vca_column_activity_codes UNIQUE (vca_column_id, activity_code_id)
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_vca_column_activity_codes_vca_column_id'
      AND object_id = OBJECT_ID('dbo.vca_column_activity_codes')
)
BEGIN
    CREATE INDEX IX_vca_column_activity_codes_vca_column_id ON dbo.vca_column_activity_codes(vca_column_id);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_vca_column_activity_codes_activity_code_id'
      AND object_id = OBJECT_ID('dbo.vca_column_activity_codes')
)
BEGIN
    CREATE INDEX IX_vca_column_activity_codes_activity_code_id ON dbo.vca_column_activity_codes(activity_code_id);
END;
"""

PHASE6_PROGRAM_REPORTS_SQL = """
IF OBJECT_ID(N'dbo.proposal_population_groups', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.proposal_population_groups (
        population_group_id INT IDENTITY(1,1) PRIMARY KEY,
        proposal_id INT NOT NULL,
        code VARCHAR(50) NOT NULL,
        label VARCHAR(100) NOT NULL,
        age_min INT NULL,
        age_max INT NULL,
        sort_order INT NOT NULL CONSTRAINT DF_proposal_population_groups_sort_order DEFAULT 0,
        is_active BIT NOT NULL CONSTRAINT DF_proposal_population_groups_is_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_proposal_population_groups_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_proposal_population_groups_proposals FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id),
        CONSTRAINT UQ_proposal_population_groups_proposal_code UNIQUE (proposal_id, code)
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_proposal_population_groups_proposal_id'
      AND object_id = OBJECT_ID('dbo.proposal_population_groups')
)
BEGIN
    CREATE INDEX IX_proposal_population_groups_proposal_id ON dbo.proposal_population_groups(proposal_id);
END;

IF OBJECT_ID(N'dbo.proposal_report_programs', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.proposal_report_programs (
        program_id INT IDENTITY(1,1) PRIMARY KEY,
        proposal_id INT NOT NULL,
        code VARCHAR(50) NOT NULL,
        name VARCHAR(150) NOT NULL,
        population_group_id INT NOT NULL,
        sort_order INT NOT NULL CONSTRAINT DF_proposal_report_programs_sort_order DEFAULT 0,
        is_active BIT NOT NULL CONSTRAINT DF_proposal_report_programs_is_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_proposal_report_programs_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_proposal_report_programs_proposals FOREIGN KEY (proposal_id) REFERENCES dbo.proposals(proposal_id),
        CONSTRAINT FK_proposal_report_programs_population_groups FOREIGN KEY (population_group_id) REFERENCES dbo.proposal_population_groups(population_group_id),
        CONSTRAINT UQ_proposal_report_programs_proposal_code UNIQUE (proposal_id, code)
    );
END;

IF COL_LENGTH('dbo.proposal_report_programs', 'population_group_id') IS NULL
BEGIN
    ALTER TABLE dbo.proposal_report_programs ADD population_group_id INT NULL;
END;

IF COL_LENGTH('dbo.proposal_report_programs', 'population_group') IS NOT NULL
BEGIN
    UPDATE prp
    SET population_group_id = ppg.population_group_id
    FROM dbo.proposal_report_programs prp
    INNER JOIN dbo.proposal_population_groups ppg
        ON ppg.proposal_id = prp.proposal_id
       AND LOWER(LTRIM(RTRIM(ppg.code))) = LOWER(LTRIM(RTRIM(prp.population_group)))
    WHERE prp.population_group_id IS NULL;
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_proposal_report_programs_population_groups'
)
BEGIN
    ALTER TABLE dbo.proposal_report_programs
    ADD CONSTRAINT FK_proposal_report_programs_population_groups
    FOREIGN KEY (population_group_id) REFERENCES dbo.proposal_population_groups(population_group_id);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_proposal_report_programs_proposal_id'
      AND object_id = OBJECT_ID('dbo.proposal_report_programs')
)
BEGIN
    CREATE INDEX IX_proposal_report_programs_proposal_id ON dbo.proposal_report_programs(proposal_id);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_proposal_report_programs_population_group_id'
      AND object_id = OBJECT_ID('dbo.proposal_report_programs')
)
BEGIN
    CREATE INDEX IX_proposal_report_programs_population_group_id ON dbo.proposal_report_programs(population_group_id);
END;

IF OBJECT_ID(N'dbo.proposal_report_program_activities', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.proposal_report_program_activities (
        program_activity_id INT IDENTITY(1,1) PRIMARY KEY,
        program_id INT NOT NULL,
        code VARCHAR(50) NOT NULL,
        label VARCHAR(255) NOT NULL,
        age_min INT NULL,
        age_max INT NULL,
        sort_order INT NOT NULL CONSTRAINT DF_proposal_report_program_activities_sort_order DEFAULT 0,
        is_active BIT NOT NULL CONSTRAINT DF_proposal_report_program_activities_is_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_proposal_report_program_activities_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_proposal_report_program_activities_programs FOREIGN KEY (program_id) REFERENCES dbo.proposal_report_programs(program_id),
        CONSTRAINT UQ_proposal_report_program_activities_program_code UNIQUE (program_id, code)
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_proposal_report_program_activities_program_id'
      AND object_id = OBJECT_ID('dbo.proposal_report_program_activities')
)
BEGIN
    CREATE INDEX IX_proposal_report_program_activities_program_id ON dbo.proposal_report_program_activities(program_id);
END;

IF OBJECT_ID(N'dbo.proposal_report_program_activity_codes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.proposal_report_program_activity_codes (
        id INT IDENTITY(1,1) PRIMARY KEY,
        program_activity_id INT NOT NULL,
        activity_code_id INT NOT NULL,
        CONSTRAINT FK_proposal_report_program_activity_codes_program_activities FOREIGN KEY (program_activity_id) REFERENCES dbo.proposal_report_program_activities(program_activity_id),
        CONSTRAINT FK_proposal_report_program_activity_codes_activity_codes FOREIGN KEY (activity_code_id) REFERENCES dbo.activity_codes(activity_code_id),
        CONSTRAINT UQ_proposal_report_program_activity_codes UNIQUE (program_activity_id, activity_code_id)
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_proposal_report_program_activity_codes_program_activity_id'
      AND object_id = OBJECT_ID('dbo.proposal_report_program_activity_codes')
)
BEGIN
    CREATE INDEX IX_proposal_report_program_activity_codes_program_activity_id ON dbo.proposal_report_program_activity_codes(program_activity_id);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_proposal_report_program_activity_codes_activity_code_id'
      AND object_id = OBJECT_ID('dbo.proposal_report_program_activity_codes')
)
BEGIN
    CREATE INDEX IX_proposal_report_program_activity_codes_activity_code_id ON dbo.proposal_report_program_activity_codes(activity_code_id);
END;
"""


def ensure_schema_updates() -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(PHASE1_PROPOSALS_SQL)
        conn.exec_driver_sql(PHASE3_RESIDENTIALS_SQL)
        conn.exec_driver_sql(PHASE4_VCA_SQL)
        conn.exec_driver_sql(PHASE5_VISITS_SQL)
        conn.exec_driver_sql(PHASE6_PROGRAM_REPORTS_SQL)
