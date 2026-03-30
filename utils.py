import json
from typing import List, Dict, Tuple
import pandas as pd
import re

# Field definitions for reference
REQUIRED_FIELDS = [
    "Chief_Complain",
    "History", 
    "Allergy",
    "Comorbidities",
    "Clinical_Examination",
    "Diagnosis",
    "Treatment_Plan"
]

def export_to_json(structured_data: List[Dict], pretty: bool = True) -> str:
    try:
        if pretty:
            return json.dumps(structured_data, indent=2, ensure_ascii=False)
        else:
            return json.dumps(structured_data, ensure_ascii=False)
            
    except Exception as e:
        raise Exception(f"Error exporting to JSON: {str(e)}")


def filter_empty_records(data: List[Dict]) -> Tuple[List[Dict], int]:
    if not data:
        return data, 0
    
    filtered_data = []
    removed_count = 0
    
    for record in data:
        # Check if all required fields are empty or None
        all_empty = True
        for field in REQUIRED_FIELDS:
            value = record.get(field)
            if value is not None and str(value).strip() != "":
                all_empty = False
                break
        
        if not all_empty:
            filtered_data.append(record)
        else:
            removed_count += 1
    
    return filtered_data, removed_count


def get_field_label(field_name: str) -> str:
    return FIELD_LABELS.get(field_name, field_name.replace("_", " ").title())


def clean_extracted_data(data: List[Dict]) -> List[Dict]:
    if not data:
        return data
    
    cleaned_data = []
    
    for record in data:
        cleaned_record = {}
        
        for field in REQUIRED_FIELDS:
            value = record.get(field, "")
            
            # Convert to string and clean
            if value is None or pd.isna(value):
                cleaned_record[field] = ""
            else:
                # Convert to string and strip whitespace
                cleaned_value = str(value).strip()
                
                # Remove excessive whitespace
                cleaned_value = re.sub(r'\s+', ' ', cleaned_value)
                
                # Remove common artifacts
                cleaned_value = re.sub(r'^[-*•]\s*', '', cleaned_value)  # Remove bullet points
                cleaned_value = re.sub(r'\n+', ' ', cleaned_value)  # Replace newlines with spaces
                
                cleaned_record[field] = cleaned_value
        
        # Copy any additional fields
        for key, value in record.items():
            if key not in REQUIRED_FIELDS:
                cleaned_record[key] = value
        
        cleaned_data.append(cleaned_record)
    
    return cleaned_data


def merge_dataframes(original_df: pd.DataFrame, extracted_df: pd.DataFrame) -> pd.DataFrame:
    try:
        # Reset indices to ensure proper alignment
        original_df = original_df.reset_index(drop=True)
        extracted_df = extracted_df.reset_index(drop=True)
        
        # Concatenate side by side
        merged_df = pd.concat([original_df, extracted_df], axis=1)
        
        return merged_df
        
    except Exception as e:
        raise Exception(f"Error merging dataframes: {str(e)}")


