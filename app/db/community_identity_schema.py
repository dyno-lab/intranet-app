"""Additive, idempotent SQL Server DDL for explicit identity reviews."""

COMMUNITY_IDENTITY_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.cp_identity_reviews', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_identity_reviews (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        cp_participant_id INT NOT NULL,
        faro_participant_id INT NOT NULL,
        is_same_person BIT NOT NULL,
        reviewed_from VARCHAR(20) NOT NULL,
        reviewed_by_user_id INT NOT NULL,
        reviewed_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_identity_reviewed DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_cp_identity_pair UNIQUE (cp_participant_id, faro_participant_id),
        CONSTRAINT CK_cp_identity_source CHECK (reviewed_from IN ('community', 'faro')),
        CONSTRAINT FK_cp_identity_community FOREIGN KEY (cp_participant_id) REFERENCES dbo.cp_participants(participant_id),
        CONSTRAINT FK_cp_identity_faro FOREIGN KEY (faro_participant_id) REFERENCES dbo.participants(participant_id),
        CONSTRAINT FK_cp_identity_reviewer FOREIGN KEY (reviewed_by_user_id) REFERENCES dbo.users(user_id)
    );
END;
IF COL_LENGTH('dbo.cp_identity_reviews', 'comparison_fingerprint') IS NULL
    ALTER TABLE dbo.cp_identity_reviews ADD comparison_fingerprint VARCHAR(64) NULL;
IF COL_LENGTH('dbo.cp_identity_reviews', 'needs_review') IS NULL
    ALTER TABLE dbo.cp_identity_reviews ADD needs_review BIT NOT NULL CONSTRAINT DF_cp_identity_needs_review DEFAULT 0;
IF COL_LENGTH('dbo.cp_identity_reviews', 'revision') IS NULL
    ALTER TABLE dbo.cp_identity_reviews ADD revision INT NOT NULL CONSTRAINT DF_cp_identity_revision DEFAULT 1;
IF OBJECT_ID(N'dbo.cp_identity_review_events', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cp_identity_review_events (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        review_id INT NOT NULL REFERENCES dbo.cp_identity_reviews(id),
        previous_decision BIT NULL,
        decision BIT NULL,
        comparison_fingerprint VARCHAR(64) NULL,
        reviewed_from VARCHAR(20) NOT NULL,
        reviewed_by_user_id INT NOT NULL REFERENCES dbo.users(user_id),
        reviewed_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_cp_identity_event_at DEFAULT SYSUTCDATETIME(),
        reason NVARCHAR(500) NULL
    );
    CREATE INDEX IX_cp_identity_events_review ON dbo.cp_identity_review_events(review_id);
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.cp_identity_reviews') AND name = N'UQ_cp_identity_confirmed_community')
BEGIN
    CREATE UNIQUE INDEX UQ_cp_identity_confirmed_community ON dbo.cp_identity_reviews(cp_participant_id)
        WHERE is_same_person = 1;
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.cp_identity_reviews') AND name = N'UQ_cp_identity_confirmed_faro')
BEGIN
    CREATE UNIQUE INDEX UQ_cp_identity_confirmed_faro ON dbo.cp_identity_reviews(faro_participant_id)
        WHERE is_same_person = 1;
END;
"""
