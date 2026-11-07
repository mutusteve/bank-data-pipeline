"""Project settings: folder locations and the business rules for what counts as a VALID value.

Keeping these in one place means a rule change (e.g. a new allowed currency) is a one-line edit here,
not a hunt through the code.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
WAREHOUSE = PROCESSED_DIR / "warehouse.duckdb"

# Valid values, agreed with the business owners of the data
ALLOWED_CURRENCIES = ("KES", "USD", "EUR", "UGX", "TZS")
ALLOWED_CHANNELS = ("MPESA", "ATM", "BRANCH", "CARD", "ONLINE")
ALLOWED_DIRECTIONS = ("DR", "CR")   # DR = debit (money out), CR = credit (money in)