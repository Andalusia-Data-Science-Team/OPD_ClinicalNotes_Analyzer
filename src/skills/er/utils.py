"""
ER skill utility: classify_note_type, used by the ER prompt builder.
"""


def classify_note_type(note: str) -> str:
    """
    Returns one of: 'medication_order', 'clinical_note', 'fragment', 'empty'
    """
    if not note or not str(note).strip():
        return "empty"
    text = str(note).lower().strip()
    if len(text) < 30:
        return "fragment"

    med_tokens = sum(t in text for t in [
        " mg ", " ml ", "tablet", "capsule", "syrup",
        "bid", "tid", "qid", "prn", "po", "iv", "im",
        "twice daily", "once daily", "every "
    ])
    clinical_tokens = sum(t in text for t in [
        "chief complaint", "c/o", "presented", "history of",
        "examination", "assessment", "diagnosis", "vital",
        "bp", "hr", "temp", "gcs", "pain", "patient",
    ])
    if med_tokens >= 3 and clinical_tokens < 3:
        return "medication_order"
    return "clinical_note"
