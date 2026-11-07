"""PRIVACY: remove personal data from free text before it leaves the raw (bronze) layer.

The `narrative` column is free text typed by systems and people, and it can contain phone numbers,
emails and account numbers. Under the Data Protection Act, 2019 we should only keep personal data
we actually need (data minimisation). Analytics does not need anyone's phone number, so silver,
quarantine and gold get a redacted version; only bronze keeps the original, and bronze is short-lived.

We register the Python function inside DuckDB so the cleaning stays in SQL:  redact_pii(narrative)
"""
import re

try:                                    # DuckDB 2.x
    from duckdb.sqltypes import VARCHAR
except ImportError:                     # DuckDB 1.x
    from duckdb.typing import VARCHAR

# Kenyan mobile numbers: 07xx / 01xx / 2547xx / +2547xx
_PHONE = re.compile(r"(?<!\d)(?:\+?254|0)[17]\d{8}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_NUMBER = re.compile(r"(?<!\d)\d{10,16}(?!\d)")     # bank / card style numbers


def redact_pii(text):
    """Replace phones, emails and long numbers with a tag. Order matters: phones before long numbers."""
    if text is None:
        return None
    text = _EMAIL.sub("[EMAIL]", text)
    text = _PHONE.sub("[PHONE]", text)
    return _LONG_NUMBER.sub("[NUMBER]", text)


def register_privacy_functions(con):
    """Make redact_pii() available inside SQL queries on this connection."""
    # DuckDB refuses to register a function while an earlier query's result is only half-read
    # (e.g. after .fetchone()). Running one tiny query to the end clears it.
    con.execute("select 1").fetchall()
    try:
        con.remove_function("redact_pii")     # safe to call more than once
    except Exception:                         # not registered yet
        pass
    con.create_function("redact_pii", redact_pii, [VARCHAR], VARCHAR)