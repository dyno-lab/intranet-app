"""Additive, idempotent SQL Server DDL. Importing never connects or executes it."""

COMMUNITY_ACTIVITY_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.cp_activities', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_activities (
        activity_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        program_id INT NOT NULL,
        code NVARCHAR(50) NOT NULL,
        code_key NVARCHAR(50) NOT NULL,
        description NVARCHAR(255) NULL,
        is_active BIT NOT NULL CONSTRAINT DF_cp_activity_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_activity_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_cp_activity_program FOREIGN KEY (program_id) REFERENCES dbo.cp_programs(program_id),
        CONSTRAINT UQ_cp_activity_program_code UNIQUE (program_id, code_key),
        CONSTRAINT UQ_cp_activity_program UNIQUE (activity_id, program_id)
    );
END;

IF OBJECT_ID(N'dbo.cp_fiscal_activities', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_fiscal_activities (
        activity_id INT NOT NULL,
        fiscal_year_id INT NOT NULL,
        program_id INT NOT NULL,
        is_active BIT NOT NULL CONSTRAINT DF_cp_fiscal_activity_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_fiscal_activity_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_cp_fiscal_activities PRIMARY KEY (activity_id, fiscal_year_id),
        CONSTRAINT FK_cp_fiscal_activity_year FOREIGN KEY (fiscal_year_id) REFERENCES dbo.cp_fiscal_years(fiscal_year_id),
        CONSTRAINT FK_cp_fiscal_activity_program FOREIGN KEY (activity_id, program_id) REFERENCES dbo.cp_activities(activity_id, program_id),
        CONSTRAINT UQ_cp_fiscal_activity_context UNIQUE (activity_id, fiscal_year_id, program_id)
    );
END;

IF OBJECT_ID(N'dbo.cp_adm_service_types', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_adm_service_types (
        adm_service_type_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        fiscal_year_id INT NOT NULL,
        program_id INT NOT NULL,
        name NVARCHAR(150) NOT NULL,
        name_key NVARCHAR(150) NOT NULL,
        sort_order INT NOT NULL CONSTRAINT DF_cp_adm_service_sort DEFAULT 0,
        is_active BIT NOT NULL CONSTRAINT DF_cp_adm_service_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_adm_service_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_cp_adm_service_year FOREIGN KEY (fiscal_year_id) REFERENCES dbo.cp_fiscal_years(fiscal_year_id),
        CONSTRAINT FK_cp_adm_service_program FOREIGN KEY (program_id) REFERENCES dbo.cp_programs(program_id),
        CONSTRAINT UQ_cp_adm_service_name UNIQUE (fiscal_year_id, program_id, name_key),
        CONSTRAINT UQ_cp_adm_service_context UNIQUE (adm_service_type_id, fiscal_year_id, program_id)
    );
END;

IF OBJECT_ID(N'dbo.cp_adm_service_activities', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_adm_service_activities (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        adm_service_type_id INT NOT NULL,
        activity_id INT NOT NULL,
        fiscal_year_id INT NOT NULL,
        program_id INT NOT NULL,
        is_active BIT NOT NULL CONSTRAINT DF_cp_adm_mapping_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_adm_mapping_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_cp_adm_mapping_service FOREIGN KEY (adm_service_type_id, fiscal_year_id, program_id)
            REFERENCES dbo.cp_adm_service_types(adm_service_type_id, fiscal_year_id, program_id),
        CONSTRAINT FK_cp_adm_mapping_activity FOREIGN KEY (activity_id, fiscal_year_id, program_id)
            REFERENCES dbo.cp_fiscal_activities(activity_id, fiscal_year_id, program_id),
        CONSTRAINT UQ_cp_adm_service_activity UNIQUE (adm_service_type_id, activity_id)
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.cp_adm_service_activities') AND name = N'UQ_cp_adm_active_activity')
BEGIN
    CREATE UNIQUE INDEX UQ_cp_adm_active_activity ON dbo.cp_adm_service_activities(fiscal_year_id, activity_id)
        WHERE is_active = 1;
END;
"""
