![ci](https://github.com/mutusteve/bank-data-pipeline/actions/workflows/ci.yml/badge.svg)

# Bank Data Pipeline

A small, runnable **ELT pipeline** that turns messy bank transaction files into clean, validated, privacy-safe data products, and prepares documents and call transcripts for GenAI search.

Everything runs locally with **Python and DuckDB**, on **entirely synthetic data**. No real customer data is used.

## What it demonstrates

- **Batch ingestion** of raw files into a layered warehouse (bronze, silver, gold)
- **Data quality controls**: 10 rules, with rejected rows kept in a quarantine table together with the reason
- **Reconciliation**: 7 checks proving no rows or money were lost between source, bronze, silver and gold
- **Privacy by design**: personal data is removed before it leaves the raw layer, and raw data expires after 90 days
- **Reliability**: a safety stop that refuses to publish a badly broken batch, repeatable runs, a log of every stage
- **Unstructured data for GenAI**: documents and call transcripts are redacted, chunked, embedded and searchable
- **Engineering practice**: 41 automated tests, source control, and CI that runs the tests and the whole pipeline on every push

## How it works

```
 raw CSV files            BRONZE                 SILVER                   GOLD
 -----------------        ------------------     --------------------     -----------------------
 transactions.csv  --->   exactly as received    typed, validated,        daily_channel_summary
 accounts.csv             all text, plus audit   de-duplicated,           daily_account_summary
                          columns                personal data masked     account_features
                                                          |
                                                          +--->  QUARANTINE  (rejected rows + reason)

 docs/*.txt  --->  remove personal data --> chunk --> vectors --> genai.chunks  (similarity search)

 Alongside: ops.pipeline_runs (every stage logged)  |  ops.reconciliation (every check logged)
```

**ELT, not ETL:** data is loaded untouched first, and all transformation happens inside the warehouse in SQL. The raw layer can always be replayed.

One command runs the stages in order, and each is logged:
`ingest -> transform -> gold -> reconcile -> documents -> retention`

## Quick start

Needs Python 3.10 or newer. On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pytest

python scripts/generate_data.py     # fake transactions with deliberate defects
python scripts/generate_docs.py     # fake policy documents and a call transcript
python -m pipeline.run              # run the whole pipeline
python -m pytest -q                 # 41 tests
```

On Mac or Linux, activate with `source .venv/bin/activate`.

Example output:

```
  ingest       SUCCESS  rows=5206  0.05s
  transform    SUCCESS  rows=5050  0.13s
  gold         SUCCESS  rows=2177  0.02s
  reconcile    SUCCESS  rows=7     0.02s
  documents    SUCCESS  rows=11    0.04s
  retention    SUCCESS  rows=0     0.00s
```

Try the GenAI search with `python -m pipeline.unstructured`.

## The data

The generator creates 5,206 transactions in which about 4% of rows are broken on purpose, so the controls have real work to do:

| Problem injected | Handled by |
|---|---|
| Duplicate and missing transaction ids | rejected |
| Blank, non-numeric, zero or negative amounts | rejected |
| Unknown currency, channel or direction | rejected |
| Account that does not exist | rejected |
| Future-dated or impossible timestamps | rejected |
| Wrong case and stray spaces (`" mpesa "`) | **repaired**, not rejected |
| Phone numbers inside free text | masked |

Result: **5,050 clean rows** go to silver and **156 rejected rows** go to quarantine, each with its reason. 5,206 = 5,050 + 156, and the pipeline proves it on every run.

## Data quality and reconciliation

Rules live in `pipeline/quality.py` as data (a name, a SQL condition and a plain-English meaning), and the same list drives both the counts and the quarantine. They cover completeness, uniqueness, validity, timeliness and referential integrity.

Reconciliation (`pipeline/reconcile.py`) compares an expected number with an actual number for **both row counts and money totals** at each hand-off: source to bronze, bronze to silver plus quarantine, and silver to gold. The source totals are recomputed from the file with plain Python, so the check does not depend on the tool that did the load. Results are stored in `ops.reconciliation` as an audit trail.

**Safety stop:** if more than 10% of a batch is rejected, the source is probably broken, so the run stops *before* publishing and consumers keep the last good data.

## Privacy and security

Designed around the principles of Kenya's Data Protection Act, 2019, mainly **data minimisation** and **storage limitation**:

- Phone numbers, emails, labelled ID numbers and long account-style numbers are replaced with tags (`[PHONE]`, `[EMAIL]`, `[ID]`, `[NUMBER]`) before data leaves bronze, and before any text is stored for search.
- Bronze is the only layer that keeps the original text, and it has a 90-day retention limit.
- Gold tables never mix currencies, and hold no personal data beyond the account id.

## Project structure

```
pipeline/    config, ingest, quality, transform, gold, reconcile,
             privacy, retention, observability, unstructured, run
scripts/     generate_data.py, generate_docs.py   (synthetic source data)
tests/       41 tests on a small hand-made dataset
notebooks/   01_profile_raw_data.ipynb            (profiling before any cleaning)
data/        raw/ (inputs, not committed), processed/ (warehouse, not committed)
.github/     workflows/ci.yml                     (lint, tests, full run)
```

## Testing and CI

- Tests use a tiny dataset where every row has a known purpose, so a failing test names the rule that broke. They check that each rejection reason is right, that nothing is lost between layers, that the safety stop publishes nothing, that reconciliation catches a dropped row and a changed source file, that no phone number survives downstream, and that retention deletes only expired data.
- GitHub Actions runs lint, the tests, and the full pipeline from a clean machine on every push. The run command exits with code 1 on any failure, which is how CI knows.

## Limitations

This is a learning and portfolio project, and it is deliberately small.

- **Batch only.** There is no streaming or real-time path.
- **Single machine.** DuckDB on about 5,000 rows, not a distributed platform at scale.
- **Full reload.** Bronze is rebuilt from the files on each run. A production pipeline would load incrementally and skip files it has already seen.
- **Reconciliation runs after the tables are built.** A mismatch is caught and fails the run, but production would build into a staging area and only swap it in once the checks pass.
- **Placeholder embedder.** The vector step uses a simple word-counting embedder that finds the right document but not always the best passage. A real embedding model and vector database would replace it.
- **Voice** is supported only as transcripts. The speech-to-text step is a plug-in point.
- **Redaction uses patterns.** It catches formatted identifiers but cannot detect names in free text.
- **No access control or encryption is demonstrated.**

## What I would do next

1. Incremental loading with a record of which files were processed.
2. Stage-then-swap publishing, so bad data is never visible.
3. A streaming ingestion path for transaction events.
4. A real embedding model and vector store, with access rules on the chunks.
5. Role-based access to each layer, and encryption of stored data.
6. A dashboard over `ops.pipeline_runs` and `ops.reconciliation`.