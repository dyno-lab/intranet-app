"""Additive fiscal schema. Importing this module never connects or executes DDL."""

COMMUNITY_FISCAL_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.cp_fiscal_states', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_fiscal_states (
        fiscal_year_id INT NOT NULL PRIMARY KEY,
        snapshots_frozen BIT NOT NULL CONSTRAINT DF_cp_fiscal_state_frozen DEFAULT 0,
        locked_through DATE NULL,
        updated_by_user_id INT NOT NULL,
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_fiscal_state_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_cp_fiscal_state_year FOREIGN KEY (fiscal_year_id) REFERENCES dbo.cp_fiscal_years(fiscal_year_id),
        CONSTRAINT FK_cp_fiscal_state_actor FOREIGN KEY (updated_by_user_id) REFERENCES dbo.users(user_id)
    );
END;

IF OBJECT_ID(N'dbo.cp_fiscal_participants', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_fiscal_participants (
        participant_id INT NOT NULL,
        fiscal_year_id INT NOT NULL,
        snapshot_json NVARCHAR(MAX) NOT NULL,
        updated_by_user_id INT NOT NULL,
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_fiscal_participant_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_cp_fiscal_participant PRIMARY KEY (participant_id, fiscal_year_id),
        CONSTRAINT FK_cp_fiscal_participant_participant FOREIGN KEY (participant_id) REFERENCES dbo.cp_participants(participant_id),
        CONSTRAINT FK_cp_fiscal_participant_year FOREIGN KEY (fiscal_year_id) REFERENCES dbo.cp_fiscal_years(fiscal_year_id),
        CONSTRAINT FK_cp_fiscal_participant_actor FOREIGN KEY (updated_by_user_id) REFERENCES dbo.users(user_id)
    );
END;

IF OBJECT_ID(N'dbo.cp_fiscal_enrollments', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_fiscal_enrollments (
        enrollment_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        participant_id INT NOT NULL,
        program_id INT NOT NULL,
        fiscal_year_id INT NOT NULL,
        created_by_user_id INT NOT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_enrollment_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_cp_enrollment_participant_program_year UNIQUE (participant_id, program_id, fiscal_year_id),
        CONSTRAINT FK_cp_enrollment_participant FOREIGN KEY (participant_id) REFERENCES dbo.cp_participants(participant_id),
        CONSTRAINT FK_cp_enrollment_program FOREIGN KEY (program_id) REFERENCES dbo.cp_programs(program_id),
        CONSTRAINT FK_cp_enrollment_year FOREIGN KEY (fiscal_year_id) REFERENCES dbo.cp_fiscal_years(fiscal_year_id),
        CONSTRAINT FK_cp_enrollment_permanent_program FOREIGN KEY (participant_id, program_id) REFERENCES dbo.cp_participant_programs(participant_id, program_id),
        CONSTRAINT FK_cp_enrollment_snapshot FOREIGN KEY (participant_id, fiscal_year_id) REFERENCES dbo.cp_fiscal_participants(participant_id, fiscal_year_id),
        CONSTRAINT FK_cp_enrollment_actor FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(user_id)
    );
END;

IF OBJECT_ID(N'dbo.cp_enrollment_periods', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_enrollment_periods (
        period_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        enrollment_id INT NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NULL,
        reason NVARCHAR(250) NOT NULL,
        observation NVARCHAR(1000) NULL,
        created_by_user_id INT NOT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_enrollment_period_created DEFAULT SYSUTCDATETIME(),
        end_reason NVARCHAR(250) NULL,
        end_observation NVARCHAR(1000) NULL,
        ended_by_user_id INT NULL,
        ended_at DATETIMEOFFSET NULL,
        CONSTRAINT CK_cp_enrollment_period_dates CHECK (end_date IS NULL OR end_date >= start_date),
        CONSTRAINT UQ_cp_enrollment_period_start UNIQUE (enrollment_id, start_date),
        CONSTRAINT FK_cp_enrollment_period_enrollment FOREIGN KEY (enrollment_id) REFERENCES dbo.cp_fiscal_enrollments(enrollment_id),
        CONSTRAINT FK_cp_enrollment_period_creator FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(user_id),
        CONSTRAINT FK_cp_enrollment_period_closer FOREIGN KEY (ended_by_user_id) REFERENCES dbo.users(user_id)
    );
    CREATE INDEX IX_cp_enrollment_periods_enrollment_id ON dbo.cp_enrollment_periods(enrollment_id);
END;
"""
