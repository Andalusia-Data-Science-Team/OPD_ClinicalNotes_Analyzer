import sys
import argparse
import json
from src.config import ExtractionConfig
from src.extractor import ClinicalNotesExtractor
from src.database_ops import load_notes_from_sql, insert_to_sql_table, test_database_connection
from src.data_processor import (
    validate_structured_data,
    get_data_summary,
    calculate_icd10_accuracy,
)
from src.skill_router import discover_skills, route_notes


def run_extraction(config):
    """
    Run extraction for a single department with the given config.
    """
    print("\n" + "=" * 60)
    print(f"Running extraction for department: {config.department}")
    print("=" * 60)

    print("\nDiscovering available skills...")
    skills = discover_skills()
    print(f"   Found skills: {list(skills.keys())}")

    print("\nTesting database connection...")
    if not test_database_connection(config):
        print("\nERROR: Database connection failed. Exiting.")
        return 0

    print("\nLoading clinical notes...")
    original_df = load_notes_from_sql(
        config=config,
        notes_column=config.notes_column,
        sql_file=config.sql_file,
    )
    if original_df is None or original_df.empty:
        print("\nERROR: No notes loaded from SQL. Exiting.")
        return 0
    print(f"   Loaded {len(original_df)} notes")

    # Get the notes list
    notes = original_df[config.notes_column].tolist()
    diagnosis_context = None
    if 'ICD10_code' in original_df.columns or 'icd10_code' in original_df.columns:
        icd_col = 'ICD10_code' if 'ICD10_code' in original_df.columns else 'icd10_code'
        diagnosis_context = []
        for _, row in original_df.iterrows():
            diagnosis_context.append({
                'icd10_code': row.get(icd_col, ''),
                'diagnosis_name': row.get('ShortName', ''),
            })

    # ------------------------------------------------------------------ #
    # Skill loading                                                      #
    # ------------------------------------------------------------------ #
    print(f"\nLoading skill for department: {config.department}...")
    from src.skill_loader import load_skill_config
    skill_config = load_skill_config(config.department)
    if skill_config is None:
        print(f"\nERROR: Could not load skill for department '{config.department}'. Exiting.")
        return 0
    print(f"   Loaded skill: {config.department}")
    print(f"   Required fields: {len(skill_config['required_fields'])}")

    # ------------------------------------------------------------------ #
    # Extraction                                                         #
    # ------------------------------------------------------------------ #
    print("\nInitializing extractor...")
    extractor = ClinicalNotesExtractor(
        system_prompt=skill_config['system_prompt'],
        get_user_prompt=skill_config['get_user_prompt'],
        required_fields=skill_config['required_fields'],
        field_aliases=skill_config['field_aliases'],
        scoring_fn=skill_config['scoring_fn'],
        client=None,  # Will be initialized per batch
        model=config.openrouter_model,
        api_key=config.openrouter_api_key,
        temperature=config.temperature,
        max_retries=3,
    )

    print(f"\nExtracting features from {len(notes)} notes (batch_size={config.batch_size})...")
    structured_data = extractor.extract_batch(
        notes_list=notes,
        diagnosis_context=diagnosis_context,
        batch_size=config.batch_size,
    )
    if not structured_data:
        print("\nERROR: No structured data extracted. Exiting.")
        return 0
    print(f"   Extracted {len(structured_data)} records")

    # ------------------------------------------------------------------ #
    # Validation                                                         #
    # ------------------------------------------------------------------ #
    print("\nValidating extracted data...")
    validate_structured_data(structured_data, skill_config['required_fields'])
    summary = get_data_summary(structured_data, skill_config['required_fields'])
    print(f"   Total records: {summary['total_records']}")
    print(f"   Overall completion rate: {summary['completion_rate']:.2f}%")

    # ------------------------------------------------------------------ #
    # ICD-10 accuracy & Documentation Appropriateness                        #
    # ------------------------------------------------------------------ #
    print("\nCalculating ICD-10 accuracy...")
    icd_ai_field = "icd10_AI_Generated" if config.department == "OPD" else "Recommended_ICD10"
    for i, record in enumerate(structured_data):
        actual_icd10 = ''
        if i < len(original_df):
            for col in ('ICD10_code', 'icd10_code'):
                if col in original_df.columns:
                    val = original_df.iloc[i].get(col, '')
                    if val and not (isinstance(val, float) and val != val):
                        actual_icd10 = str(val)
                        break
        record['ICD10_Accuracy'] = calculate_icd10_accuracy(
            record.get(icd_ai_field, ''),
            actual_icd10,
        )
        # Calculate Documentation Appropriateness using skill's scoring_fn
        record['Documentation_Appropriateness'] = extractor.scoring_fn(record)
    print("   ICD-10 accuracy calculated")
    print("   Documentation Appropriateness calculated")

    # ------------------------------------------------------------------ #
    # Insert to SQL                                                        #
    # ------------------------------------------------------------------ #
    print("\nInserting results to SQL database...")
    try:
        rows_inserted = insert_to_sql_table(
            structured_data=structured_data,
            original_df=original_df,
            config=config,
        )
        print(f"   Successfully inserted {rows_inserted} rows to SQL.")
    except Exception as e:
        print(f"\nWARNING: Could not insert to SQL: {str(e)}")
        print(f"   Saving extracted data to JSON file for retry...")
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"extracted_data_{config.department}_{timestamp}.json"
        
        # Convert original_df to dict with string conversion for timestamps
        original_data = None
        if original_df is not None:
            original_data = original_df.astype(str).to_dict('records')
        
        save_data = {
            "structured_data": structured_data,
            "original_df": original_data
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        print(f"   Saved to: {filename}")
        print(f"   To retry insertion, use: python main.py --load-json {filename}")

    print("\n" + "=" * 60)
    print(f"Pipeline completed for {config.department}!")
    print("=" * 60)
    print(f"\nDepartment: {config.department}")
    print(f"Total records: {len(structured_data)}")
    print(f"Fields extracted: {len(structured_data[0]) if structured_data else 0}")
    print("\n")
    
    return len(structured_data)


def main():
    """
    Main extraction pipeline.
    DEPARTMENT in .env: pin to a specific skill (OPD/ER/etc.) — legacy behavior.
    DEPARTMENT=AUTO or unset: skill_router reads each SKILL.md description and
    picks the best-matching department from the loaded notes automatically.
    DEPARTMENT=ALL or --all: run extraction for all available departments (ER, OPD).
    """
    parser = argparse.ArgumentParser(description="Clinical Notes Extraction Pipeline")
    parser.add_argument("--load-json", help="Load extracted data from JSON file and retry SQL insertion")
    parser.add_argument("--all", action="store_true", help="Run extraction for all available departments")
    args = parser.parse_args()

    print("=" * 60)
    print("Clinical Notes Extraction Pipeline")
    print("=" * 60)

    # Load from JSON mode
    if args.load_json:
        print(f"\nLoading extracted data from: {args.load_json}")
        try:
            with open(args.load_json, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            structured_data = save_data["structured_data"]
            original_data = save_data.get("original_df")
            print(f"   Loaded {len(structured_data)} extracted records")
            if original_data:
                import pandas as pd
                original_df = pd.DataFrame(original_data)
                print(f"   Loaded {len(original_df)} original records")
            else:
                original_df = None
                print("   Warning: No original data in JSON file - some columns may be missing")
        except Exception as e:
            print(f"\nERROR loading JSON: {str(e)}")
            sys.exit(1)

        # Load config to get department and output table
        config = ExtractionConfig()
        config.validate()

        # Set department from filename if not set
        if config.department is None:
            import re
            match = re.search(r'extracted_data_(\w+)_', args.load_json)
            if match:
                config.department = match.group(1).upper()
                print(f"   Detected department from filename: {config.department}")

        config.resolve_output_table(config.department)
        print(f"   Output table: {config.output_schema}.{config.output_table}")

        # Retry insertion
        print("\nRetrying SQL insertion...")
        try:
            rows_inserted = insert_to_sql_table(
                structured_data=structured_data,
                original_df=original_df,
                config=config,
            )
            print(f"   Successfully inserted {rows_inserted} rows to SQL.")
        except Exception as e:
            print(f"\nERROR: Could not insert to SQL: {str(e)}")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("Insertion retry completed!")
        print("=" * 60)
        return

    # Run for all departments
    if args.all or (config.department and config.department.upper() == "ALL"):
        print("\nRunning extraction for ALL available departments...")
        skills = discover_skills()
        departments = list(skills.keys())
        print(f"   Found departments: {departments}")
        
        total_records = 0
        for dept in departments:
            # Create a new config for each department
            dept_config = ExtractionConfig()
            dept_config.department = dept
            dept_config.validate()
            dept_config.resolve_output_table(dept)
            
            records = run_extraction(dept_config)
            total_records += records
        
        print("\n" + "=" * 60)
        print("ALL DEPARTMENTS COMPLETED")
        print("=" * 60)
        print(f"Total records processed: {total_records}")
        print("\n")
        return

    print("\nLoading configuration...")
    config = ExtractionConfig()
    config.validate()

    print("\nDiscovering available skills...")
    skills = discover_skills()
    print(f"   Found skills: {list(skills.keys())}")

    print("\nTesting database connection...")
    if not test_database_connection(config):
        print("\nERROR: Database connection failed. Please check your .env configuration.")
        sys.exit(1)

    print("\nLoading clinical notes from SQL database...")
    try:
        notes, original_df = load_notes_from_sql(config)

        print(f"\n   DEBUG: Loaded {len(notes)} notes")
        for i, note in enumerate(notes[:2]):
            print(f"   DEBUG: Note {i+1} (first 200 chars): {note[:200]}...")

        diagnosis_context = None
        icd_col = None
        for cand in ('icd10_code', 'ICD10_code'):
            if cand in original_df.columns:
                icd_col = cand
                break
        if icd_col:
            diag_col = 'diagnosis_name' if 'diagnosis_name' in original_df.columns else None
            diagnosis_context = []
            for _, row in original_df.iterrows():
                ctx = {'icd10_code': str(row.get(icd_col, '') or '')}
                if diag_col:
                    ctx['diagnosis_name'] = str(row.get(diag_col, '') or '')
                diagnosis_context.append(ctx)
            print(f"   Loaded diagnosis context for {len(diagnosis_context)} notes")

    except Exception as e:
        print(f"\nERROR loading from database: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Skill routing — runs only when DEPARTMENT is not pinned in .env     #
    # ------------------------------------------------------------------ #
    if config.department is None:
        print(f"\nRouting notes to skill (strategy: {config.routing_strategy})...")

        # For LLM routing we reuse the same client the extractor will use
        llm_client = None
        try:
            import openai
            llm_client = openai.OpenAI(
                api_key=config.api_key,
                base_url="https://openrouter.ai/api/v1"
            )
        except Exception as e:
            print(f"   ERROR: Could not init LLM client for routing ({e}). LLM routing is required.")
            sys.exit(1)

        department = route_notes(
            notes,
            client=llm_client,
            model=config.model,
        )
        config.department = department.upper()
        print(f"   Routed to: {config.department}")
    else:
        print(f"\nDepartment pinned to: {config.department} (DEPARTMENT set in .env)")

    # Resolve output table now that we know the department
    config.resolve_output_table(config.department)
    print(f"   Output table: {config.output_schema}.{config.output_table}")

    # ------------------------------------------------------------------ #
    # Extractor init                                                       #
    # ------------------------------------------------------------------ #
    print(f"\nInitializing AI extractor for: {config.department}...")
    try:
        extractor = ClinicalNotesExtractor(
            department=config.department,
            api_key=config.api_key,
            model=config.model,
            temperature=config.temperature,
        )
        print(f"   Extractor initialized — {len(extractor.required_fields)} fields")
    except Exception as e:
        print(f"\nERROR initializing extractor: {str(e)}")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Extraction                                                           #
    # ------------------------------------------------------------------ #
    try:
        def progress_callback(curr, total, msg):
            print(f"   {msg}")

        structured_data = extractor.extract_batch(
            notes,
            diagnosis_context=diagnosis_context,
            batch_size=config.batch_size,
            progress_callback=progress_callback,
        )
        print(f"\nExtraction complete: {len(structured_data)} records")

        print(f"\n   DEBUG: First extracted record:")
        if structured_data:
            for key, val in structured_data[0].items():
                val_display = str(val)[:100] if val else "[EMPTY]"
                print(f"      {key}: {val_display}")

    except Exception as e:
        print(f"\nERROR during extraction: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # ICD-10 accuracy & Documentation Appropriateness                        #
    # ------------------------------------------------------------------ #
    print("\nCalculating ICD-10 accuracy...")
    icd_ai_field = "icd10_AI_Generated" if config.department == "OPD" else "Recommended_ICD10"
    for i, record in enumerate(structured_data):
        actual_icd10 = ''
        if i < len(original_df):
            for col in ('ICD10_code', 'icd10_code'):
                if col in original_df.columns:
                    val = original_df.iloc[i].get(col, '')
                    if val and not (isinstance(val, float) and val != val):
                        actual_icd10 = str(val)
                        break
        record['ICD10_Accuracy'] = calculate_icd10_accuracy(
            record.get(icd_ai_field, ''),
            actual_icd10,
        )
        # Calculate Documentation Appropriateness using skill's scoring_fn
        record['Documentation_Appropriateness'] = extractor.scoring_fn(record)
    print("   ICD-10 accuracy calculated")
    print("   Documentation Appropriateness calculated")

    # ------------------------------------------------------------------ #
    # Validation + summary                                                 #
    # ------------------------------------------------------------------ #
    print("\nValidating extracted data...")
    if validate_structured_data(structured_data, extractor.required_fields, verbose=True):
        print("   All records validated successfully")
    else:
        print("   Warning: Some records may have issues")

    print("\nExtraction Summary:")
    summary = get_data_summary(structured_data, extractor.required_fields)
    print(f"   Total records: {summary['total_records']}")
    print(f"   Overall completion rate: {summary['completion_rate']:.1f}%")
    print(f"\n   Top populated fields:")

    sorted_fields = sorted(
        summary['fields_populated'].items(),
        key=lambda x: x[1]['percentage'],
        reverse=True,
    )[:5]
    for field, stats in sorted_fields:
        print(f"      - {field}: {stats['count']} ({stats['percentage']:.1f}%)")

    key_fields = [icd_ai_field] + (["Final_Diagnosis"] if config.department == "OPD" else [])
    for field in key_fields:
        stats = summary['fields_populated'].get(field, {})
        print(f"      - {field}: {stats.get('count', 0)} ({stats.get('percentage', 0):.1f}%)")

    # ------------------------------------------------------------------ #
    # Insert to SQL                                                        #
    # ------------------------------------------------------------------ #
    print("\nInserting results to SQL database...")
    try:
        rows_inserted = insert_to_sql_table(
            structured_data=structured_data,
            original_df=original_df,
            config=config,
        )
        print(f"   Successfully inserted {rows_inserted} rows to SQL.")
    except Exception as e:
        print(f"\nWARNING: Could not insert to SQL: {str(e)}")
        print(f"   Saving extracted data to JSON file for retry...")
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"extracted_data_{config.department}_{timestamp}.json"
        
        # Convert original_df to dict with string conversion for timestamps
        original_data = None
        if original_df is not None:
            original_data = original_df.astype(str).to_dict('records')
        
        save_data = {
            "structured_data": structured_data,
            "original_df": original_data
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        print(f"   Saved to: {filename}")
        print(f"   To retry insertion, use: python main.py --load-json {filename}")

    print("\n" + "=" * 60)
    print("Pipeline completed successfully!")
    print("=" * 60)
    print(f"\nDepartment: {config.department}")
    print(f"Total records: {len(structured_data)}")
    print(f"Fields extracted: {len(structured_data[0]) if structured_data else 0}")
    print("\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
