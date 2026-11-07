"""RETENTION: delete raw (bronze) rows once they are older than the retention period.

Bronze is the only layer that still contains personal data (phone numbers in free text), so it is the
layer with a time limit. This is the 'storage limitation' principle of the Data Protection Act, 2019:
do not keep personal data longer than you need it. Silver and gold hold no raw personal data.
"""
from datetime import datetime, timedelta

from .config import BRONZE_RETENTION_DAYS


def apply_retention(con, days=BRONZE_RETENTION_DAYS, now=None):
    """Delete bronze transactions loaded more than `days` days ago. Returns how many rows were removed."""
    cutoff = (now or datetime.now()) - timedelta(days=days)
    expired = con.execute("select count(*) from bronze.transactions where ingested_at < ?", [cutoff]).fetchone()[0]
    con.execute("delete from bronze.transactions where ingested_at < ?", [cutoff])
    return expired