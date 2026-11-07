"""RECONCILIATION: prove that no rows or money were lost or invented between the layers.

Four checks, each comparing an EXPECTED number with an ACTUAL number:
  1. source rows      = bronze rows                   (did we load every row from the file?)
  2. source amount    = bronze amount                 (did the money total survive the load?)
  3. bronze rows      = silver + quarantine rows      (was any row dropped by cleaning?)
  4. bronze amount    = silver + quarantine amount    (was any money lost by cleaning?)

In production the source system sends its own control totals. Here we recompute them from the CSV
with plain Python, a different tool from the one that loaded it, so the check is still independent.
Every result is saved to ops.reconciliation, so there is an audit trail.

Run:   python -m pipeline.reconcile      (exit code 1 if any check fails)
"""
import csv
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

import duckdb

from .config import RAW_DIR, WAREHOUSE


class ReconciliationError(RuntimeError):
    """Raised when the layers do not add up."""


def source_control_totals(path):
    """Row count and amount total, counted straight from the CSV file."""
    rows, total = 0, Decimal("0")
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows += 1
            try:
                total += Decimal(row["amount"])
            except InvalidOperation:      # blank or 'N/A' amounts have no value to add
                pass
    return rows, total.quantize(Decimal("0.01"))


def run_checks(con, raw_dir=RAW_DIR):
    src_rows, src_amount = source_control_totals(raw_dir / "transactions.csv")
    one = lambda sql: con.execute(sql).fetchone()[0]   # noqa: E731 - tiny helper for readability

    bronze_rows = one("select count(*) from bronze.transactions")
    bronze_amount = one("select coalesce(sum(try_cast(amount as decimal(18,2))), 0) from bronze.transactions")
    silver_rows = one("select count(*) from silver.transactions")
    silver_amount = one("select coalesce(sum(amount), 0) from silver.transactions")
    quar_rows = one("select count(*) from quarantine.transactions")
    quar_amount = one("select coalesce(sum(try_cast(amount as decimal(18,2))), 0) from quarantine.transactions")
    gold_chan_rows = one("select coalesce(sum(txn_count), 0) from gold.daily_channel_summary")
    gold_chan_amount = one("select coalesce(sum(total_amount), 0) from gold.daily_channel_summary")
    gold_acct_rows = one("select coalesce(sum(txn_count), 0) from gold.daily_account_summary")

    checks = [
        ("source_rows = bronze_rows", src_rows, bronze_rows),
        ("source_amount = bronze_amount", src_amount, bronze_amount),
        ("bronze_rows = silver + quarantine rows", bronze_rows, silver_rows + quar_rows),
        ("bronze_amount = silver + quarantine amount", bronze_amount, silver_amount + quar_amount),
        ("silver_rows = gold channel rows", silver_rows, gold_chan_rows),
        ("silver_amount = gold channel amount", silver_amount, gold_chan_amount),
        ("silver_rows = gold account rows", silver_rows, gold_acct_rows),
    ]
    return [(name, str(exp), str(act), "MATCH" if str(exp) == str(act) else "MISMATCH")
            for name, exp, act in checks]


def save_results(con, results):
    con.execute("create schema if not exists ops")
    con.execute("""create table if not exists ops.reconciliation (
                       check_name varchar, expected varchar, actual varchar, status varchar, checked_at timestamp)""")
    now = datetime.now()
    con.executemany("insert into ops.reconciliation values (?,?,?,?,?)", [(*r, now) for r in results])


def main():
    con = duckdb.connect(str(WAREHOUSE))
    results = run_checks(con)
    save_results(con, results)
    con.close()

    for name, expected, actual, status in results:
        print(f"{status:9} {name:45} expected {expected:>12}  actual {actual:>12}")
    if any(r[3] == "MISMATCH" for r in results):
        print("\nRECONCILIATION FAILED: do not publish these tables.")
        sys.exit(1)
    print("\nAll checks match.")


if __name__ == "__main__":
    main()