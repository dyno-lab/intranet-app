"""Idempotent additive SQL Server DDL; import does not connect or execute it."""

COMMUNITY_OPERATIONS_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.cp_activity_sessions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_activity_sessions (
        session_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        fiscal_year_id INT NOT NULL,
        program_id INT NOT NULL,
        activity_id INT NOT NULL,
        session_date DATE NOT NULL,
        notes NVARCHAR(500) NULL,
        created_by_user_id INT NOT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_session_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_cp_session_fiscal_year FOREIGN KEY (fiscal_year_id) REFERENCES dbo.cp_fiscal_years(fiscal_year_id),
        CONSTRAINT FK_cp_session_program FOREIGN KEY (program_id) REFERENCES dbo.cp_programs(program_id),
        CONSTRAINT FK_cp_session_fiscal_activity FOREIGN KEY (activity_id, fiscal_year_id, program_id)
            REFERENCES dbo.cp_fiscal_activities(activity_id, fiscal_year_id, program_id),
        CONSTRAINT FK_cp_session_creator FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(user_id)
    );
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_cp_session_period_program' AND object_id = OBJECT_ID(N'dbo.cp_activity_sessions'))
    CREATE INDEX IX_cp_session_period_program ON dbo.cp_activity_sessions(fiscal_year_id, program_id, session_date);

IF COL_LENGTH(N'dbo.cp_activity_sessions', N'duration_minutes') IS NULL
    ALTER TABLE dbo.cp_activity_sessions ADD duration_minutes INT NULL;

IF OBJECT_ID(N'dbo.cp_attendance', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_attendance (
        session_id INT NOT NULL,
        participant_id INT NOT NULL,
        is_present BIT NOT NULL CONSTRAINT DF_cp_attendance_present DEFAULT 0,
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_attendance_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_cp_attendance PRIMARY KEY (session_id, participant_id),
        CONSTRAINT FK_cp_attendance_session FOREIGN KEY (session_id) REFERENCES dbo.cp_activity_sessions(session_id),
        CONSTRAINT FK_cp_attendance_participant FOREIGN KEY (participant_id) REFERENCES dbo.cp_participants(participant_id)
    );
END;

IF OBJECT_ID(N'dbo.cp_grade_reports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_grade_reports (
        report_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        fiscal_year_id INT NOT NULL,
        program_id INT NOT NULL,
        report_month INT NOT NULL,
        report_year INT NOT NULL,
        notes NVARCHAR(500) NULL,
        created_by_user_id INT NOT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_grade_report_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_grade_report_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_cp_grade_report_period UNIQUE (fiscal_year_id, program_id, report_year, report_month),
        CONSTRAINT CK_cp_grade_report_month CHECK (report_month BETWEEN 1 AND 12),
        CONSTRAINT CK_cp_grade_report_year CHECK (report_year BETWEEN 1000 AND 9999),
        CONSTRAINT FK_cp_grade_report_year FOREIGN KEY (fiscal_year_id) REFERENCES dbo.cp_fiscal_years(fiscal_year_id),
        CONSTRAINT FK_cp_grade_report_program FOREIGN KEY (program_id) REFERENCES dbo.cp_programs(program_id),
        CONSTRAINT FK_cp_grade_report_creator FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(user_id)
    );
END;

IF OBJECT_ID(N'dbo.cp_grade_items', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_grade_items (
        report_id INT NOT NULL,
        participant_id INT NOT NULL,
        grade_level VARCHAR(20) NULL,
        is_content_room BIT NOT NULL CONSTRAINT DF_cp_grade_item_content DEFAULT 0,
        spanish_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_spanish_grade CHECK (spanish_grade IS NULL OR spanish_grade BETWEEN 0 AND 100),
        english_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_english_grade CHECK (english_grade IS NULL OR english_grade BETWEEN 0 AND 100),
        math_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_math_grade CHECK (math_grade IS NULL OR math_grade BETWEEN 0 AND 100),
        science_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_science_grade CHECK (science_grade IS NULL OR science_grade BETWEEN 0 AND 100),
        social_studies_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_social_studies_grade CHECK (social_studies_grade IS NULL OR social_studies_grade BETWEEN 0 AND 100),
        elective_1_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_elective_1_grade CHECK (elective_1_grade IS NULL OR elective_1_grade BETWEEN 0 AND 100),
        elective_2_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_elective_2_grade CHECK (elective_2_grade IS NULL OR elective_2_grade BETWEEN 0 AND 100),
        elective_3_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_elective_3_grade CHECK (elective_3_grade IS NULL OR elective_3_grade BETWEEN 0 AND 100),
        elective_4_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_elective_4_grade CHECK (elective_4_grade IS NULL OR elective_4_grade BETWEEN 0 AND 100),
        average_grade NUMERIC(5,2) NULL CONSTRAINT CK_cp_grade_average_grade CHECK (average_grade IS NULL OR average_grade BETWEEN 0 AND 100),
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_grade_item_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_grade_item_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_cp_grade_items PRIMARY KEY (report_id, participant_id),
        CONSTRAINT FK_cp_grade_item_report FOREIGN KEY (report_id) REFERENCES dbo.cp_grade_reports(report_id),
        CONSTRAINT FK_cp_grade_item_participant FOREIGN KEY (participant_id) REFERENCES dbo.cp_participants(participant_id)
    );
END;
"""
