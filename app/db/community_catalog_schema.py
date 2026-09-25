COMMUNITY_CATALOG_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.cp_catalog_types', N'U') IS NULL
CREATE TABLE dbo.cp_catalog_types (
 catalog_type_id INT IDENTITY PRIMARY KEY, field_key VARCHAR(80) NOT NULL UNIQUE, label NVARCHAR(150) NOT NULL,
 defaults_loaded BIT NOT NULL DEFAULT 0
);
IF COL_LENGTH(N'dbo.cp_catalog_types', N'defaults_loaded') IS NULL
 ALTER TABLE dbo.cp_catalog_types ADD defaults_loaded BIT NOT NULL CONSTRAINT DF_cp_catalog_defaults_loaded DEFAULT 0;
IF OBJECT_ID(N'dbo.cp_catalog_options', N'U') IS NULL
CREATE TABLE dbo.cp_catalog_options (
 option_id INT IDENTITY PRIMARY KEY, catalog_type_id INT NOT NULL REFERENCES dbo.cp_catalog_types(catalog_type_id),
 value NVARCHAR(150) NOT NULL, label NVARCHAR(150) NULL, sort_order INT NOT NULL DEFAULT 0,
 is_active BIT NOT NULL DEFAULT 1,
 CONSTRAINT UQ_cp_catalog_value UNIQUE(catalog_type_id,value)
);
IF COL_LENGTH(N'dbo.cp_catalog_options', N'label') IS NULL
 ALTER TABLE dbo.cp_catalog_options ADD label NVARCHAR(150) NULL;
IF COL_LENGTH(N'dbo.cp_catalog_options', N'sort_order') IS NULL
 ALTER TABLE dbo.cp_catalog_options ADD sort_order INT NOT NULL CONSTRAINT DF_cp_catalog_sort_order DEFAULT 0;
IF OBJECT_ID(N'dbo.cp_profile_fields', N'U') IS NULL
CREATE TABLE dbo.cp_profile_fields (
 field_id INT IDENTITY PRIMARY KEY, field_key VARCHAR(80) NOT NULL UNIQUE, label NVARCHAR(150) NOT NULL,
 field_type VARCHAR(20) NOT NULL DEFAULT 'text', is_required BIT NOT NULL DEFAULT 0,
 is_active BIT NOT NULL DEFAULT 1, sort_order INT NOT NULL DEFAULT 0,
 CONSTRAINT CK_cp_profile_type CHECK(field_type IN ('text','email','phone'))
);
IF OBJECT_ID(N'dbo.cp_profile_values', N'U') IS NULL
CREATE TABLE dbo.cp_profile_values (
 participant_id INT NOT NULL REFERENCES dbo.cp_participants(participant_id),
 field_id INT NOT NULL REFERENCES dbo.cp_profile_fields(field_id), value NVARCHAR(MAX) NOT NULL,
 CONSTRAINT PK_cp_profile_values PRIMARY KEY(participant_id,field_id)
);
"""
