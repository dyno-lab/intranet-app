"""Additive SQL Server migration; repeatable and independent of source data."""
DATA_VALIDATION_SQL = """
IF OBJECT_ID(N'dbo.faro_validation_issues', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.faro_validation_issues (
        issue_key VARCHAR(64) NOT NULL PRIMARY KEY,
        proposal_id INT NOT NULL REFERENCES dbo.proposals(proposal_id),
        residential_id INT NULL REFERENCES dbo.residentials(residential_id),
        other_residential_id INT NULL REFERENCES dbo.residentials(residential_id),
        kind VARCHAR(20) NOT NULL, session_date DATE NULL,
        fingerprint VARCHAR(64) NOT NULL, evidence_json NVARCHAR(MAX) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        assignee VARCHAR(20) NULL, due_on DATE NULL,
        justification NVARCHAR(1000) NULL, revision INT NOT NULL DEFAULT 1,
        checked_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_faro_validation_status CHECK(status IN ('pending','review','resolved','justified'))
    );
    CREATE INDEX IX_faro_validation_scope ON dbo.faro_validation_issues(proposal_id, residential_id, session_date);
END;
IF OBJECT_ID(N'dbo.faro_validation_events', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.faro_validation_events (
        event_id INT IDENTITY PRIMARY KEY,
        issue_key VARCHAR(64) NOT NULL REFERENCES dbo.faro_validation_issues(issue_key),
        actor_user_id INT NOT NULL REFERENCES dbo.users(user_id),
        actor_name NVARCHAR(255) NOT NULL, kind VARCHAR(20) NOT NULL,
        message NVARCHAR(2000) NOT NULL,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_faro_validation_event_issue ON dbo.faro_validation_events(issue_key, event_id);
END;
"""
