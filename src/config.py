"""
Configuration for clinical notes extraction pipeline.
Reads from .env file in project root.

DEPARTMENT is now OPTIONAL. If set, it pins the pipeline to that skill
(legacy behavior — same as before). If unset/AUTO, the pipeline loads notes
first, then uses src.skill_router to pick the department automatically from
each skill's SKILL.md description — the "agent reads descriptions and picks"
concept, instead of a hardcoded value.
"""
import os
from pathlib import Path
from dotenv import load_dotenv


class ExtractionConfig:
    def __init__(self, env_path: str = None):
        if env_path:
            load_dotenv(env_path)
        else:
            project_root = Path(__file__).parent.parent
            env_file = project_root / ".env"
            if env_file.exists():
                load_dotenv(env_file)
            else:
                load_dotenv()

        # Department selector — optional now. "", "AUTO", or unset => router decides.
        raw_dept = os.getenv("DEPARTMENT", "AUTO").strip().upper()
        self.department: str = None if raw_dept in ("", "AUTO") else raw_dept

        # Routing strategy when department is auto-detected: 'llm' (one classification call per run).
        self.routing_strategy: str = os.getenv("ROUTING_STRATEGY", "llm").strip().lower()

        # AI provider
        self.api_key: str = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("FIREWORKS_API_KEY", "")
        self.model: str = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
        self.temperature: float = float(os.getenv("TEMPERATURE", "0.0"))
        self.batch_size: int = int(os.getenv("BATCH_SIZE", "3"))

        # Database
        self.db_server: str = os.getenv("DB_SERVER", "")
        self.db_database: str = os.getenv("DB_DATABASE", "")
        self.db_driver: str = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
        self.db_username: str = os.getenv("DB_USERNAME", "")
        self.db_password: str = os.getenv("DB_PASSWORD", "")
        trusted = os.getenv("DB_TRUSTED_CONNECTION", "no").strip().lower()
        self.db_trusted_connection: bool = trusted in ("yes", "true", "1")

        # Column / query config — now explicit, NOT derived from department,
        # since department may not be known until after notes are loaded.
        self.notes_column: str = os.getenv("NOTES_COLUMN", "Note")
        self.sql_file: str = os.getenv("SQL_FILE", "er_query.sql")
        max_rows_env = os.getenv("MAX_ROWS", "")
        self.max_rows: int = int(max_rows_env) if max_rows_env.strip() else None

        # Output table — if not explicitly set, resolved per-department after
        # routing (see DEFAULT_OUTPUT_TABLES below / main.py).
        self.output_schema: str = os.getenv("OUTPUT_SCHEMA", "dbo")
        self.output_table: str = os.getenv("OUTPUT_TABLE", "")  # may be "" until routed

    def resolve_output_table(self, department: str):
        """Call after department is known (explicit or routed) to fill in a
        sensible default output table if OUTPUT_TABLE wasn't set in .env."""
        if self.output_table:
            return
        defaults = {
            "ER": "Clinical_Notes_Features_New",
            "OPD": "OPD_Extracted",
        }
        self.output_table = defaults.get(department.upper(), f"{department}_Extracted")

    def validate(self):
        errors = []

        if not self.api_key:
            errors.append("OPENROUTER_API_KEY / FIREWORKS_API_KEY is not set")
        if not self.db_server:
            errors.append("DB_SERVER is not set")
        if not self.db_database:
            errors.append("DB_DATABASE is not set")
        if not self.db_trusted_connection:
            if not self.db_username:
                errors.append("DB_USERNAME is not set (required when not using trusted connection)")
            if not self.db_password:
                errors.append("DB_PASSWORD is not set (required when not using trusted connection)")

        if errors:
            print("\nConfiguration errors:")
            for err in errors:
                print(f"   - {err}")
            raise ValueError(f"Invalid configuration: {len(errors)} error(s) found")

        print("   Configuration loaded:")
        print(f"      Department:  {self.department or '(auto — routed at runtime)'}")
        print(f"      Routing:     {self.routing_strategy if self.department is None else 'n/a (pinned)'}")
        print(f"      Model:       {self.model}")
        print(f"      DB Server:   {self.db_server}")
        print(f"      DB Name:     {self.db_database}")
        print(f"      SQL file:    {self.sql_file}")
        print(f"      Batch size:  {self.batch_size}")
        print(f"      Max rows:    {self.max_rows or 'unlimited'}")
