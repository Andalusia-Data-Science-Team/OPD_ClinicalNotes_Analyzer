"""
Generic data processing utilities (department-agnostic). Functions take
required_fields as a parameter instead of relying on a hardcoded module-level
list, so the same code works for OPD and ER.
"""
import pandas as pd
from typing import List, Dict
import re
import html


def strip_html_tags(text: str) -> str:
    """Remove HTML tags, CSS, JavaScript, and decode HTML entities from text."""
    if not text or not isinstance(text, str):
        return ""

    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'@[a-z-]+[^{]*\{[^}]*\}', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\.[a-z-]+[^{]*\{[^}]*\}', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'@[^;]+;', '', text)
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\b[a-z0-9]+-[a-z0-9]+-[a-z0-9]+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[a-z]+-[a-z0-9]{1,3}\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[a-z-]+:\s*[^;]+;', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'</[a-z]+>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[a-z-]+=[\'\"][^\'"]*[\'\"]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'["\']>', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    if not text or (len(text) < 30 and len(re.findall(r'[<>{}"\']', text)) > 0):
        return ""

    return text


def validate_structured_data(data: List[Dict], required_fields: List[str], verbose: bool = False) -> bool:
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

        missing_fields = [field for field in required_fields if field not in record]
        if missing_fields:
            if verbose:
                print(f"   Record {i}: Missing fields: {missing_fields}")
            continue

        valid_count += 1

    if verbose:
        print(f"   Validated {valid_count}/{total_count} records")

    return valid_count == total_count


def get_data_summary(data: List[Dict], required_fields: List[str]) -> Dict:
    if not data:
        return {'total_records': 0, 'completion_rate': 0.0, 'fields_populated': {}}

    total_records = len(data)
    fields_populated = {}

    for field in required_fields:
        count = sum(1 for record in data if record.get(field) and str(record[field]).strip())
        percentage = (count / total_records) * 100
        fields_populated[field] = {'count': count, 'percentage': percentage}

    total_possible = total_records * len(required_fields)
    total_populated = sum(stats['count'] for stats in fields_populated.values())
    completion_rate = (total_populated / total_possible) * 100 if total_possible > 0 else 0

    return {
        'total_records': total_records,
        'completion_rate': completion_rate,
        'fields_populated': fields_populated,
    }


def calculate_icd10_accuracy(ai_icd10: str, actual_icd10: str) -> int:
    """Return 1 if any AI code matches an actual code at the base/chapter level, else 0; None if inputs missing."""
    if not ai_icd10 or not actual_icd10 or pd.isna(actual_icd10) or pd.isna(ai_icd10):
        return None

    def _parse_codes(raw: str):
        return set(re.findall(r'[A-Z][0-9]{2,3}(?:\.[0-9A-Za-z]+)?', str(raw).upper().replace(" ", "")))

    def _base(code: str) -> str:
        return code.split(".")[0]

    ai_codes = _parse_codes(ai_icd10)
    actual_codes = _parse_codes(actual_icd10)

    if not actual_codes:
        return None

    ai_bases = {_base(c) for c in ai_codes}
    actual_bases = {_base(c) for c in actual_codes}
    return 1 if (ai_bases & actual_bases) else 0
