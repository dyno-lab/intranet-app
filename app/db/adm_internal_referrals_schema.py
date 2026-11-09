"""One-time repair of missing internal-referral ADM mappings in proposals 005/006."""

ADM_INTERNAL_REFERRALS_SQL = """
IF NOT EXISTS (
    SELECT 1 FROM dbo.platform_data_migrations WITH (UPDLOCK, HOLDLOCK)
    WHERE migration_key = 'faro_adm_internal_referrals_005_006_v1'
)
BEGIN
    DECLARE @PendingInternalReferrals TABLE (
        proposal_id INT NOT NULL,
        activity_code_id INT NOT NULL,
        PRIMARY KEY (proposal_id, activity_code_id)
    );

    INSERT INTO @PendingInternalReferrals (proposal_id, activity_code_id)
    SELECT proposal.proposal_id, activity.activity_code_id
    FROM dbo.proposals AS proposal
    CROSS JOIN dbo.activity_codes AS activity
    WHERE proposal.code IN ('005', '006')
      AND LOWER(LTRIM(RTRIM(activity.code))) IN ('2.a.3', '3.a.3', '3.a.11', '3.a.21')
      AND (
          activity.proposal_id = proposal.proposal_id
          OR EXISTS (
              SELECT 1 FROM dbo.proposal_activity_codes AS assignment
              WHERE assignment.proposal_id = proposal.proposal_id
                AND assignment.activity_code_id = activity.activity_code_id
          )
          OR EXISTS (
              SELECT 1 FROM dbo.activity_sessions AS session
              WHERE session.proposal_id = proposal.proposal_id
                AND session.activity_code_id = activity.activity_code_id
          )
      )
      AND NOT EXISTS (
          SELECT 1
          FROM dbo.adm_service_type_activity_codes AS mapping WITH (UPDLOCK, HOLDLOCK)
          JOIN dbo.adm_service_types AS service_type
            ON service_type.adm_service_type_id = mapping.adm_service_type_id
          WHERE mapping.activity_code_id = activity.activity_code_id
            AND service_type.proposal_id = proposal.proposal_id
      );

    -- Never guess a type by its ID/order or overwrite a configured classification.
    IF EXISTS (
        SELECT pending.proposal_id
        FROM @PendingInternalReferrals AS pending
        LEFT JOIN dbo.adm_service_types AS service_type
          ON service_type.proposal_id = pending.proposal_id
         AND service_type.is_active = 1
         AND LTRIM(RTRIM(service_type.name)) = N'Servicios consejería, orientación y trabajo social'
        GROUP BY pending.proposal_id, pending.activity_code_id
        HAVING COUNT(service_type.adm_service_type_id) <> 1
    )
    BEGIN
        ;THROW 51001, 'No se pudo clasificar los referidos internos: debe existir un solo tipo ADM activo Servicios consejería, orientación y trabajo social por propuesta.', 1;
    END;

    INSERT INTO dbo.adm_service_type_activity_codes (adm_service_type_id, activity_code_id)
    SELECT service_type.adm_service_type_id, pending.activity_code_id
    FROM @PendingInternalReferrals AS pending
    JOIN dbo.adm_service_types AS service_type
      ON service_type.proposal_id = pending.proposal_id
     AND service_type.is_active = 1
     AND LTRIM(RTRIM(service_type.name)) = N'Servicios consejería, orientación y trabajo social';

    INSERT INTO dbo.platform_data_migrations (migration_key)
    VALUES ('faro_adm_internal_referrals_005_006_v1');
END;
"""
