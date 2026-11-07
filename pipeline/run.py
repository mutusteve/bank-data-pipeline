"""RUN THE WHOLE PIPELINE with one command:   python -m pipeline.run

Order of stages (each one is logged to ops.pipeline_runs):
  ingest -> transform -> gold -> reconcile -> documents -> retention

If any stage fails, the run stops, the failure is logged, and the command exits with code 1
so a scheduler (or CI) can tell that something went wrong.
"""
import sys
from datetime import datetime

import duckdb

from .config import PROCESSED_DIR, WAREHOUSE
from .gold import build_gold
from .ingest import load_bronze
from .observability import RunLogger
from .reconcile import ReconciliationError, run_checks, save_results
from .retention import apply_retention
from .transform import build_silver_and_quarantine
from .unstructured import ingest_documents


def count(con, table):
    return con.execute(f"select count(*) from {table}").fetchone()[0]


def run(as_of=None):
    """Run every stage. Returns True if the whole run succeeded."""
    as_of = as_of or datetime.now()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    log = RunLogger(con)
    print(f"run {log.run_id}  as_of {as_of:%Y-%m-%d %H:%M}")

    try:
        with log.stage("ingest") as s:
            load_bronze(con)
            s.rows = count(con, "bronze.transactions")

        with log.stage("transform") as s:
            build_silver_and_quarantine(con, as_of)
            s.rows = count(con, "silver.transactions")

        with log.stage("gold") as s:
            build_gold(con, as_of)
            s.rows = sum(count(con, f"gold.{t}") for t in
                         ("daily_channel_summary", "daily_account_summary", "account_features"))

        with log.stage("reconcile") as s:
            results = run_checks(con)
            save_results(con, results)
            failed = [r[0] for r in results if r[3] == "MISMATCH"]
            if failed:
                raise ReconciliationError("checks failed: " + "; ".join(failed))
            s.rows = len(results)

        with log.stage("documents") as s:
            s.rows = ingest_documents(con)["chunks"]          # chunks written (0 if nothing changed)

        with log.stage("retention") as s:
            s.rows = apply_retention(con)          # rows purged

        print("\nRun finished successfully.")
        return True
    except Exception as exc:
        print(f"\nRUN FAILED at the stage above: {type(exc).__name__}: {exc}")
        return False
    finally:
        con.close()


def main():
    sys.exit(0 if run() else 1)


if __name__ == "__main__":
    main()