"""
Helper functions used by the Airflow DAG (dags/clinical_extractor_dag.py).
Wraps the existing pipeline (config, database_ops, extractor) into 3 discrete
steps per department: query -> ai_process -> insert, with intermediate
state passed between Airflow tasks via pickle files (not XCom, since
DataFrames / note lists can be large).
"""
import os
import pickle
from pathlib import Path
from datetime import datetime

import pandas as pd

from src.config import ExtractionConfig
from src.database_ops import load_notes_from_sql, insert_to_sql_table
from src.data_processor import calculate_icd10_accuracy
from src.extractor import ClinicalNotesExtractor

# ------------------------------------------------------------------ #
# Cost model — deepseek/deepseek-chat via OpenRouter.
# Quoted range: $0.20-0.25 / 1M input tokens, $0.80-0.95 / 1M output tokens.
# Defaults below use the upper bound (conservative). Override via env vars
# DEEPSEEK_INPUT_COST_PER_M / DEEPSEEK_OUTPUT_COST_PER_M if OpenRouter
# pricing changes.
# ------------------------------------------------------------------ #
INPUT_COST_PER_M = float(os.getenv("DEEPSEEK_INPUT_COST_PER_M", "0.25"))
OUTPUT_COST_PER_M = float(os.getenv("DEEPSEEK_OUTPUT_COST_PER_M", "0.95"))

SQL_FILE_MAP = {"ER": "er_query.sql", "OPD": "OPD_query.sql"}

STATE_DIR = Path(os.getenv("CLINICAL_EXTRACTOR_STATE_DIR", "/tmp/clinical_extractor"))

# Cost sheet: appended to forever, never overwritten/rotated.
COST_SHEET_PATH = Path(
    os.getenv("CLINICAL_EXTRACTOR_COST_SHEET", str(Path(os.getenv("AIRFLOW_HOME", ".")) / "data" / "cost_sheet.csv"))
)


def _run_dir(run_id: str) -> Path:
    d = STATE_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_config(department: str) -> ExtractionConfig:
    config = ExtractionConfig()
    config.department = department.upper()
    config.sql_file = SQL_FILE_MAP[department.upper()]
    config.resolve_output_table(department)
    config.validate()
    return config


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * INPUT_COST_PER_M + (output_tokens / 1_000_000) * OUTPUT_COST_PER_M


# ------------------------------------------------------------------ #
# Step 1: query
# ------------------------------------------------------------------ #
def run_query(department: str, run_id: str) -> str:
    config = build_config(department)
    notes, original_df = load_notes_from_sql(config)

    out_path = _run_dir(run_id) / f"{department}_notes.pkl"
    with open(out_path, "wb") as f:
        pickle.dump({"notes": notes, "original_df": original_df}, f)
    return str(out_path)


# ------------------------------------------------------------------ #
# Step 2: AI process
# ------------------------------------------------------------------ #
def run_ai_process(department: str, run_id: str, notes_path: str) -> dict:
    with open(notes_path, "rb") as f:
        payload = pickle.load(f)
    notes, original_df = payload["notes"], payload["original_df"]

    if not notes:
        out_path = _run_dir(run_id) / f"{department}_result.pkl"
        with open(out_path, "wb") as f:
            pickle.dump({"structured_data": [], "original_df": original_df}, f)
        return {"data_path": str(out_path), "input_tokens": 0, "output_tokens": 0, "records": 0}

    config = build_config(department)

    diagnosis_context = None
    icd_col = next((c for c in ("icd10_code", "ICD10_code") if c in original_df.columns), None)
    if icd_col:
        diag_col = "diagnosis_name" if "diagnosis_name" in original_df.columns else None
        diagnosis_context = [
            {
                "icd10_code": str(row.get(icd_col, "") or ""),
                **({"diagnosis_name": str(row.get(diag_col, "") or "")} if diag_col else {}),
            }
            for _, row in original_df.iterrows()
        ]

    extractor = ClinicalNotesExtractor(
        department=config.department,
        api_key=config.api_key,
        model=config.model,
        temperature=config.temperature,
    )
    structured_data = extractor.extract_batch(
        notes, diagnosis_context=diagnosis_context, batch_size=config.batch_size
    )

    icd_ai_field = "icd10_AI_Generated" if department.upper() == "OPD" else "Recommended_ICD10"
    for i, record in enumerate(structured_data):
        actual_icd10 = ""
        if i < len(original_df):
            for col in ("ICD10_code", "icd10_code"):
                if col in original_df.columns:
                    val = original_df.iloc[i].get(col, "")
                    if val and not (isinstance(val, float) and val != val):
                        actual_icd10 = str(val)
                        break
        record["ICD10_Accuracy"] = calculate_icd10_accuracy(record.get(icd_ai_field, ""), actual_icd10)
        record["Documentation_Appropriateness"] = extractor.scoring_fn(record)

    out_path = _run_dir(run_id) / f"{department}_result.pkl"
    with open(out_path, "wb") as f:
        pickle.dump({"structured_data": structured_data, "original_df": original_df}, f)

    return {
        "data_path": str(out_path),
        "input_tokens": extractor.total_input_tokens,
        "output_tokens": extractor.total_output_tokens,
        "records": len(structured_data),
    }


# ------------------------------------------------------------------ #
# Step 3: insert + cost sheet append
# ------------------------------------------------------------------ #
def run_insert(department: str, run_id: str, data_path: str, input_tokens: int, output_tokens: int) -> int:
    with open(data_path, "rb") as f:
        payload = pickle.load(f)
    structured_data, original_df = payload["structured_data"], payload["original_df"]

    config = build_config(department)
    rows_inserted = 0
    if structured_data:
        rows_inserted = insert_to_sql_table(structured_data=structured_data, original_df=original_df, config=config)

    append_cost_row(
        {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "run_id": run_id,
            "department": department.upper(),
            "model": config.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "records": len(structured_data),
            "rows_inserted": rows_inserted,
            "cost_usd": round(compute_cost(input_tokens, output_tokens), 6),
        }
    )
    return rows_inserted


def append_cost_row(row: dict) -> None:
    """Appends one row to the cost sheet CSV. Never overwrites existing data."""
    COST_SHEET_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    write_header = not COST_SHEET_PATH.exists()
    df.to_csv(COST_SHEET_PATH, mode="a", header=write_header, index=False)
