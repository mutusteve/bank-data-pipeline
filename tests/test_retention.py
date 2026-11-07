from datetime import datetime, timedelta

from pipeline.retention import apply_retention


def test_fresh_raw_data_is_kept(bronze_con):
    assert apply_retention(bronze_con, days=90, now=datetime.now()) == 0
    assert bronze_con.execute("select count(*) from bronze.transactions").fetchone()[0] == 16


def test_raw_data_older_than_the_limit_is_deleted(bronze_con):
    later = datetime.now() + timedelta(days=100)         # pretend 100 days have passed
    assert apply_retention(bronze_con, days=90, now=later) == 16
    assert bronze_con.execute("select count(*) from bronze.transactions").fetchone()[0] == 0