"""Shared test setup: a tiny hand-made dataset where every row has a known purpose.

Using a few rows we wrote ourselves (instead of the big generated file) means each test can say exactly
which row should end up where, and a failing test points straight at the broken rule.
"""
import csv
from datetime import datetime

import duckdb
import pytest

from pipeline.gold import build_gold
from pipeline.ingest import load_bronze
from pipeline.transform import build_silver_and_quarantine

AS_OF = datetime(2026, 11, 7, 12, 0, 0)    # a fixed "now", so tests give the same answer every day

TXN_HEADER = ["txn_id", "account_id", "txn_ts", "amount", "currency", "direction", "channel", "merchant", "narrative"]

TRANSACTIONS = [
    # ---- clean rows
    ["T1", "ACC1", "2026-11-05 10:00:00", "1000.00", "KES", "DR", "MPESA", "Naivas", "M-Pesa payment to 0722111222"],
    ["T2", "ACC1", "2026-11-05 11:00:00", "500.00", "KES", "CR", "CARD", "Naivas", "CARD payment Naivas"],
    ["T3", "ACC2", "2026-11-06 09:00:00", "250.50", "USD", "DR", "ONLINE", "Uber", "ONLINE payment Uber"],
    # ---- messy but fixable (wrong case and spaces): should be repaired, not rejected
    ["T4", "ACC2", "2026-11-06 10:00:00", "100.00", "KES", "DR", " mpesa ", "  naivas", "MPESA payment"],
    # ---- bad rows: each one breaks exactly one rule
    ["T1", "ACC1", "2026-11-05 10:00:00", "1000.00", "KES", "DR", "MPESA", "Naivas", "same id as the first row"],
    ["", "ACC1", "2026-11-05 12:00:00", "10.00", "KES", "DR", "ATM", "Uber", "missing id"],
    ["T6", "ACC1", "2026-11-05 12:00:00", "", "KES", "DR", "ATM", "Uber", "blank amount"],
    ["T7", "ACC1", "2026-11-05 12:00:00", "N/A", "KES", "DR", "ATM", "Uber", "amount not a number"],
    ["T8", "ACC1", "2026-11-05 12:00:00", "-5.00", "KES", "DR", "ATM", "Uber", "negative amount"],
    ["T9", "ACC1", "2026-11-05 12:00:00", "0.00", "KES", "DR", "ATM", "Uber", "zero amount"],
    ["T10", "ACC1", "2026-11-05 12:00:00", "10.00", "XXX", "DR", "ATM", "Uber", "unknown currency"],
    ["T11", "ACC1", "2026-11-05 12:00:00", "10.00", "KES", "DR", "FAX", "Uber", "unknown channel"],
    ["T12", "ACC1", "2026-11-05 12:00:00", "10.00", "KES", "??", "ATM", "Uber", "bad direction"],
    ["T13", "ACC9", "2026-11-05 12:00:00", "10.00", "KES", "DR", "ATM", "Uber", "account does not exist"],
    ["T14", "ACC1", "2026-12-31 10:00:00", "10.00", "KES", "DR", "ATM", "Uber", "dated in the future"],
    ["T15", "ACC1", "2026-13-45 99:99:99", "10.00", "KES", "DR", "ATM", "Uber", "impossible date"],
]
ACCOUNTS = [["account_id", "status"], ["ACC1", "ACTIVE"], ["ACC2", "ACTIVE"]]


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


@pytest.fixture()
def raw_dir(tmp_path):
    """A temporary folder holding the two small CSV files (deleted automatically after each test)."""
    write_csv(tmp_path / "transactions.csv", [TXN_HEADER, *TRANSACTIONS])
    write_csv(tmp_path / "accounts.csv", ACCOUNTS)
    return tmp_path


@pytest.fixture()
def bronze_con(raw_dir):
    """An empty in-memory warehouse with only the raw (bronze) layer loaded."""
    con = duckdb.connect()
    load_bronze(con, raw_dir)
    yield con
    con.close()


@pytest.fixture()
def con(bronze_con):
    """A warehouse with bronze, silver, quarantine and gold all built."""
    # 12 of the 16 rows are bad on purpose, so the safety-stop limit is switched off for this fixture.
    build_silver_and_quarantine(bronze_con, AS_OF, max_quarantine_pct=100)
    build_gold(bronze_con, AS_OF)
    return bronze_con