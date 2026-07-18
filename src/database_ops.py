"""
Database operations for clinical notes extraction pipeline (department-agnostic).
"""
import re
import warnings
import pandas as pd
import pyodbc
from sqlalchemy import create_engine, text
from typing import List, Dict, Tuple
from pathlib import Path
from urllib.parse import quote_plus
from src.data_processor import strip_html_tags

warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy connectable.*",
    category=UserWarning,
)

# Source SQL column -> destination table column, where names differ.
# ER's query returns 'ShortName' but its destination table column is 'BU'.
# OPD's destination table uses 'shortname' (lowercase), so no rename needed.
SOURCE_TO_DEST_COLUMN_MAP = {
    "ER": {"ShortName": "BU"},
    "OPD": {},  # OPD keeps ShortName as-is (maps to shortname via case-insensitive matching)
}

# ID-like columns that must never be coerced to int/float during pandas round-trips
ID_COLUMNS_TO_PRESERVE = ['episode_key', 'Episode_key', 'visit_id', 'patient_code', 'Patient_Code']


def get_sql_connection_string(config) -> str:
    odbc_parts = [
        f"DRIVER={{{config.db_driver}}}",
        f"SERVER={config.db_server}",
        f"DATABASE={config.db_database}",
    ]
    if config.db_trusted_connection:
        odbc_parts.append("Trusted_Connection=yes")
    else:
        if config.db_username:
            odbc_parts.append(f"UID={config.db_username}")
        if config.db_password:
            odbc_parts.append(f"PWD={config.db_password}")

    odbc_string = ";".join(odbc_parts)
    encoded_odbc = quote_plus(odbc_string)
    return f"mssql+pyodbc:///?odbc_connect={encoded_odbc}"


