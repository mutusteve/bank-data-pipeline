import duckdb
import pytest

from pipeline.unstructured import HashingEmbedder, chunk_text, ingest_documents, load_text, search

POLICY = ("Loan policy. A credit reference bureau check is mandatory before any loan is approved. "
          "Customers with active defaults are declined. Repayment is deducted on the salary date.")
TRANSCRIPT = ("Call transcript. Agent: please confirm your ID No 23456789 and phone 0722111222. "
              "Customer: my email is jane@example.com. Agent: failed transfers are reversed in two days.")


@pytest.fixture()
def docs_dir(tmp_path):
    (tmp_path / "loan_policy.txt").write_text(POLICY, encoding="utf-8")
    (tmp_path / "call_0042.txt").write_text(TRANSCRIPT, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def docs_con(docs_dir):
    con = duckdb.connect()
    ingest_documents(con, docs_dir)
    yield con
    con.close()


def test_chunks_overlap_and_cover_the_whole_text():
    text = " ".join(f"w{i}" for i in range(100))
    chunks = chunk_text(text, words=30, overlap=10)
    assert chunks[0].split()[-10:] == chunks[1].split()[:10]        # neighbours share 10 words
    assert set(" ".join(chunks).split()) == set(text.split())       # no word is lost
    assert chunk_text("", words=30, overlap=10) == []


def test_embedder_is_repeatable_and_has_length_one():
    embedder = HashingEmbedder(dim=64)
    first = embedder.embed(["loan arrears policy"])[0]
    assert first == embedder.embed(["loan arrears policy"])[0]
    assert abs(sum(x * x for x in first) - 1.0) < 1e-9


def test_audio_without_a_speech_engine_fails_loudly_not_silently(tmp_path):
    audio = tmp_path / "call_7.wav"
    audio.write_bytes(b"RIFF")
    with pytest.raises(NotImplementedError):
        load_text(audio)


def test_personal_data_is_removed_before_anything_is_stored(docs_con):
    stored = " ".join(r[0] for r in docs_con.execute("select text from genai.chunks").fetchall())
    for secret in ("23456789", "0722111222", "jane@example.com"):
        assert secret not in stored
    assert "[ID]" in stored and "[PHONE]" in stored and "[EMAIL]" in stored
    redactions = docs_con.execute("select n_redactions from genai.documents where doc_id = 'call_0042'").fetchone()[0]
    assert redactions == 3


def test_transcripts_are_labelled_as_such(docs_con):
    kinds = dict(docs_con.execute("select doc_id, doc_type from genai.documents").fetchall())
    assert kinds == {"loan_policy": "document", "call_0042": "voice_transcript"}


def test_search_returns_the_right_document(docs_con):
    assert search(docs_con, "credit bureau check before a loan", k=1)[0]["source_file"] == "loan_policy.txt"
    assert search(docs_con, "failed transfer reversed", k=1)[0]["source_file"] == "call_0042.txt"


def test_unchanged_documents_are_skipped_and_changed_ones_replaced(docs_con, docs_dir):
    again = ingest_documents(docs_con, docs_dir)
    assert (again["processed"], again["skipped"]) == (0, 2)           # nothing changed: nothing to do

    (docs_dir / "loan_policy.txt").write_text("Overdraft policy: the limit is ten thousand shillings.", encoding="utf-8")
    changed = ingest_documents(docs_con, docs_dir)
    assert (changed["processed"], changed["skipped"]) == (1, 1)
    texts = [r[0] for r in docs_con.execute("select text from genai.chunks where doc_id = 'loan_policy'").fetchall()]
    assert texts == ["Overdraft policy: the limit is ten thousand shillings."]    # old chunks replaced, not added to