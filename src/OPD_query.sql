SELECT 
    FormattedDate,
    Doctor_Name,
    Patient_Code,
    Episode_key,
    visit_id,
    Note,
    ICD10_code,
    ShortName
FROM dbo.clincial_notes_opd_temp
WHERE Note IS NOT NULL
  AND LTRIM(RTRIM(Note)) <> ''
  AND FormattedDate = (
      SELECT MAX(FormattedDate)
      FROM dbo.clincial_notes_opd_temp
      WHERE Note IS NOT NULL
        AND LTRIM(RTRIM(Note)) <> ''
  )
ORDER BY FormattedDate DESC;
