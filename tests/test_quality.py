import pytest

from pipeline.quality import DataQualityError
from pipeline.transform import build_silver_and_quarantine
from tests.conftest import AS_OF

# Each bad row must be rejected for exactly the reason it was built to trigger.
EXPECTED_REASONS = {
    "T6": "INVALID_AMOUNT",
    "T7": "INVALID_AMOUNT",
    "T8": "NON_POSITIVE_AMOUNT",
    "T9": "NON_POSITIVE_AMOUNT",
    "T10": "UNKNOWN_CURRENCY",
    "T11": "UNKNOWN_CHANNEL",
    "T12": "INVALID_DIRECTION",
    "T13": "ORPHAN_ACCOUNT",
    "T14": "FUTURE_TIMESTAMP",
    "T15": "INVALID_TIMESTAMP",
}


@pytest.mark.parametrize("txn_id, reason", EXPECTED_REASONS.items())
def test_bad_row_is_rejected_for_the_right_reason(con, txn_id, reason):
    found = con.execute("select reject_reason from quarantine.transactions where txn_id = ?", [txn_id]).fetchall()
    assert found == [(reason,)]


def test_missing_id_and_duplicate_id_are_rejected(con):
    # DuckDB reads an empty CSV cell as NULL (not as an empty string), so the missing id is NULL.
    missing = con.execute("select reject_reason from quarantine.transactions where txn_id is null").fetchall()
    assert missing == [("NULL_TXN_ID",)]
    repeat = con.execute("select reject_reason from quarantine.transactions where txn_id = 'T1'").fetchall()
    assert repeat == [("DUPLICATE_TXN_ID",)]


def test_only_clean_rows_reach_silver(con):
    ids = {r[0] for r in con.execute("select txn_id from silver.transactions").fetchall()}
    assert ids == {"T1", "T2", "T3", "T4"}        # the first copy of T1 is kept, the repeat is rejected


def test_messy_but_valid_row_is_repaired_not_rejected(con):
    channel, merchant = con.execute("select channel, merchant from silver.transactions where txn_id = 'T4'").fetchone()
    assert channel == "MPESA"          # ' mpesa ' was trimmed and upper-cased
    assert merchant == "Naivas"        # '  naivas' was trimmed and matched to the usual spelling


def test_no_row_is_lost_between_bronze_and_silver_plus_quarantine(con):
    count = lambda t: con.execute(f"select count(*) from {t}").fetchone()[0]   # noqa: E731
    assert count("bronze.transactions") == count("silver.transactions") + count("quarantine.transactions")


def test_safety_stop_blocks_a_badly_broken_batch_and_publishes_nothing(bronze_con):
    # With the normal 10% limit, this dataset (75% bad) must be refused.
    with pytest.raises(DataQualityError):
        build_silver_and_quarantine(bronze_con, AS_OF, max_quarantine_pct=10)
    tables = {r[0] for r in bronze_con.execute(
        "select table_schema || '.' || table_name from information_schema.tables").fetchall()}
    assert "silver.transactions" not in tables
    assert "quarantine.transactions" not in tables