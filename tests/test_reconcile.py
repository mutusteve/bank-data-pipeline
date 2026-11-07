from pipeline.reconcile import run_checks


def test_all_checks_match_on_a_correct_run(con, raw_dir):
    results = run_checks(con, raw_dir)
    assert len(results) == 7
    assert all(status == "MATCH" for _, _, _, status in results)


def test_reconciliation_catches_a_lost_row(con, raw_dir):
    con.execute("delete from silver.transactions where txn_id = 'T1'")      # simulate a bug that drops a row
    failed = [name for name, _, _, status in run_checks(con, raw_dir) if status == "MISMATCH"]
    assert "bronze_rows = silver + quarantine rows" in failed


def test_reconciliation_catches_a_changed_source_file(con, raw_dir):
    with open(raw_dir / "transactions.csv", "a", encoding="utf-8") as f:    # the source now has one extra row
        f.write("T99,ACC1,2026-11-05 10:00:00,5.00,KES,DR,ATM,Uber,late row\n")
    failed = [name for name, _, _, status in run_checks(con, raw_dir) if status == "MISMATCH"]
    assert "source_rows = bronze_rows" in failed