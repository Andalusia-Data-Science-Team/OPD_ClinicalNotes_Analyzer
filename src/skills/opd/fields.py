"""
OPD skill: field schema, field-name aliases (for normalizing AI output),
and the OPD-specific Documentation Appropriateness score.
"""
import pandas as pd

REQUIRED_FIELDS = [
    "Chief_Complain",
    "History",
    "Comorbidities",
    "Clinical_Examination",
    "Diagnosis",
    "Treatment_Plan",
    "icd10_AI_Generated",
    "Final_Diagnosis",
    "Arabic_Treatment_Plan",
    "Surgery_Visit_Type",
]

# Maps variant keys the model might emit -> canonical OPD field name
FIELD_ALIASES = {
    "Chief_Complaint": "Chief_Complain",
    "Examination": "Clinical_Examination",
    "Physical_Examination": "Clinical_Examination",
    "Plan": "Treatment_Plan",
    "Management": "Treatment_Plan",
}


def scoring_fn(record: dict, actual_icd10: str = None) -> float:
    """
    OPD Documentation Appropriateness score (0-100), weighted by field.
    Treatment_Plan 50% / Chief_Complain 20% / Diagnosis 10% /
    Clinical_Examination 10% / Comorbidities 5% / History 5%
    """
    def present(key: str) -> bool:
        try:
            value = record.get(key)
            if value is None or pd.isna(value):
                return False
            return len(str(value).strip()) >= 10
        except Exception:
            return False

    if not isinstance(record, dict):
        return 0.0

    field_weights = {
        "Treatment_Plan": 50,
        "Chief_Complain": 20,
        "Diagnosis": 10,
        "Clinical_Examination": 10,
        "Comorbidities": 5,
        "History": 5,
    }

    score = 0.0
    try:
        for field, weight in field_weights.items():
            if present(field):
                score += weight
        return round(min(score, 100.0))
    except Exception:
        return 0.0
