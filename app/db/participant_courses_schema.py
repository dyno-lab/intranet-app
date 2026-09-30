PARTICIPANT_COURSES_SQL = """
IF OBJECT_ID(N'dbo.participant_monthly_courses', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.participant_monthly_courses (
        participant_id INT NOT NULL,
        report_year INT NOT NULL,
        report_month INT NOT NULL,
        course_code VARCHAR(30) NULL,
        revision INT NOT NULL CONSTRAINT DF_monthly_course_revision DEFAULT 1,
        updated_by_user_id INT NULL,
        updated_at DATETIMEOFFSET NOT NULL CONSTRAINT DF_monthly_course_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_participant_monthly_courses PRIMARY KEY (participant_id, report_year, report_month),
        CONSTRAINT FK_monthly_course_participant FOREIGN KEY (participant_id)
            REFERENCES dbo.participants(participant_id) ON DELETE CASCADE,
        CONSTRAINT CK_monthly_course_month CHECK (report_month BETWEEN 1 AND 12),
        CONSTRAINT CK_monthly_course_year CHECK (report_year BETWEEN 2000 AND 2100),
        CONSTRAINT CK_monthly_course_code CHECK
            (course_code IS NULL OR course_code IN ('reposteria', 'charcuteria', 'campo_laboral'))
    );
END;
"""
