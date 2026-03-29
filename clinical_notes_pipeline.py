import sys
import os
from src.config import ExtractionConfig
from src.extractor import ClinicalNotesExtractor
from src.database_ops import load_notes_from_sql, insert_to_sql_table, test_database_connection
from src.data_processor import (
    validate_structured_data,
    get_data_summary,
    opd_scoring
)


def main():
    """Main extraction pipeline"""
    
    print("="*60)
    print("Clinical Notes Extraction Pipeline")
    print("="*60)
    
    # 1. Load and validate configuration
    print("\nLoading configuration...")
    config = ExtractionConfig()
    config.validate()
    
    # 2. Test database connection
    print("\nTesting database connection...")
    if not test_database_connection(config):
        print("\nERROR: Database connection failed. Please check your .env configuration:")
        sys.exit(1)
    
    # 3. Load notes from SQL database
    print("\nLoading clinical notes from SQL database...")
    try:
        notes, original_df = load_notes_from_sql(config)
        
    except Exception as e:
        print(f"\nERROR loading from database: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 4. Initialize extractor
    print("\nInitializing AI extractor...")
    try:
        extractor = ClinicalNotesExtractor(
            api_key=config.api_key,
            model=config.model,
            temperature=config.temperature
        )
        print("   Extractor initialized")
    except Exception as e:
        print(f"\nERROR initializing extractor: {str(e)}")
        sys.exit(1)
    
    # 5. Extract features
    try:
        structured_data = extractor.extract_batch(
            notes, 
            batch_size=config.batch_size,
            progress_callback=lambda curr, total, msg: print(f"   {msg}")
        )
        print(f"\n   Extraction complete: {len(structured_data)} records")
    except Exception as e:
        print(f"\nERROR during extraction: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 6. Calculate additional metrics
    print("\nCalculating documentation scores...")
    for record in structured_data:
        record['Documentation_Appropriateness'] = opd_scoring(record)
    print("   Documentation scores calculated")

    # 7. Validate results
    print("\nValidating extracted data...")
    if validate_structured_data(structured_data, verbose=True):
        print("   All records validated successfully")
    else:
        print("   Warning: Some records may have issues")
    
    # 8. Show summary statistics
    print("\nExtraction Summary:")
    summary = get_data_summary(structured_data)
    print(f"   Total records: {summary['total_records']}")
    print(f"   Overall completion rate: {summary['completion_rate']:.1f}%")
    print(f"\n   Top populated fields:")
    
    # Sort fields by completion percentage
    sorted_fields = sorted(
        summary['fields_populated'].items(),
        key=lambda x: x[1]['percentage'],
        reverse=True
    )[:5]
    
    for field, stats in sorted_fields:
        print(f"      - {field}: {stats['count']} ({stats['percentage']:.1f}%)")
    
    # 9. Insert to SQL Database
    print("\nInserting results to SQL database...")
    try:
        rows_inserted = insert_to_sql_table(
            structured_data=structured_data,
            original_df=original_df,
            config=config
        )   
        print(f"   Successfully inserted {rows_inserted} rows to SQL.")
        
    except Exception as e:
        print(f"\nWARNING: Could not insert to SQL: {str(e)}")         

    # 10. Success
    print("\n" + "="*60)
    print("Pipeline completed successfully!")
    print("="*60)
    print(f"\nTotal records: {len(structured_data)}")
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
