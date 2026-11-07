import pytest

from pipeline.privacy import redact_pii


@pytest.mark.parametrize("text, expected", [
    ("pay 0722111222 now", "pay [PHONE] now"),
    ("call +254712345678", "call [PHONE]"),
    ("mail jane@example.com", "mail [EMAIL]"),
    ("ref 0123456789012 done", "ref [NUMBER] done"),
    ("please confirm your ID No 23456789 today", "please confirm your [ID] today"),
    ("paid 23456789 shillings", "paid 23456789 shillings"),          # an unlabelled number is not an ID
    ("CARD payment Naivas 2500 KES", "CARD payment Naivas 2500 KES"),   # nothing personal: unchanged
    (None, None),
])
def test_redact_pii(text, expected):
    assert redact_pii(text) == expected


def test_phone_numbers_are_masked_in_silver_but_kept_in_bronze(con):
    silver = con.execute("select narrative from silver.transactions where txn_id = 'T1'").fetchone()[0]
    assert silver == "M-Pesa payment to [PHONE]"
    raw = con.execute("select narrative from bronze.transactions where txn_id = 'T1' limit 1").fetchone()[0]
    assert "0722111222" in raw          # bronze is the untouched raw copy, covered by the retention policy


def test_no_phone_number_survives_anywhere_downstream(con):
    for table in ("silver.transactions", "quarantine.transactions"):
        leaks = con.execute(f"select count(*) from {table} where regexp_matches(narrative, '07[0-9]{{8}}')").fetchone()[0]
        assert leaks == 0, table