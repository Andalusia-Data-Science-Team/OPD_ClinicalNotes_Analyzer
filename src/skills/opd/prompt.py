"""
OPD skill: get_user_prompt() only. SYSTEM_PROMPT now lives in
src/skills/opd/SYSTEM_PROMPT.md and is loaded by skill_loader.py.
"""


def get_user_prompt(notes_list, diagnosis_context=None):
    """
    Generate user prompt with OPD clinical notes and optional diagnosis context.
    """
    if not notes_list:
        return "No clinical notes provided."

    formatted_notes = []
    for i, note in enumerate(notes_list):
        if not note.strip():
            continue

        note_parts = [part.strip() for part in note.split('||') if part.strip()]
        note_text = "**Note {}:**".format(i + 1)

        for j, part in enumerate(note_parts, 1):
            note_text += "\n\n**Part {}:**\n{}".format(j, part)

        if diagnosis_context and i < len(diagnosis_context):
            context = diagnosis_context[i]
            diagnosis_name = context.get('diagnosis_name', '')
            icd10_code = context.get('icd10_code', '')

            if icd10_code:
                note_text += "\n\n**BILLING INFORMATION (for reference):**"
                note_text += "\n- Billing ICD-10: {}".format(icd10_code)
                if diagnosis_name:
                    note_text += "\n- Billing Diagnosis Name: {}".format(diagnosis_name)

        formatted_notes.append(note_text)

    notes_text = "\n\n".join(formatted_notes)

    tail = (
        "\n\n**EXTRACTION REQUIREMENTS:**\n"
        "- Extract all available information into the 10 defined fields\n"
        "- Notes may contain multiple parts separated by '||' - treat them as parts of the same patient visit\n"
        "- Short, abbreviated, or procedural notes must still be processed — extract what is present\n"
        "- Return a JSON object with a \"results\" array containing one object per patient visit\n"
        "- Maintain the order of notes as numbered above\n"
        "- Use semicolons (;) to separate multiple items within the same field\n"
        "- Return ONLY the JSON output — no explanations, no markdown formatting, no code blocks\n"
        "\n**Required Fields (exact names, case-sensitive):**\n"
        "Chief_Complain, History, Comorbidities, Clinical_Examination, Diagnosis, Treatment_Plan, icd10_AI_Generated, Final_Diagnosis, Arabic_Treatment_Plan, Surgery_Visit_Type\n"
        "\n**CRITICAL - Treatment_Plan Extraction Rules (English Text Only):**\n"
        "- 'FOR RT URS' → Treatment_Plan = 'RT URS'; Arabic_Treatment_Plan = 'تنظير الحالب الأيمن'\n"
        "- 'FOR CATHETER REMOVAL' → Treatment_Plan = 'Catheter removal'; Arabic_Treatment_Plan = 'إزالة القسطرة'\n"
        "- 'for followup' or 'for follow-up' → Treatment_Plan = 'Follow up'; Arabic_Treatment_Plan = 'متابعة'\n"
        "- 'PREPARING FOR OPERATION' → Treatment_Plan = 'Preparing for operation'; Arabic_Treatment_Plan = 'التحضير للعملية الجراحية'\n"
        "- 'next rxt' → Treatment_Plan = 'Next RXT'; Arabic_Treatment_Plan = 'العلاج الإشعاعي التالي'\n"
        "- 'for investigation' → Treatment_Plan = 'For investigation'; Arabic_Treatment_Plan = 'للتحقيق'\n"
        "- 'exo ul 5 and put implant' → Treatment_Plan = 'Completed: exo ul 5; Next: put implant'; Arabic_Treatment_Plan = 'المنجز: خلع الضرس 5 العلوي الأيسر; التالي: وضع زرع فوري'\n"
        "- Do NOT add 'Follow-up after surgery' or any other default value\n"
        "- Do NOT recommend any treatment not explicitly in the note\n"
        "- If no treatment plan is documented, use \"\"\n"
        "- NEVER include Arabic text in Treatment_Plan — store Arabic ONLY in Arabic_Treatment_Plan\n"
        "\n**UPDATED - Aggressive Treatment_Plan Detection:**\n"
        "- Look for: 'PREPARING FOR', 'FOR [procedure]', 'next [treatment]', 'for investigation', 'for followup', 'rxt', 'Plan:', 'Rx:'\n"
        "- Extract implicitly documented plans, not just explicitly labeled ones\n"
        "- Even if concatenated without spaces (e.g., 'SWELLINGPREPARING FOR OPERATION'), still extract 'Preparing for operation'\n"
        "\n**Arabic_Treatment_Plan is a SEPARATE field (English/Arabic Separation):**\n"
        "- Treatment_Plan = English ONLY\n"
        "- Arabic_Treatment_Plan = Arabic ONLY (translated from Treatment_Plan)\n"
        "- Translate using patient-friendly everyday Arabic (not technical jargon)\n"
        "- Examples: 'Blood tests' → 'تحاليل دم', 'Ultrasound' → 'سونار', 'X-ray' → 'أشعة', 'Physical therapy' → 'علاج طبيعي'\n"
        "\n**Surgery_Visit_Type Classification Rules:**\n"
        "- 'FOR [surgery]' → 'Primary visit for planned surgery'\n"
        "- 'post', 'after' + past surgery → 'Follow up after surgery'\n"
        "- 'for followup' (medical, not surgical) → 'Not applicable'\n"
        "- Dental extraction + immediate implant → 'Not applicable'\n"
        "\n**CRITICAL - Final_Diagnosis Handling (NEVER LEAVE EMPTY):**\n"
        "- If the note has an explicit diagnosis (e.g., 'Diagnosis:', 'Dx:', 'Impression:'), use that as Final_Diagnosis\n"
        "- If NO explicit diagnosis but BILLING ICD-10 is provided, generate a simple human-readable Final_Diagnosis from the ICD-10 description\n"
        "- If NO explicit diagnosis AND NO ICD-10, generate Final_Diagnosis from the chief complaint, treatment plan, or history\n"
        "- Examples: 'chest pain' → 'Chest pain evaluation', 'FOR RT URS' → 'Pre-operative evaluation for ureteroscopy'\n"
        "- NEVER leave Final_Diagnosis empty if there is ANY diagnosable condition in the note\n"
        "\n**CRITICAL - icd10_AI_Generated (ALWAYS POPULATE & BE COMPREHENSIVE):**\n"
        "- ALWAYS include the billing ICD-10 code if provided\n"
        "- Generate codes for ALL documented conditions (diagnoses, comorbidities, symptoms, post-op status)\n"
        "- Use the most specific codes possible (e.g., E11.65 not just E11)\n"
        "- Include Z-codes where appropriate (Z48.89 for post-op, Z01.818 for pre-op)\n"
        "- NEVER leave icd10_AI_Generated empty if there is ANY diagnosable condition\n"
        "- Be COMPREHENSIVE - generate codes for ALL conditions, not just 1-3 codes\n"
        "\n**Common extraction mistakes to avoid:**\n"
        "- Do NOT put imaging or lab results into Clinical_Examination\n"
        "- Do NOT put visit dates into History\n"
        "- Do NOT return all-empty fields for a note that has clinical content\n"
        "- Do NOT use field names Chief_Complaint\n"
        "- When multiple note parts exist, extract the most comprehensive information from all parts\n"
        "- For surgery follow-up visits: include 'Status post' in Diagnosis, place surgery in History under PSH\n"
        "- For surgery follow-up visits: Treatment_Plan should be \"\" unless explicit post-op instructions are documented\n"
        "- **CRITICAL - Completed vs. Next actions:** When a note describes BOTH a completed action AND an immediate next action in the same visit, separate them as 'Completed: [action] (المنجز: [action]); Next: [action] (التالي: [action])'\n"
        "- **CRITICAL - Preserve exact text:** Do NOT correct typos, grammar, or abbreviations\n"
        "- **CRITICAL - 'FOR' pattern:** Extract as Treatment_Plan, not Chief_Complain\n"
        "- **CRITICAL - Final_Diagnosis:** NEVER leave Final_Diagnosis empty if ANY condition exists — generate from available context\n"
        "- **CRITICAL - icd10_AI_Generated:** ALWAYS populate with ALL appropriate codes — be comprehensive, not limited to 2-3 codes\n"
        "\n**Quality Checks Before Returning:**\n"
        "- ✓ Valid JSON syntax, no trailing commas\n"
        "- ✓ All 10 fields present in every object\n"
        "- ✓ Empty strings (\"\") for missing data — not null, not omitted\n"
        "- ✓ Imaging/lab results are NOT placed in Clinical_Examination\n"
        "- ✓ Visit dates are NOT placed in History\n"
        "- ✓ No object is all-empty if the note contains any clinical content\n"
        "- ✓ One object per input note, in the same order as input\n"
        "- ✓ icd10_AI_Generated ALWAYS populated with at least one code when ANY diagnosable condition exists\n"
        "- ✓ icd10_AI_Generated includes ALL appropriate codes (comprehensive, not just 1-3)\n"
        "- ✓ Arabic_Treatment_Plan: empty string if Treatment_Plan is empty; translated text if Treatment_Plan is populated\n"
        "- ✓ Surgery_Visit_Type correctly classified for surgical cases\n"
        "- ✓ For post-op follow-up visits: Diagnosis includes 'Status post', History includes the surgery under PSH, Treatment_Plan is \"\" unless explicitly documented\n"
        "- ✓ For notes with completed action + immediate next action: Treatment_Plan uses format 'Completed: X; Next: Y'\n"
        "- ✓ For 'FOR [procedure]' notes: Treatment_Plan populated with patient-friendly Arabic translation, Surgery_Visit_Type = 'Primary visit for planned surgery'\n"
        "- ✓ For 'for followup' notes: Treatment_Plan = 'Follow up'\n"
        "- ✓ Treatment_Plan contains NO default, inferred, or recommended values - only explicit text from the note\n"
        "- ✓ Patient-friendly Arabic is used in Treatment_Plan translations — no overly technical terms\n"
        "- ✓ Final_Diagnosis ALWAYS populated when ANY condition exists — never empty for a clinical note with diagnosable content\n"
        "- ✓ Final_Diagnosis generated from ICD-10 code, chief complaint, or treatment plan if no explicit diagnosis exists\n"
        "- ✓ icd10_AI_Generated uses most specific codes possible and includes all documented conditions\n"
        '\n**Expected Output Format:**\n'
        '{"results": [{"Chief_Complain": "", "History": "", "Comorbidities": "", "Clinical_Examination": "", "Diagnosis": "", "Treatment_Plan": "", "icd10_AI_Generated": "", "Final_Diagnosis": "", "Arabic_Treatment_Plan": "", "Surgery_Visit_Type": ""}]}\n'
    )

    return notes_text + tail
