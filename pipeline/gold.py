"""GOLD layer: business-ready data products built from the clean SILVER data.

  gold.daily_channel_summary   one row per day, channel and currency  (for BI dashboards)
  gold.daily_account_summary   one row per account, day and currency  (for customer-level reporting)
  gold.account_features        one row per account, behaviour summary (an input for analytics / AI later)

Rules for gold tables: they hold no raw identifiers beyond the account id, they are rebuilt from silver
every run (so they can never drift from it), and amounts are never added across different currencies.

Run:   python -m pipeline.gold
"""
from datetime import datetime

import duckdb

from .config import WAREHOUSE


def build_gold(con, as_of):
    con.execute("create schema if not exists gold")

    con.execute("""
        create or replace table gold.daily_channel_summary as
        select cast(txn_ts as date)                                  as txn_date,
               channel,
               currency,
               count(*)                                              as txn_count,
               coalesce(sum(amount) filter (where direction = 'DR'), 0) as debit_total,
               coalesce(sum(amount) filter (where direction = 'CR'), 0) as credit_total,
               sum(amount)                                           as total_amount
        from silver.transactions
        group by all
    """)

    con.execute("""
        create or replace table gold.daily_account_summary as
        select account_id,
               cast(txn_ts as date)                                  as txn_date,
               currency,
               count(*)                                              as txn_count,
               coalesce(sum(amount) filter (where direction = 'DR'), 0) as debit_total,
               coalesce(sum(amount) filter (where direction = 'CR'), 0) as credit_total
        from silver.transactions
        group by all
    """)

    # Behaviour features per account. KES only: adding KES, USD and EUR together would be meaningless
    # without exchange rates, so other currencies are left out of this table on purpose.
    con.execute("""
        create or replace table gold.account_features as
        select account_id,
               count(*)                                              as txn_count,
               coalesce(sum(amount) filter (where direction = 'DR'), 0) as debit_total,
               round(avg(amount), 2)                                 as avg_txn_amount,
               count(distinct channel)                               as distinct_channels,
               round(avg(case when channel = 'MPESA' then 1.0 else 0.0 end), 3) as mpesa_share,
               date_diff('day', max(txn_ts), ?::timestamp)           as days_since_last_txn,
               ?::timestamp                                          as feature_as_of
        from silver.transactions
        where currency = 'KES'
        group by account_id
    """, [as_of, as_of])


def main():
    con = duckdb.connect(str(WAREHOUSE))
    build_gold(con, as_of=datetime.now())
    for table in ("daily_channel_summary", "daily_account_summary", "account_features"):
        n = con.execute(f"select count(*) from gold.{table}").fetchone()[0]
        print(f"gold.{table}: {n} rows")
    print("\nKES transactions by channel (all days):")
    for channel, n, total in con.execute("""
            select channel, sum(txn_count), sum(total_amount) from gold.daily_channel_summary
            where currency = 'KES' group by channel order by 3 desc""").fetchall():
        print(f"  {channel:8} {n:>6} txns   {total:>14,.2f} KES")
    con.close()


if __name__ == "__main__":
    main()