"""Additive, idempotent SQL Server migration; importing it does not connect."""
COMMUNITY_ALERTS_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.cp_announcements', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_announcements (
        announcement_id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_cp_announcements PRIMARY KEY,
        title NVARCHAR(160) NOT NULL,
        message NVARCHAR(4000) NOT NULL,
        starts_on DATE NOT NULL,
        ends_on DATE NULL,
        is_active BIT NOT NULL CONSTRAINT DF_cp_announcement_active DEFAULT 1,
        created_by_user_id INT NOT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_announcement_created DEFAULT SYSUTCDATETIME(),
        withdrawn_by_user_id INT NULL,
        withdrawn_at DATETIMEOFFSET NULL,
        CONSTRAINT FK_cp_announcement_author FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(user_id),
        CONSTRAINT FK_cp_announcement_withdrawn_by FOREIGN KEY (withdrawn_by_user_id) REFERENCES dbo.users(user_id),
        CONSTRAINT CK_cp_announcement_dates CHECK (ends_on IS NULL OR ends_on >= starts_on)
    );
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_cp_announcement_visibility' AND object_id = OBJECT_ID(N'dbo.cp_announcements'))
    CREATE INDEX IX_cp_announcement_visibility ON dbo.cp_announcements(is_active, starts_on, ends_on);

IF OBJECT_ID(N'dbo.cp_announcement_roles', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_announcement_roles (
        announcement_id INT NOT NULL,
        role VARCHAR(20) NOT NULL,
        CONSTRAINT PK_cp_announcement_roles PRIMARY KEY (announcement_id, role),
        CONSTRAINT FK_cp_announcement_role FOREIGN KEY (announcement_id)
            REFERENCES dbo.cp_announcements(announcement_id) ON DELETE CASCADE,
        CONSTRAINT CK_cp_announcement_role CHECK (role IN ('admin', 'supervisor', 'user', 'viewer'))
    );
END;
IF OBJECT_ID(N'dbo.cp_announcement_programs', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_announcement_programs (
        announcement_id INT NOT NULL,
        program_id INT NOT NULL,
        CONSTRAINT PK_cp_announcement_programs PRIMARY KEY (announcement_id, program_id),
        CONSTRAINT FK_cp_announcement_program_notice FOREIGN KEY (announcement_id)
            REFERENCES dbo.cp_announcements(announcement_id) ON DELETE CASCADE,
        CONSTRAINT FK_cp_announcement_program FOREIGN KEY (program_id) REFERENCES dbo.cp_programs(program_id)
    );
END;
IF OBJECT_ID(N'dbo.cp_announcement_reads', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_announcement_reads (
        announcement_id INT NOT NULL,
        user_id INT NOT NULL,
        read_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_announcement_read DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_cp_announcement_reads PRIMARY KEY (announcement_id, user_id),
        CONSTRAINT FK_cp_announcement_read_notice FOREIGN KEY (announcement_id)
            REFERENCES dbo.cp_announcements(announcement_id) ON DELETE CASCADE,
        CONSTRAINT FK_cp_announcement_read_user FOREIGN KEY (user_id) REFERENCES dbo.users(user_id)
    );
END;
"""
