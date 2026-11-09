"""Additive history storage; replace single enrollment with one CURRENT stay."""
PARTICIPANT_TRANSFERS_SQL = """
SET XACT_ABORT ON;
IF COL_LENGTH(N'dbo.proposal_participants', N'valid_from') IS NULL
    ALTER TABLE dbo.proposal_participants ADD valid_from DATE NULL;
IF COL_LENGTH(N'dbo.proposal_participants', N'valid_until') IS NULL
    ALTER TABLE dbo.proposal_participants ADD valid_until DATE NULL;
IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.proposal_participants')
           AND name=N'UQ_proposal_participants_proposal_person')
    ALTER TABLE dbo.proposal_participants DROP CONSTRAINT UQ_proposal_participants_proposal_person;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.proposal_participants')
               AND name=N'UX_proposal_participants_current_person')
    EXEC(N'CREATE UNIQUE INDEX UX_proposal_participants_current_person
           ON dbo.proposal_participants(proposal_id, person_id) WHERE valid_until IS NULL');
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.proposal_participants')
               AND name=N'CK_proposal_participant_stay_dates')
    EXEC(N'ALTER TABLE dbo.proposal_participants ADD CONSTRAINT CK_proposal_participant_stay_dates
           CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from < valid_until)');
IF OBJECT_ID(N'dbo.participant_residential_numbers', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.participant_residential_numbers (
        number_id INT IDENTITY PRIMARY KEY,
        participant_id INT NOT NULL REFERENCES dbo.participants(participant_id),
        residential_id INT NOT NULL REFERENCES dbo.residentials(residential_id),
        sequence VARCHAR(4) NULL,
        expediente_num VARCHAR(50) NOT NULL UNIQUE,
        exp_year INT NOT NULL
    );
    CREATE INDEX IX_participant_residential_numbers_participant_id ON dbo.participant_residential_numbers(participant_id);
    CREATE UNIQUE INDEX UX_participant_residential_number
        ON dbo.participant_residential_numbers(residential_id, sequence) WHERE sequence IS NOT NULL;
END;
IF OBJECT_ID(N'dbo.participant_transfers', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.participant_transfers (
        transfer_id INT IDENTITY PRIMARY KEY,
        participant_id INT NOT NULL REFERENCES dbo.participants(participant_id),
        from_residential_id INT NOT NULL REFERENCES dbo.residentials(residential_id),
        to_residential_id INT NOT NULL REFERENCES dbo.residentials(residential_id),
        effective_date DATE NOT NULL,
        old_expediente_num VARCHAR(50) NOT NULL,
        new_expediente_num VARCHAR(50) NOT NULL,
        proposal_codes VARCHAR(1000) NOT NULL,
        reason NVARCHAR(500) NOT NULL,
        created_by_user_id INT NOT NULL REFERENCES dbo.users(user_id),
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_participant_transfer_destination CHECK (from_residential_id <> to_residential_id)
    );
    CREATE INDEX IX_participant_transfers_participant_id ON dbo.participant_transfers(participant_id);
END;
"""
