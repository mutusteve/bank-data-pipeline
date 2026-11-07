"""TRANSFORM inside the warehouse: BRONZE -> SILVER (clean) + QUARANTINE (rejected).

  silver.transactions      rows that pass every rule, with proper types and tidy text
  quarantine.transactions  rows that failed a rule, kept as received, with the reason

Nothing is silently dropped: every bronze row ends up in exactly one of the two tables.

Run:   python -m pipeline.transform
"""
from datetime import datetime

import duckdb

from .config import WAREHOUSE
from .quality import build_rules, build_staging, reject_reason_sql


def build_silver_and_quarantine(con, as_of):
    build_staging(con)
    rules = build_rules(as_of)

    # Tag every row with its reject reason (NULL means the row is clean).
    con.execute(f"create or replace temp table stg_flagged as "
                f"select *, {reject_reason_sql(rules)} as reject_reason from stg_txn")

    # Standardise merchant names to their most common spelling, so 'naivas' and 'Naivas' become one merchant.
    con.execute("""
        create or replace temp table merchant_lookup as
        select lower(trim(merchant)) as merchant_key, mode(trim(merchant)) as merchant_clean
        from stg_flagged where reject_reason is null
        group by 1
    """)

    for schema in ("silver", "quarantine"):
        con.execute(f"create schema if not exists {schema}")

    con.execute("begin")   # publish both tables together, or neither
    try:
        con.execute("""
            create or replace table silver.transactions as
            select f.txn_id_n        as txn_id,
                   trim(f.account_id) as account_id,
                   f.txn_ts_t        as txn_ts,
                   f.amount_n        as amount,
                   f.currency_n      as currency,
                   f.direction_n     as direction,
                   f.channel_n       as channel,
                   m.merchant_clean  as merchant,
                   f.narrative       as narrative,
                   f.source_file
            from stg_flagged f
            join merchant_lookup m on m.merchant_key = lower(trim(f.merchant))
            where f.reject_reason is null
        """)
        con.execute("""
            create or replace table quarantine.transactions as
            select txn_id, account_id, txn_ts, amount, currency, direction, channel, merchant, narrative,
                   source_file, row_num, reject_reason, ? as quarantined_at
            from stg_flagged
            where reject_reason is not null
        """, [datetime.now()])
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise


def main():
    con = duckdb.connect(str(WAREHOUSE))
    build_silver_and_quarantine(con, as_of=datetime.now())

    bronze, silver, quar = (con.execute(f"select count(*) from {t}").fetchone()[0]
                            for t in ("bronze.transactions", "silver.transactions", "quarantine.transactions"))
    print(f"bronze {bronze}  ->  silver {silver} + quarantine {quar}")
    print("\nquarantine by reason:")
    for reason, n in con.execute("select reject_reason, count(*) from quarantine.transactions "
                                 "group by 1 order by 2 desc, 1").fetchall():
        print(f"  {reason:22} {n}")
    con.close()


if __name__ == "__main__":
    main()