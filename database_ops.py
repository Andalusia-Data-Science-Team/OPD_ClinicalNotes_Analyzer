"""
Database operations for clinical notes extraction pipeline.
"""
import os
import pandas as pd
import pyodbc
from sqlalchemy import create_engine, text
from typing import List, Dict, Tuple
from pathlib import Path
from urllib.parse import quote_plus


def get_sql_connection_string(config) -> str:
    """Build SQL Server connection string for SQLAlchemy."""
    # Build ODBC connection string
    odbc_parts = [
        f"DRIVER={{{config.db_driver}}}",
        f"SERVER={config.db_server}",
        f"DATABASE={config.db_database}",
    ]
    
    if config.db_trusted_connection:
        # Use Windows Authentication
        odbc_parts.append("Trusted_Connection=yes")
    else:
        # Use SQL Server Authentication
        if config.db_username:
            odbc_parts.append(f"UID={config.db_username}")
        if config.db_password:
            odbc_parts.append(f"PWD={config.db_password}")
    
    odbc_string = ";".join(odbc_parts)
    
    # URL encode the ODBC string for SQLAlchemy
    encoded_odbc = quote_plus(odbc_string)
    
    # Return SQLAlchemy-compatible URL
    return f"mssql+pyodbc:///?odbc_connect={encoded_odbc}"


def read_sql_query(file_path: str = "OPD_query.sql") -> str:
    try:
        # Get the project root (parent of src directory)
        current_dir = Path(__file__).parent
        project_root = current_dir.parent
        full_path = project_root / "src" / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"SQL file not found: {full_path}")
        
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    
    except Exception as e:
        raise RuntimeError(f"Failed to read SQL file: {str(e)}")


def test_database_connection(config) -> bool:
    """Test database connection before proceeding."""
    try:
        connection_string = get_sql_connection_string(config)
        
        # Try to connect and run a simple query
        engine = create_engine(connection_string)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            return True
    except Exception as e:
        print(f"   Database connection test: FAILED - {str(e)}")
        return False


def load_notes_from_sql(config) -> Tuple[List[str], pd.DataFrame]:
    try:
        # Read SQL query
        sql_text = read_sql_query("OPD_query.sql")
        
        # Create database connection
        connection_string = get_sql_connection_string(config)
        engine = create_engine(connection_string)
        
        # Execute query and load data
        print(f"   Executing SQL query...")
        df = pd.read_sql_query(sql_text, engine)
        
        # Limit rows if specified
        if config.max_rows and len(df) > config.max_rows:
            print(f"   Limiting to {config.max_rows} rows (from {len(df)} total)")
            df = df.head(config.max_rows)
        
        # Extract notes from specified column
        if config.notes_column not in df.columns:
            raise ValueError(f"Column '{config.notes_column}' not found in query results")
        
        notes = df[config.notes_column].fillna("").astype(str).tolist()
        
        return notes, df
        
    except Exception as e:
        raise RuntimeError(f"SQL load failed: {str(e)}")


def insert_to_sql_table(
    structured_data: List[Dict],
    original_df: pd.DataFrame,
    config
) -> int:
    try:
        # Prepare structured data as DataFrame
        df_extracted = pd.DataFrame(structured_data)
        
        # Combine with original data
        if original_df is not None:
            final_df = pd.concat([original_df.reset_index(drop=True), df_extracted], axis=1)
        else:
            final_df = df_extracted
        
        # Create database connection
        connection_string = get_sql_connection_string(config)
        engine = create_engine(connection_string)
        
        # Insert data
        table_name = f"{config.output_schema}.{config.output_table}"
        final_df.to_sql(
            name=config.output_table,
            con=engine,
            schema=config.output_schema,
            if_exists="append",
            index=False
        )
        
        return len(final_df)
        
    except Exception as e:
        raise Exception(f"Failed to insert to SQL: {str(e)}")
