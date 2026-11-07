"""EXTRACT + LOAD: land the raw CSV files in the warehouse exactly as received (the BRONZE layer).

No cleaning happens here. Every column is stored as text, so no value is silently changed, and we add
audit columns (which file, which row, when) so any row can be traced back to its source.

Note: this reloads bronze from scratch each run (simple and repeatable). Real pipelines usually
append new files and skip ones already loaded; we add that later.

Run:   python -m pipeline.ingest
"""
from datetime import datetime

import duckdb

from .config import PROCESSED_DIR, RAW_DIR, WAREHOUSE


def load_bronze(con, raw_dir=RAW_DIR):
    con.execute("create schema if not exists bronze")
    loaded_at = datetime.now()
    for table in ("transactions", "accounts"):
        path = raw_dir / f"{table}.csv"
        con.execute(f"""
            create or replace table bronze.{table} as
            select *,
                   row_number() over ()  as row_num,        -- position in the file
                   ?                     as source_file,    -- where it came from
                   ?                     as ingested_at     -- when we loaded it
            from read_csv(?, header=true, all_varchar=true)
        """, [path.name, loaded_at, str(path)])
        n = con.execute(f"select count(*) from bronze.{table}").fetchone()[0]
        print(f"bronze.{table}: {n} rows loaded from {path.name}")


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    load_bronze(con)
    con.close()


if __name__ == "__main__":
    main()