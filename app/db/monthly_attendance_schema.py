"""Additive, repeatable schema; deployment starts tracking the preceding month."""
MONTHLY_ATTENDANCE_SQL = """
IF COL_LENGTH(N'dbo.faro_announcements', N'action_url') IS NULL
    ALTER TABLE dbo.faro_announcements ADD action_url VARCHAR(500) NULL;
IF OBJECT_ID(N'dbo.monthly_attendance_settings', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.monthly_attendance_settings (
        settings_id INT NOT NULL PRIMARY KEY,
        first_month DATE NOT NULL,
        CONSTRAINT CK_monthly_attendance_settings_singleton CHECK (settings_id = 1)
    );
END;
IF NOT EXISTS (SELECT 1 FROM dbo.monthly_attendance_settings WHERE settings_id=1)
    INSERT INTO dbo.monthly_attendance_settings(settings_id, first_month)
    VALUES (1, DATEADD(month, DATEDIFF(month, 0, GETDATE()) - 1, 0));
IF OBJECT_ID(N'dbo.attendance_months', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.attendance_months (
        proposal_id INT NOT NULL REFERENCES dbo.proposals(proposal_id),
        report_year INT NOT NULL, report_month INT NOT NULL,
        due_on DATE NOT NULL, revision INT NOT NULL DEFAULT 0,
        all_announcement_id INT NULL REFERENCES dbo.faro_announcements(announcement_id),
        CONSTRAINT PK_attendance_months PRIMARY KEY(proposal_id, report_year, report_month),
        CONSTRAINT CK_attendance_month_period CHECK (report_month BETWEEN 1 AND 12 AND report_year BETWEEN 2000 AND 2100)
    );
END;
IF OBJECT_ID(N'dbo.attendance_month_residentials', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.attendance_month_residentials (
        proposal_id INT NOT NULL, report_year INT NOT NULL, report_month INT NOT NULL,
        residential_id INT NOT NULL REFERENCES dbo.residentials(residential_id),
        is_included BIT NOT NULL DEFAULT 1, revision INT NOT NULL DEFAULT 0,
        confirmed_revision INT NULL, fingerprint VARCHAR(64) NULL,
        confirmed_at DATETIMEOFFSET NULL,
        confirmed_by_user_id INT NULL REFERENCES dbo.users(user_id), confirmed_by_name NVARCHAR(255) NULL,
        note NVARCHAR(1000) NULL, no_activity BIT NOT NULL DEFAULT 0,
        confirmed_sessions INT NULL, confirmed_participations INT NULL,
        confirmation_announcement_id INT NULL REFERENCES dbo.faro_announcements(announcement_id),
        last_reminded_at DATETIMEOFFSET NULL,
        reminder_announcement_id INT NULL REFERENCES dbo.faro_announcements(announcement_id),
        CONSTRAINT PK_attendance_month_residentials PRIMARY KEY(proposal_id, report_year, report_month, residential_id),
        CONSTRAINT FK_attendance_month_residential_period FOREIGN KEY(proposal_id, report_year, report_month)
            REFERENCES dbo.attendance_months(proposal_id, report_year, report_month)
    );
END;
IF OBJECT_ID(N'dbo.attendance_month_events', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.attendance_month_events (
        event_id INT IDENTITY PRIMARY KEY,
        proposal_id INT NOT NULL, report_year INT NOT NULL, report_month INT NOT NULL,
        residential_id INT NULL REFERENCES dbo.residentials(residential_id),
        kind VARCHAR(30) NOT NULL, actor_user_id INT NOT NULL REFERENCES dbo.users(user_id),
        actor_name NVARCHAR(255) NOT NULL, created_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        message NVARCHAR(2000) NOT NULL,
        announcement_id INT NULL REFERENCES dbo.faro_announcements(announcement_id),
        CONSTRAINT FK_attendance_month_event_period FOREIGN KEY(proposal_id, report_year, report_month)
            REFERENCES dbo.attendance_months(proposal_id, report_year, report_month)
    );
    CREATE INDEX IX_attendance_month_events_period ON dbo.attendance_month_events(proposal_id, report_year, report_month, event_id);
END;
"""
