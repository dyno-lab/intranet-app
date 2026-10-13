NOTIFICATIONS_SQL = """
IF OBJECT_ID(N'dbo.faro_announcements', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.faro_announcements (
        announcement_id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_faro_announcements PRIMARY KEY,
        title NVARCHAR(160) NOT NULL,
        message NVARCHAR(4000) NOT NULL,
        starts_on DATE NOT NULL,
        ends_on DATE NULL,
        is_active BIT NOT NULL CONSTRAINT DF_faro_announcement_active DEFAULT 1,
        created_by_user_id INT NOT NULL,
        created_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_faro_announcement_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_faro_announcement_author FOREIGN KEY (created_by_user_id) REFERENCES dbo.users(user_id),
        CONSTRAINT CK_faro_announcement_dates CHECK (ends_on IS NULL OR ends_on >= starts_on)
    );
    CREATE INDEX IX_faro_announcement_visibility ON dbo.faro_announcements(is_active, starts_on, ends_on);
END;
IF OBJECT_ID(N'dbo.faro_announcement_roles', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.faro_announcement_roles (
        announcement_id INT NOT NULL,
        role VARCHAR(20) NOT NULL,
        CONSTRAINT PK_faro_announcement_roles PRIMARY KEY (announcement_id, role),
        CONSTRAINT FK_faro_announcement_role FOREIGN KEY (announcement_id)
            REFERENCES dbo.faro_announcements(announcement_id) ON DELETE CASCADE,
        CONSTRAINT CK_faro_announcement_role CHECK (role IN ('admin', 'supervisor', 'user', 'viewer'))
    );
END;
IF OBJECT_ID(N'dbo.faro_announcement_residentials', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.faro_announcement_residentials (
        announcement_id INT NOT NULL,
        residential_id INT NOT NULL,
        CONSTRAINT PK_faro_announcement_residentials PRIMARY KEY (announcement_id, residential_id),
        CONSTRAINT FK_faro_announcement_residential_notice FOREIGN KEY (announcement_id)
            REFERENCES dbo.faro_announcements(announcement_id) ON DELETE CASCADE,
        CONSTRAINT FK_faro_announcement_residential FOREIGN KEY (residential_id)
            REFERENCES dbo.residentials(residential_id)
    );
END;
IF OBJECT_ID(N'dbo.faro_announcement_reads', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.faro_announcement_reads (
        announcement_id INT NOT NULL,
        user_id INT NOT NULL,
        read_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_faro_announcement_read DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_faro_announcement_reads PRIMARY KEY (announcement_id, user_id),
        CONSTRAINT FK_faro_announcement_read_notice FOREIGN KEY (announcement_id)
            REFERENCES dbo.faro_announcements(announcement_id) ON DELETE CASCADE,
        CONSTRAINT FK_faro_announcement_read_user FOREIGN KEY (user_id) REFERENCES dbo.users(user_id)
    );
END;
"""
