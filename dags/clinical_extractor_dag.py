"""
Clinical Extractor DAG — runs ER and OPD extraction pipelines daily.
No Docker: plain PythonOperators calling into src/airflow_helpers.py.

6 tasks total (3 per department, department branches run in parallel):
  er_query        -> er_ai_process        -> er_insert
  opd_query       -> opd_ai_process       -> opd_insert

Each *_insert task appends one row (date, tokens, cost) to a persistent
cost sheet CSV (append-only — nothing is ever removed).

Requires: DAGS folder must be able to `import src...`, so this project's
root is added to sys.path below. Place this repo somewhere Airflow can
read, and set that path (or symlink this `dags/` folder into your
AIRFLOW_HOME/dags).
"""
import sys
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import heavy dependencies inside functions to avoid DAG parsing timeout

CAIRO_TZ = pendulum.timezone("Africa/Cairo")

default_args = {
    "owner": "clinical-extractor",
    "retries": 2,
    "retry_delay": pendulum.duration(minutes=5),
}

with DAG(
    dag_id="clinical_extractor_daily",
    description="ER + OPD clinical notes extraction (query -> AI -> insert) with cost tracking",
    schedule="30 10 * * *",  # 10:30 AM Cairo time, every day
    start_date=pendulum.datetime(2025, 1, 1, tz=CAIRO_TZ),
    catchup=False,
    default_args=default_args,
    max_active_runs=1,
    tags=["clinical-extractor", "er", "opd"],
) as dag:

    def _query(department, **ctx):
        from src.airflow_helpers import run_query  # noqa: E402
        return run_query(department, run_id=ctx["run_id"])

    def _ai_process(department, **ctx):
        from src.airflow_helpers import run_ai_process  # noqa: E402
        notes_path = ctx["ti"].xcom_pull(task_ids=f"{department.lower()}_query")
        return run_ai_process(department, run_id=ctx["run_id"], notes_path=notes_path)

    def _insert(department, **ctx):
        from src.airflow_helpers import run_insert  # noqa: E402
        result = ctx["ti"].xcom_pull(task_ids=f"{department.lower()}_ai_process")
        return run_insert(
            department,
            run_id=ctx["run_id"],
            data_path=result["data_path"],
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
        )

    tasks = {}
    for dept in ("er", "opd"):
        query_task = PythonOperator(
            task_id=f"{dept}_query",
            python_callable=_query,
            op_kwargs={"department": dept.upper()},
        )
        ai_task = PythonOperator(
            task_id=f"{dept}_ai_process",
            python_callable=_ai_process,
            op_kwargs={"department": dept.upper()},
        )
        insert_task = PythonOperator(
            task_id=f"{dept}_insert",
            python_callable=_insert,
            op_kwargs={"department": dept.upper()},
        )
        query_task >> ai_task >> insert_task
        tasks[dept] = (query_task, ai_task, insert_task)

    # er and opd branches are independent -> Airflow runs them in parallel
    # automatically (no cross-branch dependency declared).
