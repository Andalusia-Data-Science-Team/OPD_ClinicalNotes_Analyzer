import pandas as pd
from typing import List, Dict, Tuple


# Required fields for OPD extraction
REQUIRED_FIELDS = [
    "Chief_Complain",
    "History", 
    "Allergy",
    "Comorbidities",
    "Clinical_Examination",
    "Diagnosis",
    "Treatment_Plan"
]


def validate_structured_data(data: List[Dict], verbose: bool = False) -> bool:
    if not data:
        if verbose:
            print("   Warning: No data to validate")
        return False
    
    valid_count = 0
    total_count = len(data)
    
    for i, record in enumerate(data):
        if not isinstance(record, dict):
            if verbose:
                print(f"   Record {i}: Not a dictionary")
            continue
            
        # Check if required fields exist (even if empty)
        missing_fields = [field for field in REQUIRED_FIELDS if field not in record]
        if missing_fields:
            if verbose:
                print(f"   Record {i}: Missing fields: {missing_fields}")
            continue
            
        valid_count += 1
    
    if verbose:
        print(f"   Validated {valid_count}/{total_count} records")
    
    return valid_count == total_count


def get_data_summary(data: List[Dict]) -> Dict:
    if not data:
        return {
            'total_records': 0,
            'completion_rate': 0.0,
            'fields_populated': {}
        }
    
    total_records = len(data)
    fields_populated = {}
    
    # Calculate population for each field
    for field in REQUIRED_FIELDS:
        count = sum(1 for record in data if record.get(field) and str(record[field]).strip())
        percentage = (count / total_records) * 100
        fields_populated[field] = {
            'count': count,
            'percentage': percentage
        }
    
    # Calculate overall completion rate
    total_possible = total_records * len(REQUIRED_FIELDS)
    total_populated = sum(stats['count'] for stats in fields_populated.values())
    completion_rate = (total_populated / total_possible) * 100 if total_possible > 0 else 0
    
    return {
        'total_records': total_records,
        'completion_rate': completion_rate,
        'fields_populated': fields_populated
    }



def calculate_icd10_accuracy(ai_icd10: str, actual_icd10: str) -> str:
    if not ai_icd10 or not actual_icd10 or pd.isna(actual_icd10):
        return "N/A"
    
    # Normalize codes (remove spaces, convert to uppercase)
    ai_normalized = str(ai_icd10).replace(" ", "").upper()
    actual_normalized = str(actual_icd10).replace(" ", "").upper()
    
    if ai_normalized == actual_normalized:
        return "Correct"
    elif ai_normalized.startswith(actual_normalized[:3]):
        return "Partial"
    else:
        return "Incorrect"


def opd_scoring(record: dict) -> float:
    def present(key) -> bool:
        """NaN-safe field presence check."""
        value = record.get(key)
        return value is not None and not pd.isna(value) and str(value).strip() != ""
    
    # Define field weights
    field_weights = {
        "Chief_Complain": 0.20,
        "History": 0.15,
        "Allergy": 0.10,
        "Comorbidities": 0.10,
        "Clinical_Examination": 0.20,
        "Diagnosis": 0.15,
        "Treatment_Plan": 0.10
    }
    
    score = 0.0
    for field, weight in field_weights.items():
        if present(field):
            score += weight
    
    return min(score, 1.0)
