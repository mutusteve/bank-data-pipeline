"""Project settings: folder locations and the business rules for what counts as a VALID value.

Keeping these in one place means a rule change (e.g. a new allowed currency) is a one-line edit here,
not a hunt through the code.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DOCS_DIR = RAW_DIR / "docs"
PROCESSED_DIR = ROOT / "data" / "processed"
WAREHOUSE = PROCESSED_DIR / "warehouse.duckdb"

# Valid values, agreed with the business owners of the data
ALLOWED_CURRENCIES = ("KES", "USD", "EUR", "UGX", "TZS")
ALLOWED_CHANNELS = ("MPESA", "ATM", "BRANCH", "CARD", "ONLINE")
ALLOWED_DIRECTIONS = ("DR", "CR")   # DR = debit (money out), CR = credit (money in)

# Safety stop: if more than this % of a batch is rejected, something is wrong upstream - do not publish
MAX_QUARANTINE_PCT = 10.0

# Storage limitation: the raw layer holds personal data, so it is only kept for this many days
BRONZE_RETENTION_DAYS = 90

# Documents for GenAI: how to cut text into pieces and how long each vector is
CHUNK_WORDS = 50        # words per chunk (small here because our sample documents are short)
CHUNK_OVERLAP = 10      # words shared between neighbouring chunks, so a sentence cut in half is not lost
EMBEDDING_DIM = 256     # numbers per vector