def read_sql_query(file_path: str) -> str:
    try:
        current_dir = Path(__file__).parent
        project_root = current_dir.parent
        full_path = project_root / "src" / file_path

        if not full_path.exists():
            raise FileNotFoundError(f"SQL file not found: {full_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    except Exception as e:
        raise RuntimeError(f"Failed to read SQL file: {str(e)}")


def test_database_connection(config) -> bool:
    try:
        connection_string = get_sql_connection_string(config)
        engine = create_engine(connection_string)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 as test"))
        return True
    except Exception as e:
        print(f"   Database connection test: FAILED - {str(e)}")
        return False


def _is_html_content(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False

    sample = text[:2000].lower()

    if any(x in sample for x in ["<!doctype", "<html", "<head", "<meta charset", "<body"]):
        return True
    if any(x in sample for x in [
        "@media", "@keyframes", "{border:", "{padding:", "{margin:",
        "box-shadow:", "text-muted-foreground", "inline-flex", "whitespace-nowrap",
    ]):
        return True
    if re.search(r"/_next/static|\.js\?|chunk.*\.js|\.bundle\.js", sample):
        return True

    css_pattern_count = len(re.findall(r"\b[a-z]+-[a-z0-9]+-[a-z0-9]+\b", sample))
    if css_pattern_count >= 3:
        return True

    tag_count = len(re.findall(r"<[a-z]+[^>]*>", sample))
    if tag_count >= 3:
        return True

    closing_tag_count = len(re.findall(r"</[a-z]+>", sample))
    if closing_tag_count >= 2:
        return True

    word_count = len(re.findall(r"\b[a-zA-Z]{2,}\b", sample))
    special_count = len(re.findall(r'[<>{}=:";]', sample))
    if word_count < 20 and special_count > 30:
        return True

    if re.search(r'[a-z]+-[a-z]+-[a-z0-9]+.*[<>"]', sample):
        return True

    return False


def _deduplicate_note_parts(note: str) -> str:
    parts = [p.strip() for p in note.split("||") if p.strip()]
    seen = set()
    unique_parts = []
    for part in parts:
        if _is_html_content(part):
            continue
        cleaned = strip_html_tags(part)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            unique_parts.append(cleaned)
    return " || ".join(unique_parts)


def _clean_icd10_code(raw: str) -> str:
    if not raw or pd.isna(raw):
        return ""
    codes = re.findall(r"\b([A-Z][0-9]{2,3}(?:\.[0-9A-Z]+)?)\b", str(raw).upper())
    seen: set = set()
    unique = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return "; ".join(unique)


def load_notes_from_sql(config) -> Tuple[List[str], pd.DataFrame]:
    try:
        sql_text = read_sql_query(config.sql_file)
        connection_string = get_sql_connection_string(config)
        engine = create_engine(connection_string)

        print("   Executing SQL query...")
        conn_str = (
            f"DRIVER={{{config.db_driver}}};"
            f"SERVER={config.db_server};"
            f"DATABASE={config.db_database};"
        )
        if config.db_trusted_connection:
            conn_str += "Trusted_Connection=yes;"
        else:
            conn_str += f"UID={config.db_username};PWD={config.db_password};"
        conn = pyodbc.connect(conn_str)
        try:
            df = pd.read_sql_query(sql_text, conn)
        finally:
            conn.close()

        # Force ID columns to string to prevent truncation (e.g. "11_12345" -> int "12345")
        for col in df.columns:
            if col in ID_COLUMNS_TO_PRESERVE or col.lower() in [c.lower() for c in ID_COLUMNS_TO_PRESERVE]:
                df[col] = df[col].astype(str).replace('nan', '').replace('None', '')
                print(f"   Preserved column '{col}' as string (sample: {df[col].iloc[0] if len(df) > 0 else 'N/A'})")

        if config.max_rows and len(df) > config.max_rows:
            print(f"   Limiting to {config.max_rows} rows (from {len(df)} total)")
            df = df.head(config.max_rows)

        if config.notes_column not in df.columns:
            raise ValueError(
                f"Column '{config.notes_column}' not found in query results. "
                f"Available columns: {list(df.columns)}"
            )

        before_dedup = df[config.notes_column].astype(str)
        df[config.notes_column] = before_dedup.apply(_deduplicate_note_parts)

        duplicated_rows = sum(
            1 for orig, deduped in zip(before_dedup, df[config.notes_column])
            if orig != deduped
        )
        if duplicated_rows:
            print(f"   Deduplicated note parts in {duplicated_rows} row(s) (SQL cartesian product artefact removed)")

        before_strip = df[config.notes_column].copy()
        df[config.notes_column] = df[config.notes_column].apply(strip_html_tags)

        html_cleaned_rows = sum(
            1 for orig, cleaned in zip(before_strip, df[config.notes_column])
            if orig != cleaned
        )
        if html_cleaned_rows:
            print(f"   Stripped HTML tags from {html_cleaned_rows} row(s)")

        def _is_still_html_like(text: str) -> bool:
            if not text or len(text) < 10:
                return False
            sample = text[:500].lower()
            special_ratio = len(re.findall(r'[<>{}=:";]', sample)) / (len(sample) + 1)
            return special_ratio > 0.15

        html_like_mask = df[config.notes_column].apply(_is_still_html_like)
        html_like_count = html_like_mask.sum()
        if html_like_count:
            print(f"   Discarding {html_like_count} row(s) with HTML-like content that persisted after cleaning")
            df = df[~html_like_mask].reset_index(drop=True)

        if len(before_strip) > 0:
            print(f"\n   DEBUG: Sample note (before cleaning):")
            print(f"      {before_strip.iloc[0][:200]}...")
            if len(df) > 0:
                print(f"   DEBUG: Sample note (after cleaning):")
                print(f"      {df[config.notes_column].iloc[0][:200]}...")

        if "icd10_code" in df.columns:
            df["icd10_code"] = df["icd10_code"].apply(_clean_icd10_code)
        if "ICD10_code" in df.columns:
            df["ICD10_code"] = df["ICD10_code"].apply(_clean_icd10_code)

        df["_note_str"] = df[config.notes_column].fillna("").astype(str).str.strip()
        empty_mask = df["_note_str"] == ""
        empty_count = empty_mask.sum()
        if empty_count:
            print(f"   Skipping {empty_count} row(s) with empty/null notes (out of {len(df)} total)")
        df = df[~empty_mask].reset_index(drop=True)
        df.drop(columns=["_note_str"], inplace=True)

        if df.empty:
            print("   WARNING: No non-empty notes found after filtering — returning empty result")
            return [], pd.DataFrame()

        notes = df[config.notes_column].astype(str).tolist()
        print(f"   Loaded {len(notes)} note(s) for extraction")
        return notes, df

    except Exception as e:
        raise RuntimeError(f"SQL load failed: {str(e)}")


def _get_table_column_lengths(conn, schema: str, table: str) -> Dict[str, int]:
    query = """
        SELECT COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
          AND CHARACTER_MAXIMUM_LENGTH IS NOT NULL
    """
    cursor = conn.cursor()
    cursor.execute(query, (schema, table))
    result = {}
    for col_name, max_len in cursor.fetchall():
        result[col_name] = 10**9 if max_len == -1 else int(max_len)
    cursor.close()
    return result


def insert_to_sql_table(
    structured_data: List[Dict],
    original_df: pd.DataFrame,
    config,
) -> int:
    def _sanitise_df(df: pd.DataFrame, column_max_lengths: Dict[str, int]) -> pd.DataFrame:
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(r"[\r\n\t]+", " ", regex=True)
                    .str.strip()
                )
                if col in column_max_lengths:
                    cap = column_max_lengths[col]
                    too_long = df[col].str.len() > cap
                    if too_long.any():
                        print(f"   WARNING: Truncating {too_long.sum()} value(s) in column '{col}' to {cap} chars (DB limit)")
                    df[col] = df[col].str[:cap]
        return df

    try:
        if not structured_data:
            print("   WARNING: No structured data to insert — skipping")
            return 0

        df_extracted = pd.DataFrame(structured_data)

        if original_df is not None and len(original_df) > 0:
            left = original_df.reset_index(drop=True)
            for _id_col in ID_COLUMNS_TO_PRESERVE:
                if _id_col in left.columns:
                    left[_id_col] = left[_id_col].astype(str).replace({'nan': '', 'None': ''})
            overlap = set(left.columns) & set(df_extracted.columns)
            if overlap:
                print(f"   WARNING: Overlapping column names — renaming source copies with '_src' suffix: {sorted(overlap)}")
                left = left.rename(columns={c: f"{c}_src" for c in overlap})
            final_df = pd.concat([left, df_extracted], axis=1)
        else:
            final_df = df_extracted

        conn_str = (
            f"DRIVER={{{config.db_driver}}};"
            f"SERVER={config.db_server};"
            f"DATABASE={config.db_database};"
        )
        if config.db_trusted_connection:
            conn_str += "Trusted_Connection=yes;"
        else:
            conn_str += f"UID={config.db_username};PWD={config.db_password};"

        conn = pyodbc.connect(conn_str)
        try:
            db_col_lengths = _get_table_column_lengths(conn, config.output_schema, config.output_table)
            final_df = _sanitise_df(final_df, db_col_lengths)

            cursor = conn.cursor()
            cursor.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
                (config.output_schema, config.output_table),
            )
            db_columns = [row[0] for row in cursor.fetchall()]
            cursor.close()

            db_columns_lower = {c.lower(): c for c in db_columns}

            # Explicit source -> destination renames (e.g. ShortName -> BU for ER)
            dept_map = SOURCE_TO_DEST_COLUMN_MAP.get(config.department.upper(), {})
            for src_col, dst_col in dept_map.items():
                if src_col in final_df.columns and dst_col not in final_df.columns:
                    final_df = final_df.rename(columns={src_col: dst_col})
                    print(f"   Renamed source column '{src_col}' -> '{dst_col}' for destination table")

            rename_map = {}
            for df_col in final_df.columns:
                if df_col not in db_columns and df_col.lower() in db_columns_lower:
                    rename_map[df_col] = db_columns_lower[df_col.lower()]
            if rename_map:
                print(f"   Renaming columns to match DB casing: {rename_map}")
                final_df = final_df.rename(columns=rename_map)
                final_df = _sanitise_df(final_df, db_col_lengths)

            db_columns_set = set(db_columns)
            extra_cols = [c for c in final_df.columns if c not in db_columns_set]
            if extra_cols:
                print(f"   WARNING: Dropping columns not in destination table: {extra_cols}")
                final_df = final_df.drop(columns=extra_cols)

            for col in final_df.columns:
                if pd.api.types.is_datetime64_any_dtype(final_df[col]):
                    final_df[col] = pd.to_datetime(final_df[col], errors="coerce")
                    min_dt = pd.Timestamp("1753-01-01")
                    max_dt = pd.Timestamp("9999-12-31")
                    out_of_range = (final_df[col] < min_dt) | (final_df[col] > max_dt)
                    if out_of_range.any():
                        print(f"   WARNING: {out_of_range.sum()} value(s) in datetime column '{col}' out of SQL Server range — setting to NULL")
                        final_df.loc[out_of_range, col] = pd.NaT

            cursor = conn.cursor()
            cursor.fast_executemany = False
            table_full = f"[{config.output_schema}].[{config.output_table}]"
            columns = list(final_df.columns)
            col_names = ", ".join(f"[{c}]" for c in columns)
            placeholders = ", ".join(["?"] * len(columns))
            insert_sql = f"INSERT INTO {table_full} ({col_names}) VALUES ({placeholders})"

            def _convert(v):
                try:
                    if pd.isna(v):
                        return None
                except (TypeError, ValueError):
                    pass
                if isinstance(v, str) and v.strip().lower() in ('none', 'nan', 'null', 'n/a', 'na', 'not applicable', '-'):
                    return None
                if isinstance(v, pd.Timestamp):
                    return v.to_pydatetime()
                return v

            rows = [
                tuple(_convert(v) for v in row)
                for row in final_df.itertuples(index=False, name=None)
            ]

            inserted = 0
            for i, row in enumerate(rows):
                try:
                    cursor.execute(insert_sql, row)
                    inserted += 1
                except pyodbc.Error as row_err:
                    diag = []
                    for col, val in zip(columns, row):
                        if isinstance(val, str):
                            cap = db_col_lengths.get(col, "?")
                            diag.append(f"{col}(len={len(val)}, cap={cap})")
                    print(f"   ERROR inserting row {i}: {row_err}\n      Row column info: {'; '.join(diag)}")
                    raise

            conn.commit()
            cursor.close()
        finally:
            conn.close()

        return inserted

    except Exception as e:
        raise Exception(f"Failed to insert to SQL: {str(e)}")
