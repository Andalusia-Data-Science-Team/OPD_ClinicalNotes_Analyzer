"""
ER skill: get_user_prompt() only. SYSTEM_PROMPT now lives in
src/skills/er/SYSTEM_PROMPT.md and is loaded by skill_loader.py.
"""
import json


def get_user_prompt(notes_list, diagnosis_context=None):
    from src.skills.er.utils import classify_note_type

    if not notes_list:
        return "No clinical notes provided."

    formatted_notes = []
    for i, note in enumerate(notes_list):
        if not note.strip():
            continue

        note_text = f"**Note {i+1}:**\n{note.strip()}"

        if diagnosis_context and i < len(diagnosis_context):
            context = diagnosis_context[i]
            diagnosis_name = context.get('diagnosis_name', '')
            icd10_code = context.get('icd10_code', '')
            if diagnosis_name or icd10_code:
                note_text += "\n\n**BILLING REFERENCE (use as one of the codes if clinically supported):**"
                if diagnosis_name:
                    note_text += f"\n- Billing Diagnosis: {diagnosis_name}"
                if icd10_code:
                    note_text += f"\n- Billing ICD-10: {icd10_code}"

        formatted_notes.append(note_text)

    notes_text = "\n\n".join(formatted_notes)
    note_count = len(formatted_notes)

    empty_record = {
        "Patient_Identification": "", "Arrival_Triage": "", "Chief_Complaint": "",
        "Medical_Surgical_History": "",
        "Allergies_Adverse_Reactions": "", "Drug_History": "",
        "Vital_Signs_Initial": "", "Assessment": "",
        "Imaging_Results_Text": "", "Plan_Text": "",
        "Disposition_Discharge": "", "Recommended_ICD10": ""
    }
    empty_template = json.dumps({"results": [empty_record] * note_count})

    note_types = [classify_note_type(note) for note in notes_list]
    note_types_str = ', '.join(f'Note {i+1}: {t}' for i, t in enumerate(note_types))
    plural = 's' if note_count > 1 else ''

    return """DO NOT THINK. DO NOT EXPLAIN. OUTPUT JSON ONLY. START WITH {{ IMMEDIATELY.

NOTE TYPES: {note_types_str}

NOTES TO EXTRACT ({note_count} note{plural}):

{notes_text}

============================================================
EXHAUSTIVE ICD-10 CODING IS THE TOP PRIORITY
============================================================
For EVERY clinical note, walk through this checklist before writing Recommended_ICD10:

1. [ ] Did I code EVERY symptom in Chief_Complaint? (R-codes)
2. [ ] Did I code EVERY abnormal examination finding? (R/M codes)
3. [ ] Did I code EVERY abnormal lab value? (R79.89, D72.829, E87.x, etc.)
4. [ ] Did I code EVERY ECG abnormality? (I20.9, I21.9, I48.91, R00.x, etc.)
5. [ ] Did I code EVERY imaging finding + Z01.89 for imaging ordered?
6. [ ] Did I code EVERY chronic condition from Medical_Surgical_History? (I10, E11.9, J44.9, etc.) — MANDATORY even if stable
7. [ ] Did I code the working/acute diagnosis suggested by the findings?
8. [ ] Did I add external cause codes (W/V/Y) for any trauma/fall/injury?
9. [ ] Did I add injury site codes (S/T) for any trauma?
10. [ ] Did I add Z-codes for disposition (Z09 follow-up, Z51.89 aftercare, Z76.89 sick leave, Z53.21 procedure refused, Z03.89 observation)?
11. [ ] For each finding, did I include BOTH the parent code AND the more specific child code when applicable? (e.g., R10.13 epigastric pain + R10.9 unspecified abdominal pain)
12. [ ] For foreign body cases: did I distinguish T18.x (GI/swallowed) from T17.x (airway/aspirated)? When uncertain, emit BOTH.

MINIMUM YIELD:
- Typical clinical note → 6–12 codes
- Rich multi-system note → 8–15 codes
- Fragment → 1+ code per finding
- Medication order only → "not applicable"

DO NOT under-code. DO NOT stop at the primary diagnosis. Code EVERY finding.

============================================================

CRITICAL: Handle each note type appropriately:
- Clinical notes: Extract all fields normally. EMIT EXHAUSTIVE ICD-10 CODE SET per the checklist above.
- Medication orders: Chief_Complaint="", Assessment="", Vital_Signs_Initial="", Imaging_Results_Text="", Recommended_ICD10="not applicable"; put medication list in Plan_Text
- Unknown: Extract whatever clinical content is present and code everything you can identify

FILL THIS TEMPLATE — replace every "" with extracted values:
{empty_template}

RULES:
- Output ONLY the filled JSON. Nothing before {{. Nothing after }}.
- Recommended_ICD10: ALWAYS exhaustive. NEVER fewer than 6 codes for a typical clinical note unless content is genuinely sparse.
- Separate multiple codes with semicolon (;). No duplicates. No trailing punctuation.
- Empty string "" if a non-ICD field is not present in the note
- One JSON object per note — {note_count} note{plural} = {note_count} object{plural} in results array

SEMANTIC EXTRACTION REMINDERS:
- Patient_Identification: age/gender like "49 Y/O MALE", "MOHD VAVI MALE AGE 33"
- Chief_Complaint: symptoms after "C/O", "presented with", "Chief Complaint"
- Medical_Surgical_History: conditions AND surgeries — "PMH:", "PSH:", "HTN", "DM", "NPMH", "Appendectomy", "2 D&C"
- Allergies_Adverse_Reactions: "NKDA", "NO ALLERGIES", "NO ALLERGIC HISTORY"
- Drug_History: "Medications:", "Home meds:", "Current meds:"
- Vital_Signs_Initial: "BP: 160/100", "VITAL STABLE", "TEMP 37.2; BP 125/89"
- Assessment: exam findings, labs, ECG — "GCS 15/15", "S1+S2", "EBAE", "CBC: ...", "ECG: ..."
- Imaging_Results_Text: CT/X-ray/US/MRI/Echo results
- Plan_Text: "Plan:", "Treatment:", "FOR XRAY", "DISCHARGED ON"
- Disposition_Discharge: "DISCHARGED", "ADMITTED", "AMA", "OPD FOLLOW UP"
- Recommended_ICD10: EXHAUSTIVE list per the 10-point checklist above.""".format(
        note_types_str=note_types_str,
        note_count=note_count,
        notes_text=notes_text,
        empty_template=empty_template,
        plural=plural
    )
