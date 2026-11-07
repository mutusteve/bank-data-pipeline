def test_gold_totals_add_up_to_silver(con):
    silver_rows, silver_amount = con.execute("select count(*), sum(amount) from silver.transactions").fetchone()
    gold_rows, gold_amount = con.execute("select sum(txn_count), sum(total_amount) from gold.daily_channel_summary").fetchone()
    assert (silver_rows, silver_amount) == (gold_rows, gold_amount)


def test_daily_channel_summary_values(con):
    debit, credit = con.execute("""select debit_total, credit_total from gold.daily_channel_summary
                                   where txn_date = DATE '2026-11-05' and channel = 'MPESA' and currency = 'KES'""").fetchone()
    assert (float(debit), float(credit)) == (1000.00, 0.0)


def test_currencies_are_never_mixed(con):
    currencies = {r[0] for r in con.execute("select distinct currency from gold.daily_channel_summary").fetchall()}
    assert currencies == {"KES", "USD"}            # kept as separate rows, never summed together


def test_account_features_use_kes_only(con):
    # ACC2 has one USD and one KES transaction; only the KES one may count.
    txn_count = con.execute("select txn_count from gold.account_features where account_id = 'ACC2'").fetchone()[0]
    assert txn_count == 1