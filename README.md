# Clinical Extractor V2

A production-grade AI-powered clinical notes extraction system with automatic department routing, SQL Server integration, and Apache Airflow orchestration. Uses LLM APIs to extract structured medical information from clinical notes for Emergency Department (ER) and Outpatient Department (OPD) settings with comprehensive ICD-10 coding, documentation quality scoring, and cost tracking.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Skill System](#skill-system)
- [Pipeline Flow](#pipeline-flow)
- [Airflow Integration](#airflow-integration)
- [Data Quality & Validation](#data-quality--validation)
- [ICD-10 Coding](#icd-10-coding)
- [Troubleshooting](#troubleshooting)
- [Dependencies](#dependencies)
- [File Structure](#file-structure)

## Overview

Clinical Extractor V2 is a sophisticated NLP pipeline designed for healthcare environments that processes unstructured clinical notes and extracts structured medical data. The system features:

- **Intelligent Department Routing**: Automatically classifies notes as ER or OPD using LLM-based content analysis
- **Modular Skill Architecture**: Easy-to-extend system for adding new clinical departments
- **Robust Data Processing**: Multi-strategy JSON parsing, HTML cleaning, deduplication, and validation
- **Comprehensive ICD-10 Coding**: Exhaustive coding protocols with accuracy tracking against billing codes
- **Documentation Quality Scoring**: Department-specific scoring algorithms for clinical documentation appropriateness
- **SQL Server Integration**: Direct database operations with column length validation and data sanitization
- **Production Orchestration**: Apache Airflow DAG for automated daily processing with cost tracking
- **Fault Tolerance**: Exponential backoff retry logic, fallback structures, and JSON save-on-failure

## Key Features

### Core Capabilities

- **Automatic Department Routing**: LLM-based classification routes notes to ER or OPD skills based on clinical content patterns
- **Modular Skill System**: Add new departments by creating skill folders with SKILL.md, fields.py, and prompt.py
- **Robust JSON Parsing**: 5 fallback strategies for handling varied LLM responses (markdown stripping, array extraction, object extraction, line-by-line search)
- **Data Quality Pipeline**: HTML/CSS/JavaScript removal, duplicate note part elimination, ICD-10 code normalization, and empty note filtering
- **SQL Server Integration**: Direct database read/write with automatic column length validation, case-insensitive matching, and datetime range conversion
- **Retry Logic**: Exponential backoff (2^n seconds) for failed API calls with configurable max_retries
- **Batch Processing**: Configurable batch sizes for efficient processing and rate limiting
- **Token Usage Tracking**: Cumulative input/output token counting for cost estimation
- **Cost Sheet Generation**: Automatic CSV logging of AI API costs per run (date, tokens, records, USD cost)

### Advanced Features

- **ICD-10 Accuracy Calculation**: Base/chapter level matching between AI-generated codes and billing codes
- **Documentation Appropriateness Scoring**: Weighted field completeness scores (ER: Assessment 25%, OPD: Treatment_Plan 50%)
- **Billing Context Integration**: Incorporates existing ICD-10 codes and diagnosis names as reference for extraction
- **Multi-Department Processing**: Run extraction for all departments simultaneously with `--all` flag
- **JSON Retry Mode**: Save failed SQL insertions to JSON and retry with `--load-json` flag
- **Airflow Orchestration**: 6-task DAG (3 per department) with parallel ER/OPD processing
- **State Persistence**: Intermediate pickle files for Airflow task state passing
- **Trusted Connection Support**: Windows Authentication for SQL Server in addition to username/password

## Architecture

The system follows a modular, department-agnostic architecture where core logic is separated from department-specific extraction rules:

```
┌─────────────────────────────────────────────────────────────┐
│                     main.py (Entry Point)                    │
│  - Configuration loading                                      │
│  - Skill discovery & routing                                 │
│  - Pipeline orchestration                                    │
└──────────────────┬──────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────┐    ┌──────▼──────────┐
│  Auto Routing  │    │  Manual Pin     │
│  (skill_router)│    │  (DEPARTMENT=ER)│
└───────┬────────┘    └──────┬──────────┘
        │                    │
        └──────────┬─────────┘
                   │
        ┌──────────▼──────────┐
        │  skill_loader.py    │
        │  - Load SKILL.md    │
        │  - Load fields.py   │
        │  - Load prompt.py   │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │  extractor.py       │
        │  - LLM API calls    │
        │  - JSON parsing     │
        │  - Token tracking   │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │  database_ops.py   │
        │  - SQL load/insert  │
        │  - Data cleaning   │
        │  - Column mapping  │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │  data_processor.py │
        │  - Validation      │
        │  - ICD-10 accuracy │
        │  - Summary stats   │
        └───────────────────┘
```

## Installation

### Prerequisites

- Python 3.8 or higher
- SQL Server with ODBC Driver 17 for SQL Server
- OpenRouter API key (for DeepSeek or other models) or Fireworks AI API key
- Apache Airflow (optional, for automated scheduling)

### Setup Steps

1. **Clone the repository**:
```bash
cd "d:/Clinical notes/Clinical Extractor/Clinical Extractor/latest version/project"
```

2. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**:
```bash
cp .env.example .env  # If available, otherwise create .env manually
```

4. **Edit `.env` file** with your configuration (see [Configuration](#configuration))

5. **Test database connection**:
```bash
python -c "from src.config import ExtractionConfig; from src.database_ops import test_database_connection; cfg = ExtractionConfig(); cfg.validate(); print('Connection OK' if test_database_connection(cfg) else 'Connection FAILED')"
```

## Configuration

### Environment Variables

Create or edit the `.env` file in the project root:

```bash
# ============================================================
# DEPARTMENT SELECTION
# ============================================================
# Options: AUTO (LLM routing), ER, OPD, ALL (run all departments)
# AUTO: System analyzes note content and routes to best-matching skill
# ER/OPD: Pin to specific department (legacy behavior)
# ALL: Run extraction for all available departments sequentially
DEPARTMENT=AUTO

# Routing strategy when DEPARTMENT=AUTO
# Options: llm (uses skill descriptions for classification)
ROUTING_STRATEGY=llm

# ============================================================
# AI PROVIDER CONFIGURATION
# ============================================================
# OpenRouter API key (supports DeepSeek, OpenAI, and other models)
OPENROUTER_API_KEY="your-openrouter-api-key-here"

# Model selection (OpenRouter model identifier)
# Examples: deepseek/deepseek-chat, anthropic/claude-3-haiku, openai/gpt-4
OPENROUTER_MODEL="deepseek/deepseek-chat"

# Temperature for LLM generation (0.0 = deterministic, 1.0 = creative)
TEMPERATURE=0.0

# Batch size for processing notes (higher = faster but more memory)
# Recommended: 3-5 for DeepSeek, 1-2 for larger models
BATCH_SIZE=3

# Maximum retries for failed API calls (exponential backoff)
MAX_RETRIES=3

# ============================================================
# DATABASE CONFIGURATION
# ============================================================
# SQL Server connection details
DB_SERVER="your-server-name"
DB_DATABASE="your-database-name"
DB_DRIVER="ODBC Driver 17 for SQL Server"

# Authentication (choose one)
# Option 1: Username/Password
DB_USERNAME="your-username"
DB_PASSWORD="your-password"
DB_TRUSTED_CONNECTION=no

# Option 2: Windows Authentication (Trusted Connection)
# DB_USERNAME=""  # Leave empty
# DB_PASSWORD=""  # Leave empty
# DB_TRUSTED_CONNECTION=yes

# ============================================================
# QUERY CONFIGURATION
# ============================================================
# Column name containing clinical notes in source table
NOTES_COLUMN=Note

# SQL query file (relative to src/ directory)
# Options: er_query.sql, OPD_query.sql
SQL_FILE=er_query.sql

# Maximum rows to process (optional, for testing)
# Leave empty or comment out to process all rows
# MAX_ROWS=100

# ============================================================
# OUTPUT CONFIGURATION
# ============================================================
# Destination table and schema
OUTPUT_SCHEMA=dbo
OUTPUT_TABLE=Clinical_Notes_Features_New

# ============================================================
# AIRFLOW CONFIGURATION (Optional)
# ============================================================
# State directory for intermediate pickle files
CLINICAL_EXTRACTOR_STATE_DIR=/tmp/clinical_extractor

# Cost sheet CSV path for tracking AI API costs
CLINICAL_EXTRACTOR_COST_SHEET=./data/cost_sheet.csv

# DeepSeek cost model (USD per 1M tokens)
# Update if OpenRouter pricing changes
DEEPSEEK_INPUT_COST_PER_M=0.25
DEEPSEEK_OUTPUT_COST_PER_M=0.95
```

### Department-Specific Configuration Files

The project includes pre-configured `.env` files for different departments:

- **`.env`**: Default configuration (can be customized)
- **`.env.er`**: ER-specific configuration
- **`.env.opd`**: OPD-specific configuration

To use a department-specific config:

```bash
# Load ER configuration
python main.py --env .env.er

# Load OPD configuration
python main.py --env .env.opd
```

## Usage

### Basic Extraction

Run the extraction pipeline with default configuration:

```bash
python main.py
```

### Department-Specific Extraction

Pin to a specific department:

```bash
# ER only
DEPARTMENT=ER python main.py

# OPD only
DEPARTMENT=OPD python main.py
```

### Automatic Department Routing

Let the system automatically route notes based on content:

```bash
DEPARTMENT=AUTO python main.py
```

### Process All Departments

Run extraction for all available departments:

```bash
python main.py --all
```

### Retry Failed SQL Insertions

If SQL insertion fails, data is saved to JSON. Retry with:

```bash
python main.py --load-json extracted_data_ER_20240115_143022.json
```

### Airflow Orchestration

For automated daily processing:

1. **Set up Airflow**:
```bash
# Initialize Airflow database (if not already done)
airflow db init

# Create admin user
airflow users create --username admin --password admin --role Admin --email admin@example.com
```

2. **Configure DAG location**:
```bash
# Either symlink the dags folder to AIRFLOW_HOME/dags
ln -s "d:/Clinical notes/Clinical Extractor/Clinical Extractor/latest version/project/dags" $AIRFLOW_HOME/dags

# Or set AIRFLOW_HOME to the project root
export AIRFLOW_HOME="d:/Clinical notes/Clinical Extractor/Clinical Extractor/latest version/project"
```

3. **Start Airflow scheduler and webserver**:
```bash
airflow scheduler
airflow webserver
```

4. **Trigger the DAG manually** via Airflow UI or wait for scheduled run (10:30 AM Cairo time daily)

### Command-Line Arguments

```bash
python main.py [OPTIONS]

Options:
  --load-json FILE    Load extracted data from JSON file and retry SQL insertion
  --all               Run extraction for all available departments
  --env FILE          Use specific .env file instead of default
```

## Skill System

The skill system is the core abstraction that makes the pipeline department-agnostic. Each skill defines:

1. **System Prompt** (SKILL.md): Instructions to the LLM about its role and extraction rules
2. **Field Schema** (fields.py): Required fields, field aliases, and scoring function
3. **User Prompt Generator** (prompt.py): Function to format clinical notes for the LLM

### ER Skill (`src/skills/er/`)

**Purpose**: Emergency Department clinical notes with acute presentations, trauma, triage, and exhaustive ICD-10 coding requirements.

**Required Fields** (13):
- Patient_Identification
- Arrival_Triage
- Chief_Complaint
- Medical_Surgical_History
- Allergies_Adverse_Reactions
- Drug_History
- Vital_Signs_Initial
- Assessment
- Imaging_Results_Text
- Plan_Text
- Disposition_Discharge
- Recommended_ICD10

**Documentation Appropriateness Score**:
- Assessment: 25%
- Plan_Text: 15%
- Chief_Complaint: 15%
- Vital_Signs_Initial: 10%
- Medical_Surgical_History: 10%
- Patient_Identification: 5%
- Allergies_Adverse_Reactions: 5%
- Drug_History: 5%
- Imaging_Results_Text: 5%
- Disposition_Discharge: 5%

**Key Features**:
- Exhaustive ICD-10 coding protocol (6-12 codes minimum per note)
- Mandatory checklist for symptom, exam, lab, ECG, imaging, chronic condition, external cause, and Z-codes
- Support for ALL-CAPS free-text notes and fragmented narratives
- Special handling for medication orders vs. clinical notes

### OPD Skill (`src/skills/opd/`)

**Purpose**: Outpatient Department visit notes including routine clinic visits, follow-ups, chronic disease management, and minor procedures.

**Required Fields** (10):
- Chief_Complain
- History
- Comorbidities
- Clinical_Examination
- Diagnosis
- Treatment_Plan
- icd10_AI_Generated
- Final_Diagnosis
- Arabic_Treatment_Plan
- Surgery_Visit_Type

**Documentation Appropriateness Score**:
- Treatment_Plan: 50%
- Chief_Complain: 20%
- Diagnosis: 10%
- Clinical_Examination: 10%
- Comorbidities: 5%
- History: 5%

**Key Features**:
- Arabic translation support for treatment plans (patient-friendly language)
- Surgery visit type classification (pre-op vs. post-op follow-up)
- Comprehensive ICD-10 coding for all documented conditions
- Pattern recognition for implicit treatment plans ("FOR [procedure]", "for followup")
- Post-operative visit handling with "Status post" diagnosis formatting

### Adding New Skills

To add support for a new clinical department (e.g., ICU, Pediatrics):

1. **Create skill directory**:
```bash
mkdir src/skills/icu
```

2. **Create SKILL.md** with YAML frontmatter:
```yaml
---
name: icu
description: >
  Use for Intensive Care Unit clinical notes — critical care, ventilator
  management, hemodynamic monitoring, and multi-organ support. Notes
  typically contain detailed vital sign trends, lab series, medication
  infusions, and daily progress notes.
---
You are an expert clinical NLP system specialized in extracting structured
medical information from ICU clinical documentation...

[Detailed system prompt with field definitions and extraction guidelines]
```

3. **Create fields.py**:
```python
REQUIRED_FIELDS = [
    "Patient_Identification",
    "Admission_Diagnosis",
    "Vital_Signs_Trends",
    "Ventilator_Settings",
    "Medication_Infusions",
    "Lab_Series",
    "Daily_Progress",
    "ICD10_Codes",
]

FIELD_ALIASES = {
    "Chief_Complaint": "Admission_Diagnosis",
    "Vitals": "Vital_Signs_Trends",
    "Meds": "Medication_Infusions",
}

def scoring_fn(record: dict, actual_icd10: str = None) -> float:
    """ICU documentation appropriateness score."""
    weights = {
        "Daily_Progress": 30,
        "Vital_Signs_Trends": 25,
        "Medication_Infusions": 20,
        "Lab_Series": 15,
        "Admission_Diagnosis": 10,
    }
    score = 0.0
    for field, weight in weights.items():
        if record.get(field) and str(record[field]).strip():
            score += weight
    return round(score, 2)
```

4. **Create prompt.py**:
```python
def get_user_prompt(notes_list, diagnosis_context=None):
    """Generate user prompt for ICU notes."""
    # Format notes with ICU-specific context
    # Add billing reference information if available
    # Return formatted prompt string
    pass
```

5. **System automatically discovers** the new skill and routes to it when DEPARTMENT=AUTO

## Pipeline Flow

### Detailed Step-by-Step Process

#### Step 1: Configuration Loading
**File**: `main.py` → `main()`
**Function**: `ExtractionConfig()` in `src/config.py`

- Loads environment variables from `.env` file
- Validates required settings (API key, database credentials)
- Prints configuration summary including department, model, batch size
- Resolves output table based on department (if not explicitly set)

#### Step 2: Skill Discovery
**File**: `src/skill_router.py`
**Function**: `discover_skills()`

- Scans `src/skills/` directory for folders containing `SKILL.md` files
- Parses YAML frontmatter (name, description) from each skill file
- Returns dictionary of available skills: `{skill_name: {"description": str, "dir": Path}}`
- Used for automatic routing and skill availability validation

#### Step 3: Database Connection Test
**File**: `src/database_ops.py`
**Function**: `test_database_connection(config)`

- Constructs ODBC connection string from config
- Tests SQL Server connection using SQLAlchemy
- Executes simple test query: `SELECT 1 as test`
- Returns True if successful, False otherwise (exits pipeline on failure)

#### Step 4: Load Clinical Notes
**File**: `src/database_ops.py`
**Function**: `load_notes_from_sql(config)`

- Reads SQL query from `src/er_query.sql` or `src/OPD_query.sql`
- Executes query on SQL Server using pyodbc
- **Data Cleaning Pipeline**:
  1. **ID Column Preservation**: Forces ID columns (episode_key, visit_id, patient_code) to string to prevent truncation
  2. **Note Part Deduplication**: `_deduplicate_note_parts()` removes duplicate parts separated by `||`
  3. **HTML Content Detection**: `_is_html_content()` identifies and filters HTML-like content
  4. **HTML Tag Stripping**: `strip_html_tags()` removes HTML/CSS/JavaScript from notes
  5. **ICD-10 Code Normalization**: `_clean_icd10_code()` extracts and formats ICD-10 codes
  6. **Empty Note Filtering**: Removes rows with empty/null notes
  7. **Row Limiting**: Applies MAX_ROWS limit if configured
- Returns notes list and original DataFrame with diagnosis context

#### Step 5: LLM Routing (if DEPARTMENT=AUTO)
**File**: `src/skill_router.py`
**Functions**: `route_notes()` → `route_notes_llm()`

- Takes sample of notes (first 3, max 1500 characters)
- Formats skill descriptions from all available skills
- Sends to LLM with classification prompt:
  ```
  You are a routing classifier. Given the skill options below and a 
  sample of clinical notes, reply with ONLY the matching skill name 
  (no explanation, no punctuation).
  
  Skill options:
  - er: Use for Emergency Department (ED/ER) clinical notes...
  - opd: Use for Outpatient Department (OPD) clinical visit notes...
  
  Note sample:
  [First 1500 characters of notes]
  ```
- LLM returns best-matching department (er or opd)
- System uppercases the result and sets `config.department`

#### Step 6: Skill Loading
**File**: `src/skill_loader.py`
**Function**: `load_skill(department)`

- Reads `src/skills/{dept}/SKILL.md`:
  - Extracts YAML frontmatter (name, description)
  - Extracts body content as system_prompt (strips frontmatter)
- Imports `src/skills/{dept}/fields.py`:
  - `REQUIRED_FIELDS`: List of field names to extract
  - `FIELD_ALIASES`: Dictionary mapping variant names to canonical names
  - `scoring_fn()`: Function to calculate documentation appropriateness score
- Imports `src/skills/{dept}/prompt.py`:
  - `get_user_prompt()`: Function to format notes for LLM extraction
- Returns dictionary with all skill components

#### Step 7: Initialize Extractor
**File**: `src/extractor.py`
**Class**: `ClinicalNotesExtractor`

- Receives system_prompt, required_fields, field_aliases, scoring_fn
- Initializes OpenAI client (OpenRouter/DeepSeek) or Fireworks client
- Sets temperature, max_retries, timeout parameters
- Initializes token usage counters (total_input_tokens, total_output_tokens)

#### Step 8: Batch Extraction
**File**: `src/extractor.py`
**Functions**: `extract_batch()` → `extract_features()`

- Processes notes in batches (configurable via BATCH_SIZE in `.env`)
- For each batch:
  1. **Prompt Generation**: Calls `get_user_prompt(notes, diagnosis_context)` from skill's prompt.py
  2. **Context Formatting**: Adds billing ICD-10 codes and diagnosis names if available
  3. **LLM API Call**: Sends to LLM with:
     - System message: system_prompt from SKILL.md
     - User message: formatted prompt from prompt.py
     - Temperature, max_tokens parameters
  4. **Response Reception**: Receives JSON response from LLM
  5. **JSON Parsing** (5 fallback strategies):
     - **Strategy 1**: Strip markdown (```json, thinking tags), parse directly
     - **Strategy 2**: Extract array from "results" key
     - **Strategy 3**: Extract first JSON array found using bracket matching
     - **Strategy 4**: Extract first JSON object found using brace matching
     - **Strategy 5**: Search line-by-line for JSON patterns
  6. **Record Normalization**:
     - `_normalize_record()`: Maps field names via FIELD_ALIASES
     - Case-insensitive fallback for keys not in alias table
     - Ensures all required fields present (empty string if missing)
  7. **Count Correction**: `_fix_count()` ensures correct number of records
  8. **Retry Logic**: Exponential backoff (2^n seconds) on failure
  9. **Token Tracking**: Accumulates input/output tokens from API usage
- Returns list of structured data dictionaries

#### Step 9: ICD-10 Accuracy Calculation
**File**: `src/data_processor.py`
**Function**: `calculate_icd10_accuracy(ai_icd10, actual_icd10)`

- Compares AI-generated ICD-10 codes with actual billing codes from SQL
- Parses codes using regex: `[A-Z][0-9]{2,3}(?:\.[0-9A-Za-z]+)?`
- Compares at base/chapter level (e.g., J18 matches J18.9, I21 matches I21.9)
- Returns:
  - `1` if any AI code matches an actual code at base level
  - `0` if no match
  - `None` if inputs missing or invalid

#### Step 10: Documentation Appropriateness Scoring
**File**: `src/skills/{dept}/fields.py`
**Function**: `scoring_fn(record)`

- Calculates department-specific documentation quality score (0-100)
- Uses weighted field completeness based on clinical importance
- ER: Assessment 25%, Plan 15%, Chief Complaint 15%, etc.
- OPD: Treatment Plan 50%, Chief Complaint 20%, Diagnosis 10%, etc.
- Returns rounded score as float

#### Step 11: Data Validation
**File**: `src/data_processor.py`
**Function**: `validate_structured_data(data, required_fields, verbose)`

- Checks if all records contain all required fields
- Reports missing fields per record if verbose=True
- Returns True if all records valid, False otherwise

#### Step 12: Data Summary
**File**: `src/data_processor.py`
**Function**: `get_data_summary(data, required_fields)`

- Calculates completion rate per field (count and percentage)
- Computes overall completion rate across all fields
- Returns statistics dictionary:
  ```python
  {
    'total_records': int,
    'completion_rate': float,
    'fields_populated': {
      field_name: {'count': int, 'percentage': float}
    }
  }
  ```

#### Step 13: Database Insert
**File**: `src/database_ops.py`
**Function**: `insert_to_sql_table(structured_data, original_df, config)`

- Merges extracted data with original DataFrame
- **Column Handling**:
  - Renames columns via SOURCE_TO_DEST_COLUMN_MAP (e.g., ShortName → BU for ER)
  - Case-insensitive column name matching for destination table
  - Drops columns not in destination table with warning
- **Data Sanitization**:
  - `_sanitise_df()`: Removes newlines, truncates to column limits
  - `_get_table_column_lengths()`: Queries database schema for column max lengths
  - Converts datetime values to SQL Server compatible range (1753-01-01 to 9999-12-31)
  - Converts string representations of None/nan to NULL
- **Insertion**:
  - Uses pyodbc cursor with parameterized queries
  - Inserts rows one at a time with error reporting per row
  - Returns number of rows inserted
- **Failure Handling**:
  - On SQL failure, saves data to JSON file with timestamp
  - Provides retry command: `python main.py --load-json filename.json`

## Airflow Integration

### DAG Architecture

**File**: `dags/clinical_extractor_dag.py`

The Airflow DAG orchestrates the extraction pipeline into 6 tasks (3 per department) running in parallel:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ er_query    │───▶│ er_ai_process│───▶│ er_insert   │
└─────────────┘    └─────────────┘    └─────────────┘

┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ opd_query   │───▶│ opd_ai_process│───▶│ opd_insert  │
└─────────────┘    └─────────────┘    └─────────────┘
```

### Task Details

**er_query / opd_query**:
- Loads clinical notes from SQL Server
- Saves notes and original DataFrame to pickle file
- Returns pickle file path via XCom

**er_ai_process / opd_ai_process**:
- Loads notes from pickle file
- Runs AI extraction using ClinicalNotesExtractor
- Calculates ICD-10 accuracy and documentation scores
- Saves results to pickle file
- Returns data path, input tokens, output tokens via XCom

**er_insert / opd_insert**:
- Loads extracted data from pickle file
- Inserts to SQL Server
- Appends cost row to cost sheet CSV
- Returns rows inserted count

### Cost Tracking

**File**: `src/airflow_helpers.py`

The system tracks AI API costs per run:

```python
Cost Model (DeepSeek via OpenRouter):
- Input: $0.25 per 1M tokens
- Output: $0.95 per 1M tokens

Cost Sheet CSV columns:
- date: Run date (YYYY-MM-DD)
- run_id: Airflow run ID
- department: ER or OPD
- model: Model name (e.g., deepseek/deepseek-chat)
- input_tokens: Total input tokens consumed
- output_tokens: Total output tokens consumed
- records: Number of records processed
- rows_inserted: Number of rows successfully inserted
- cost_usd: Total cost in USD
```

### Scheduling

- **Schedule**: Daily at 10:30 AM Cairo time
- **Timezone**: Africa/Cairo
- **Catchup**: False (does not backfill missed runs)
- **Max Active Runs**: 1 (prevents overlapping executions)
- **Retries**: 2 with 5-minute delay

## Data Quality & Validation

### HTML Content Detection

The system uses sophisticated heuristics to detect and filter HTML content:

**Detection Criteria**:
- HTML doctype, html, head, meta charset, body tags
- CSS patterns: @media, @keyframes, border:, padding:, margin:
- JavaScript patterns: /_next/static, .js?, chunk, .bundle
- CSS class patterns: hyphenated-hex codes (e.g., text-muted-foreground)
- High tag count (≥3 tags) or high special character ratio

**Cleaning Process**:
1. Remove script tags and content
2. Remove style tags and content
3. Remove HTML comments
4. Remove CSS @rules
5. Decode HTML entities
6. Remove all HTML tags
7. Remove CSS class patterns
8. Normalize whitespace

### Note Deduplication

Clinical notes often contain duplicate parts due to SQL cartesian products:

**Process**:
1. Split note by `||` separator
2. Remove HTML-like parts
3. Strip HTML tags from remaining parts
4. Deduplicate based on lowercase content
5. Rejoin with `||` separator

### ICD-10 Code Normalization

**Process**:
1. Extract ICD-10 codes using regex: `[A-Z][0-9]{2,3}(?:\.[0-9A-Z]+)?`
2. Convert to uppercase
3. Remove spaces
4. Deduplicate codes
5. Join with semicolon separator

**Example**:
- Input: "j18.9, J18.9, i10, I10"
- Output: "J18.9; I10"

### Column Length Validation

Before insertion, the system:
1. Queries database schema for column maximum lengths
2. Truncates values exceeding limits with warning
3. Removes newlines and tabs from text fields
4. Converts datetime values to SQL Server compatible range

### Empty Note Filtering

Rows with empty or null notes are filtered out with:
- Warning message showing count of skipped rows
- Preservation of non-empty rows for processing

## ICD-10 Coding

### ER Exhaustive Coding Protocol

The ER skill implements an exhaustive ICD-10 coding protocol with mandatory checklist:

**Golden Rule**: Emit EVERY ICD-10 code that the note could plausibly support. Do not under-code.

**Mandatory Checklist**:
1. **Symptom codes (R00-R99)**: One for EACH symptom in Chief_Complaint
2. **Examination abnormality codes**: One for EACH abnormal finding in Assessment
3. **Lab abnormality codes**: One for EACH abnormal lab value
4. **ECG abnormality codes**: One for EACH ECG finding
5. **Imaging finding codes**: One for EACH abnormality on imaging + Z01.89
6. **Chronic condition codes**: Code EACH condition from Medical_Surgical_History
7. **Acute/working diagnosis codes**: Code the most likely diagnosis suggested
8. **External cause codes (V00-Y99)**: REQUIRED for ANY trauma/fall/injury
9. **Injury codes (S/T)**: For ANY trauma by body part
10. **OB/pregnancy codes**: If patient is pregnant
11. **Encounter/Z-codes**: Almost always at least one applies

**Minimum Yield**:
- Typical ED note: 6-12 codes
- Rich multi-system note: 8-15 codes
- Fragment: 1+ code per finding
- Medication order only: "not applicable"

**Code Hierarchy**: Include BOTH parent and child codes when unsure (e.g., R10.13 + R10.9 for epigastric pain)

### OPD Comprehensive Coding

The OPD skill generates comprehensive ICD-10 codes for all documented conditions:

**Rules**:
- ALWAYS include billing ICD-10 code if provided
- Generate codes for ALL diagnosable conditions (diagnoses, comorbidities, symptoms)
- Use most specific code level supported by note
- Add codes for secondary diagnoses and comorbidities
- For post-op visits: Z48.89 + original condition code
- For "FOR [procedure]" notes: Z01.818 + condition code
- Never leave empty if any clinical condition exists

**Common Mappings**:
- Diabetes mellitus → E11.9 (or more specific)
- Hypertension → I10
- Asthma → J45.909
- CKD → N18.x (specify stage)
- Chest pain → R07.9
- Follow-up after surgery → Z48.89

## Troubleshooting

### Database Connection Issues

**Symptom**: "Database connection test: FAILED"

**Solutions**:
1. Verify DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD in `.env`
2. Check SQL Server is accessible from your network
3. Verify ODBC Driver 17 for SQL Server is installed
4. Test with trusted connection if username/password fails:
   ```bash
   DB_TRUSTED_CONNECTION=yes
   DB_USERNAME=""
   DB_PASSWORD=""
   ```
5. Check firewall rules allow SQL Server port (usually 1433)

### LLM API Failures

**Symptom**: "ERROR after 3 retries" or "API returned HTML error page"

**Solutions**:
1. Verify OPENROUTER_API_KEY is valid and not expired
2. Check model name is correct (e.g., deepseek/deepseek-chat)
3. Verify OpenRouter service is operational
4. Check rate limits (reduce BATCH_SIZE if hitting limits)
5. Try alternative model if current model is unavailable
6. Check internet connectivity

### JSON Parsing Failures

**Symptom**: "All parsing strategies failed"

**Solutions**:
1. Check debug output for raw API response
2. Verify LLM is returning valid JSON (not markdown or text)
3. Adjust system prompt to enforce JSON-only output
4. Reduce temperature to 0.0 for more deterministic output
5. Check if model supports JSON mode (response_format={"type": "json_object"})

### Column Truncation Warnings

**Symptom**: "WARNING: Truncating X value(s) in column 'Y' to Z chars"

**Solutions**:
1. Check database column lengths in destination table
2. Increase column size in database schema if needed
3. Review if truncation is acceptable for affected fields
4. Consider splitting large text fields into multiple columns

### Empty Extraction Results

**Symptom**: "No structured data extracted" or all-empty records

**Solutions**:
1. Verify notes are not empty after cleaning (check debug output)
2. Check if LLM is refusing to extract (review system prompt)
3. Reduce batch size to give model more context per note
4. Verify required fields are not too restrictive
5. Check if notes are in a language the model doesn't support well

### Airflow DAG Not Triggering

**Symptom**: DAG not running at scheduled time

**Solutions**:
1. Verify DAG file is in AIRFLOW_HOME/dags directory
2. Check Airflow scheduler is running
3. Verify DAG is not paused in Airflow UI
4. Check schedule cron expression (10:30 AM Cairo time)
5. Review Airflow scheduler logs for errors
6. Verify project root is in sys.path (DAG adds it dynamically)

### Cost Tracking Issues

**Symptom**: Cost sheet not being updated

**Solutions**:
1. Verify CLINICAL_EXTRACTOR_COST_SHEET path is writable
2. Check data directory exists (DAG creates it if needed)
3. Verify cost model environment variables are set
4. Check if DAG tasks are completing successfully
5. Review Airflow task logs for cost append errors

## Dependencies

### Core Dependencies

```
pandas==2.3.3              # Data manipulation and analysis
numpy>=2.0,<3.0            # Numerical computing
openpyxl==3.1.5            # Excel file support (if needed)
streamlit==1.50.0          # Web UI (if needed for visualization)
openai>=1.0.0              # OpenRouter API client
fireworks-ai==0.19.19      # Fireworks AI API client (alternative)
python-dotenv==1.1.1       # Environment variable management
PyYAML==6.0.3              # Skill file parsing
requests==2.32.5            # HTTP requests
```

### Database Dependencies

```
pyodbc>=4.0.39              # SQL Server ODBC connectivity
SQLAlchemy>=1.4,<2.0       # SQL ORM and connection pooling
```

### Airflow Dependencies

```
apache-airflow>=2.8,<3.0   # Workflow orchestration
pendulum>=3.0              # Datetime handling with timezones
```

### Installation

```bash
pip install -r requirements.txt
```

### Optional Dependencies

For development or additional features:
- `pytest`: Unit testing
- `black`: Code formatting
- `flake8`: Linting
- `mypy`: Type checking

## File Structure

```
Clinical Extractor V2/
├── .env                          # Main configuration file
├── .env.er                       # ER-specific configuration
├── .env.opd                      # OPD-specific configuration
├── main.py                       # Entry point, orchestrates pipeline
├── requirements.txt              # Python dependencies
├── README.md                     # This file
├── src/
│   ├── __init__.py               # Package initialization
│   ├── config.py                 # Configuration loading and validation
│   ├── database_ops.py           # SQL Server operations (load, insert)
│   ├── data_processor.py         # Data validation, summary, ICD-10 accuracy
│   ├── extractor.py              # AI extraction with retry logic
│   ├── skill_loader.py           # Loads skill definitions
│   ├── skill_router.py           # LLM-based department routing
│   ├── airflow_helpers.py         # Airflow task helper functions
│   ├── er_query.sql              # SQL query for ER notes
│   ├── OPD_query.sql             # SQL query for OPD notes
│   └── skills/
│       ├── __init__.py           # Skills package initialization
│       ├── er/
│       │   ├── __init__.py       # ER skill package
│       │   ├── SKILL.md          # ER system prompt with YAML frontmatter
│       │   ├── fields.py         # ER field schema and scoring function
│       │   ├── prompt.py         # ER user prompt generator
│       │   └── utils.py          # ER utilities (note classification)
│       └── opd/
│           ├── __init__.py       # OPD skill package
│           ├── SKILL.md          # OPD system prompt with YAML frontmatter
│           ├── fields.py         # OPD field schema and scoring function
│           └── prompt.py         # OPD user prompt generator
├── dags/
│   ├── __init__.py               # DAGs package initialization
│   ├── clinical_extractor_dag.py # Airflow DAG for daily processing
│   └── data/                     # Cost sheet and state files (created at runtime)
│       └── cost_sheet.csv        # AI API cost tracking (append-only)
└── airflow_home/                 # Airflow runtime directory (if using local Airflow)
    ├── airflow.cfg               # Airflow configuration
    ├── dags/                     # Symlink to project dags/ directory
    └── logs/                     # Airflow task logs
```

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]

## Support

For issues, questions, or contributions, please contact [your contact information].
