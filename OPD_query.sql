WITH DeduplicatedData AS (
    SELECT 
        FB.Service_Date AS FormattedDate,
        ds.Staff_name AS Doctor_Name,
        FB.patient_id AS Patient_Code,
        FB.Episode_key,
        CN.Note AS Note,
        DD.ICDDiagnoseCode AS ICD10_code,
        DO.ShortName,
        ROW_NUMBER() OVER (
            PARTITION BY ds.Staff_name, FB.patient_id, FB.Episode_key, CN.Note, DD.ICDDiagnoseCode
            ORDER BY FB.Service_Date DESC
        ) AS RowNum
    FROM DAX.FactBilling FB
    LEFT JOIN dax.DimCompany dc 
        ON FB.Company_Key = dc.Company_Key
    LEFT JOIN dax.DimClinicalNotes CN 
        ON CN.Episode_key = FB.Episode_key
    LEFT JOIN dax.DimDiagnosisN DD 
        ON FB.Episode_key = DD.Episode_Key
    LEFT JOIN dax.DimStaff ds 
        ON FB.Doctor_Key = ds.Staff_Key
    LEFT JOIN DAX.DimPatientEpisodeType PET 
        ON PET.PatientEpisodeType_Key = FB.PatientEpisodeType_Key
    LEFT JOIN DAX.DimOrganization DO
        ON FB.Organization_Key = DO.OrganizationKey
    WHERE-- FB.Organization_Key = 1    AND
	CAST(FB.Service_Date AS DATE) = CAST(DATEADD(DAY, -1, GETDATE()) AS DATE)
      AND dc.CashAccounts = 'Credit'
      AND PET.[Unified ShortName] = 'OPD'
      AND CN.Note IS NOT NULL
      AND EXISTS (
            SELECT 1
            FROM dax.DimStaff ds2
            WHERE ds2.degree_key = ds.degree_key
              AND LOWER(ds2.category_desc) LIKE '%doctor%'
      )
)
SELECT Top 1
    FormattedDate,
    Doctor_Name,
    Patient_Code,
    Episode_key,
    Note,
    ICD10_code,
    ShortName 
FROM DeduplicatedData
WHERE RowNum = 1
ORDER BY FormattedDate DESC;