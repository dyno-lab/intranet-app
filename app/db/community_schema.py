"""Additive SQL Server migration, applied only by the controlled schema entry point.

Importing this module never creates an engine, connects, or executes DDL.
The first delivery has no fiscal snapshots or operational/report tables yet.
"""

COMMUNITY_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.platform_permissions', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.platform_permissions WHERE [key] = 'access_community')
BEGIN
    INSERT INTO dbo.platform_permissions ([key], name, description, is_active, sort_order)
    VALUES ('access_community', N'Acceder a Comunidad y Prevención',
            N'Permite acceder al módulo Comunidad y Prevención con un rol propio y programas asignados.', 1, 25);
END;

IF OBJECT_ID(N'dbo.cp_programs', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_programs (
        program_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        code VARCHAR(20) NOT NULL,
        code_key VARCHAR(20) NOT NULL CONSTRAINT UQ_cp_program_code_key UNIQUE,
        name NVARCHAR(150) NOT NULL,
        municipality NVARCHAR(100) NULL,
        is_active BIT NOT NULL CONSTRAINT DF_cp_program_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_program_created DEFAULT SYSUTCDATETIME()
    );
END;

IF COL_LENGTH(N'dbo.cp_programs', N'municipality') IS NULL
    ALTER TABLE dbo.cp_programs ADD municipality NVARCHAR(100) NULL;

IF OBJECT_ID(N'dbo.cp_fiscal_years', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_fiscal_years (
        fiscal_year_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        code VARCHAR(50) NOT NULL CONSTRAINT UQ_cp_fiscal_year_code UNIQUE,
        name NVARCHAR(150) NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,
        status VARCHAR(20) NOT NULL CONSTRAINT DF_cp_fiscal_year_status DEFAULT 'active',
        is_active BIT NOT NULL CONSTRAINT DF_cp_fiscal_year_active DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_fiscal_year_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_cp_fiscal_year_dates CHECK (end_date >= start_date),
        CONSTRAINT CK_cp_fiscal_year_status CHECK (status IN ('active', 'closed'))
    );
END;

IF OBJECT_ID(N'dbo.cp_user_access', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_user_access (
        user_id INT NOT NULL PRIMARY KEY,
        role VARCHAR(20) NOT NULL,
        CONSTRAINT FK_cp_user_access_user FOREIGN KEY (user_id) REFERENCES dbo.users(user_id),
        CONSTRAINT CK_cp_user_access_role CHECK (role IN ('admin', 'supervisor', 'viewer', 'user'))
    );
END;

IF OBJECT_ID(N'dbo.cp_user_programs', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_user_programs (
        user_id INT NOT NULL,
        program_id INT NOT NULL,
        CONSTRAINT PK_cp_user_programs PRIMARY KEY (user_id, program_id),
        CONSTRAINT FK_cp_user_program_user FOREIGN KEY (user_id) REFERENCES dbo.users(user_id),
        CONSTRAINT FK_cp_user_program_program FOREIGN KEY (program_id) REFERENCES dbo.cp_programs(program_id)
    );
END;

IF OBJECT_ID(N'dbo.cp_sequences', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_sequences (
        exp_year INT NOT NULL PRIMARY KEY,
        last_value INT NOT NULL,
        CONSTRAINT CK_cp_sequence_year CHECK (exp_year BETWEEN 1000 AND 9999),
        CONSTRAINT CK_cp_sequence_value CHECK (last_value BETWEEN 0 AND 9999)
    );
END;

IF OBJECT_ID(N'dbo.cp_participants', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_participants (
        participant_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        expediente_num VARCHAR(50) NOT NULL CONSTRAINT UQ_cp_participant_record UNIQUE,
        exp_year INT NOT NULL,
        exp_sequence INT NOT NULL,
        nombre NVARCHAR(150) NOT NULL,
        inicial NVARCHAR(12) NULL,
        apellido_paterno NVARCHAR(150) NOT NULL,
        apellido_materno NVARCHAR(150) NULL,
        genero VARCHAR(10) NOT NULL,
        fecha_nacimiento DATE NULL,
        direccion_fisica NVARCHAR(500) NULL,
        pueblo NVARCHAR(100) NULL,
        primera_vez VARCHAR(5) NULL,
        escolaridad_participante NVARCHAR(150) NULL,
        composicion_familiar NVARCHAR(100) NULL,
        relacion_familiar NVARCHAR(100) NULL,
        estatus NVARCHAR(50) NULL,
        grupo_familiar NVARCHAR(20) NULL,
        fuente_ingreso_principal NVARCHAR(100) NULL,
        rango_ingreso NVARCHAR(30) NULL,
        is_head_of_household BIT NOT NULL CONSTRAINT DF_cp_participant_head DEFAULT 0,
        telefono VARCHAR(30) NULL,
        email NVARCHAR(255) NULL,
        created_by_user_id INT NOT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_participant_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_participant_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_cp_participant_creator FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(user_id),
        CONSTRAINT UQ_cp_participant_year_sequence UNIQUE (exp_year, exp_sequence),
        CONSTRAINT CK_cp_participant_year CHECK (exp_year BETWEEN 1000 AND 9999),
        CONSTRAINT CK_cp_participant_sequence CHECK (exp_sequence BETWEEN 1 AND 9999),
        CONSTRAINT CK_cp_participant_gender CHECK (genero IN ('F', 'M'))
    );
END;

IF OBJECT_ID(N'dbo.cp_participant_programs', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_participant_programs (
        participant_id INT NOT NULL,
        program_id INT NOT NULL,
        record_number VARCHAR(80) NOT NULL CONSTRAINT UQ_cp_participant_program_record UNIQUE,
        created_by_user_id INT NOT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_participant_program_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_cp_participant_programs PRIMARY KEY (participant_id, program_id),
        CONSTRAINT FK_cp_participant_program_participant FOREIGN KEY (participant_id) REFERENCES dbo.cp_participants(participant_id),
        CONSTRAINT FK_cp_participant_program_program FOREIGN KEY (program_id) REFERENCES dbo.cp_programs(program_id),
        CONSTRAINT FK_cp_participant_program_creator FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(user_id)
    );
END;
"""
