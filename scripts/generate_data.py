"""Run from the project folder:   python scripts/generate_data.py
Creates:  data/raw/transactions.csv   and   data/raw/accounts.csv
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)  # same seed -> exactly the same data every time you run it

OUT = Path(__file__).resolve().parent.parent / "data" / "raw"
N_ROWS = 5000
N_ACCOUNTS = 300

CHANNELS = ["MPESA", "ATM", "BRANCH", "CARD", "ONLINE"]
MERCHANTS = ["Naivas", "Quickmart", "Java House", "KPLC Prepaid", "Safaricom Airtime", "Uber", "Jumia"]
COLUMNS = ["txn_id", "account_id", "txn_ts", "amount", "currency", "direction", "channel", "merchant", "narrative"]

accounts = [f"ACC{i:07d}" for i in range(1, N_ACCOUNTS + 1)]


def make_row(i):
    """One clean, valid transaction."""
    when = datetime(2026, 11, 1) + timedelta(seconds=random.randint(0, 5 * 86400 - 1))
    channel = random.choices(CHANNELS, [40, 15, 5, 25, 15])[0]
    merchant = random.choice(MERCHANTS)
    # about 8% of narratives contain a phone number: personal data we must protect later
    narrative = f"M-Pesa payment to 07{random.randint(10, 99)}{random.randint(100000, 999999)}" \
        if random.random() < 0.08 else f"{channel} payment {merchant}"
    return {
        "txn_id": f"T{i:09d}",
        "account_id": random.choice(accounts),
        "txn_ts": when.strftime("%Y-%m-%d %H:%M:%S"),
        "amount": f"{random.lognormvariate(7.2, 1.0):.2f}",   # mostly small, a few large
        "currency": random.choices(["KES", "USD", "EUR"], [92, 6, 2])[0],
        "direction": random.choice(["DR", "CR"]),
        "channel": channel,
        "merchant": merchant,
        "narrative": narrative,
    }


good = [make_row(i) for i in range(1, N_ROWS + 1)]
rows = list(good)


def break_some(count, **changes):
    """Copy `count` good rows, damage them with `changes`, and give each a new id."""
    for n in range(count):
        row = dict(random.choice(good))
        row["txn_id"] = f"T9{len(rows):08d}"
        row.update(changes)
        rows.append(row)


# --- problems that must be REJECTED (quarantined) ---
for _ in range(40):                       # exact duplicates (same txn_id appears twice)
    rows.append(dict(random.choice(good)))
break_some(15, amount="")                 # missing amount
break_some(10, amount="N/A")              # amount is not a number
break_some(15, amount="-250.00")          # negative amount
break_some(5, amount="0.00")              # zero amount
break_some(10, currency="XXX")            # unknown currency
break_some(10, channel="FAX")             # unknown channel
break_some(10, direction="??")            # direction must be DR or CR
break_some(15, account_id="ACC9999999")   # account that does not exist
break_some(10, txn_ts="2026-12-31 10:00:00")   # date in the future
break_some(8, txn_ts="2026-13-45 99:99:99")    # impossible date
break_some(8, txn_id="")                  # missing transaction id

# --- problems that can be FIXED by cleaning (not rejected) ---
break_some(30, channel=" mpesa ")         # wrong case and extra spaces
break_some(20, merchant="  naivas")       # extra spaces, wrong case

random.shuffle(rows)  # mix the bad rows in so they are not grouped together

OUT.mkdir(parents=True, exist_ok=True)
with open(OUT / "transactions.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)

with open(OUT / "accounts.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["account_id", "status"])
    writer.writerows([[a, random.choices(["ACTIVE", "DORMANT"], [92, 8])[0]] for a in accounts])

print(f"Wrote {len(rows)} transactions ({len(rows) - N_ROWS} extra bad/messy rows) to {OUT}")