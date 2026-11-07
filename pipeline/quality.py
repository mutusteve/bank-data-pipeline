"""Data quality rules for the raw transactions.

Each rule is a name plus a SQL condition that is TRUE when a row FAILS the rule.
Writing rules as data (not scattered if-statements) means we can use the same list to:
  1. count how many rows break each rule (this step), and
  2. decide which rows to reject and why (next step).

Run a check on the raw files:   python -m pipeline.quality
"""
from dataclasses import dataclass
from datetime import datetime

import duckdb

from .config import ALLOWED_CHANNELS, ALLOWED_CURRENCIES, ALLOWED_DIRECTIONS, WAREHOUSE


class DataQualityError(RuntimeError):
    """Raised when a batch is too bad to publish."""
@dataclass(frozen=True)
class Rule:
    name: str
    condition: str     # SQL: TRUE when the row FAILS
    meaning: str       # plain English, for the business owner


def _quoted(values):
    return ", ".join(f"'{v}'" for v in values)


def build_rules(as_of: datetime):
    """The rules, in priority order: if a row breaks several, the first one is its main reason."""
    now = f"TIMESTAMP '{as_of:%Y-%m-%d %H:%M:%S}'"
    return [
        Rule("NULL_TXN_ID", "txn_id_n is null", "transaction id is missing"),
        Rule("DUPLICATE_TXN_ID", "txn_id_n is not null and dup_rank > 1", "same transaction id seen before"),
        Rule("INVALID_AMOUNT", "amount_n is null", "amount is blank or not a number"),
        Rule("NON_POSITIVE_AMOUNT", "amount_n <= 0", "amount is zero or negative"),
        Rule("INVALID_TIMESTAMP", "txn_ts_t is null", "date/time cannot be read"),
        Rule("FUTURE_TIMESTAMP", f"txn_ts_t > {now}", "transaction is dated in the future"),
        Rule("UNKNOWN_CURRENCY", f"coalesce(currency_n not in ({_quoted(ALLOWED_CURRENCIES)}), true)",
             "currency is not on the approved list"),
        Rule("UNKNOWN_CHANNEL", f"coalesce(channel_n not in ({_quoted(ALLOWED_CHANNELS)}), true)",
             "channel is not on the approved list"),
        Rule("INVALID_DIRECTION", f"coalesce(direction_n not in ({_quoted(ALLOWED_DIRECTIONS)}), true)",
             "direction is not DR or CR"),
        Rule("ORPHAN_ACCOUNT", "not account_exists", "account is not in the accounts file"),
    ]


def build_staging(con):
    """Read the BRONZE tables and add tidy helper columns (suffix _n / _t) next to the raw ones.

    Nothing is deleted or overwritten: the raw columns stay exactly as received.
    Trimming and upper-casing happens here, so ' mpesa ' is fixed rather than rejected.
    """
    con.execute("""
        create or replace temp table stg_txn as
        select t.*,
               nullif(trim(t.txn_id), '')                  as txn_id_n,
               try_cast(t.amount as decimal(18,2))         as amount_n,
               try_cast(t.txn_ts as timestamp)             as txn_ts_t,
               upper(trim(t.currency))                     as currency_n,
               upper(trim(t.channel))                      as channel_n,
               upper(trim(t.direction))                    as direction_n,
               row_number() over (partition by nullif(trim(t.txn_id), '') order by t.row_num) as dup_rank,
               a.account_id is not null                    as account_exists
        from bronze.transactions t
        left join bronze.accounts a on a.account_id = trim(t.account_id)
    """)


def reject_reason_sql(rules):
    """A CASE expression giving each failing row its FIRST failing rule as the reason (NULL = clean row)."""
    whens = " ".join(f"when {r.condition} then '{r.name}'" for r in rules)
    return f"case {whens} end"

def count_failures(con, rules):
    """How many rows break each rule? (A row that breaks two rules is counted under both.)"""
    return [(r.name, con.execute(f"select count(*) from stg_txn where {r.condition}").fetchone()[0]) for r in rules]


def main():
    as_of = datetime.now()
    con = duckdb.connect(str(WAREHOUSE))           # in-memory: nothing is written to disk
    build_staging(con)
    rules = build_rules(as_of)

    total = con.execute("select count(*) from stg_txn").fetchone()[0]
    print(f"{'rule':22} {'rows failing':>12}   meaning")
    for rule, (_, failed) in zip(rules, count_failures(con, rules), strict=True):
        print(f"{rule.name:22} {failed:>12}   {rule.meaning}")

    reject_any = " or ".join(f"({r.condition})" for r in rules)
    bad = con.execute(f"select count(*) from stg_txn where {reject_any}").fetchone()[0]
    print(f"\n{total} rows read: {total - bad} pass every rule, {bad} fail at least one")
    con.close()


if __name__ == "__main__":
    main()