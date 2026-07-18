"""
ER skill: field schema, field-name aliases (for normalizing AI output),
and the ER-specific Documentation Appropriateness score.
"""

REQUIRED_FIELDS = [
    "Patient_Identification",
    "Arrival_Triage",
    "Chief_Complaint",
    "Medical_Surgical_History",
    "Allergies_Adverse_Reactions",
    "Drug_History",
    "Vital_Signs_Initial",
    "Assessment",
    "Imaging_Results_Text",
    "Plan_Text",
    "Disposition_Discharge",
    "Recommended_ICD10",
]

# Maps variant keys (including OPD-style names) the model might emit -> canonical ER field name
FIELD_ALIASES = {
    "Chief_Complain": "Chief_Complaint",
    "Clinical_Examination": "Assessment",
    "Examination": "Assessment",
    "Physical_Examination": "Assessment",
    "Plan": "Plan_Text",
    "Treatment_Plan": "Plan_Text",
    "Management": "Plan_Text",
    "Disposition": "Disposition_Discharge",
    "Discharge": "Disposition_Discharge",
    "ICD10": "Recommended_ICD10",
    "ICD_10": "Recommended_ICD10",
    "icd10_AI_Generated": "Recommended_ICD10",
    "Diagnosis": "Recommended_ICD10",
    "History": "Medical_Surgical_History",
    "Past_Medical_History": "Medical_Surgical_History",
    "PMH": "Medical_Surgical_History",
    "Comorbidities": "Medical_Surgical_History",
    "Allergies": "Allergies_Adverse_Reactions",
    "Allergy": "Allergies_Adverse_Reactions",
    "Medications": "Drug_History",
    "Current_Medications": "Drug_History",
    "Vital_Signs": "Vital_Signs_Initial",
    "Vitals": "Vital_Signs_Initial",
    "Imaging": "Imaging_Results_Text",
    "Imaging_Results": "Imaging_Results_Text",
    "Triage": "Arrival_Triage",
    "Patient_ID": "Patient_Identification",
    "Patient_Info": "Patient_Identification",
}


def scoring_fn(record: dict, actual_icd10: str = None) -> float:
    """
    ER Documentation Appropriateness score (0-100), weighted by field.
    Assessment 25% / Plan_Text 15% / Chief_Complaint 15% /
    Vital_Signs_Initial 10% / Medical_Surgical_History 10% /
    Patient_Identification 5% / Allergies_Adverse_Reactions 5% /
    Drug_History 5% / Imaging_Results_Text 5% / Disposition_Discharge 5%
    """
    if not record:
        return None

    weights = {
        "Assessment": 25,
        "Plan_Text": 15,
        "Chief_Complaint": 15,
        "Vital_Signs_Initial": 10,
        "Medical_Surgical_History": 10,
        "Patient_Identification": 5,
        "Allergies_Adverse_Reactions": 5,
        "Drug_History": 5,
        "Imaging_Results_Text": 5,
        "Disposition_Discharge": 5,
    }

    score = 0.0
    for field, weight in weights.items():
        val = record.get(field, "")
        if val is not None and str(val).strip() not in ("", "None", "nan"):
            score += weight
    return round(score, 2)
