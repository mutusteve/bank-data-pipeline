"""UNSTRUCTURED DATA -> SEARCHABLE VECTORS, to feed GenAI applications (retrieval-augmented generation).

For each document:   read -> remove personal data -> cut into chunks -> turn each chunk into a vector -> store

Why each step:
  * remove personal data FIRST, so phone numbers and IDs never end up in the vector store or in a prompt;
  * chunk, because a model can only read a small piece at a time and search works better on focused pieces;
  * vectors, so we can search by MEANING (closest vector) and not only by exact words.

A document is re-processed only if its text changed (we compare a hash), so running twice does no extra work.
Voice: audio is turned into text by a speech-to-text engine first. That engine is a plug-in point here
(`transcribe`); until one is configured we accept transcripts as .txt files.

Run:   python -m pipeline.unstructured
"""
import hashlib
import math
import re
from datetime import datetime

import duckdb

from .config import CHUNK_OVERLAP, CHUNK_WORDS, DOCS_DIR, EMBEDDING_DIM, WAREHOUSE
from .privacy import TAGS, redact_pii

TEXT_SUFFIXES = {".txt", ".md"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a"}
STOP_WORDS = set("a an and are as at be by for from has have how i in is it of on or that the this to was we "
                 "what when which with you your".split())


class HashingEmbedder:
    """A simple, dependable stand-in for a real embedding model.

    It counts words and word pairs into a fixed-length vector, so texts that share words get similar
    vectors. It needs no download and always gives the same answer, which suits learning and testing.
    In production you would swap this for a real embedding model (it only needs an .embed() method).
    """

    def __init__(self, dim=EMBEDDING_DIM):
        self.dim = dim

    @staticmethod
    def _normalise(word):
        """Crude stemming so 'customer's', 'customers' and 'customer' count as the same word."""
        word = word.replace("'s", "").strip("'")
        if len(word) > 4 and word.endswith("ies"):
            return word[:-3] + "y"
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word

    def _tokens(self, text):
        words = [self._normalise(w) for w in re.findall(r"[a-z0-9']+", text.lower())]
        words = [w for w in words if w and w not in STOP_WORDS]
        return words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]   # word pairs too

    def embed(self, texts):
        vectors = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in self._tokens(text):
                h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
                vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0     # spread each word over the vector
            length = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / length for v in vec])                    # scale to length 1
        return vectors


def chunk_text(text, words=CHUNK_WORDS, overlap=CHUNK_OVERLAP):
    """Cut text into pieces of `words` words, each sharing `overlap` words with the previous piece."""
    tokens = text.split()
    step = max(words - overlap, 1)
    return [" ".join(tokens[i:i + words]) for i in range(0, len(tokens), step) if tokens[i:i + words]]


def transcribe(path):
    """Plug-in point for speech-to-text (for example Whisper or a managed speech service)."""
    raise NotImplementedError(f"No speech-to-text engine is configured for {path.name}. "
                              "Provide a transcript as a .txt file, or plug an engine in here.")


def load_text(path):
    if path.suffix.lower() in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8")
    if path.suffix.lower() in AUDIO_SUFFIXES:
        return transcribe(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def create_tables(con):
    con.execute("create schema if not exists genai")
    con.execute("""create table if not exists genai.documents (
                       doc_id varchar, source_file varchar, doc_type varchar, text_hash varchar,
                       n_chunks integer, n_redactions integer, ingested_at timestamp)""")
    con.execute("""create table if not exists genai.chunks (
                       chunk_id varchar, doc_id varchar, chunk_no integer, text varchar,
                       n_words integer, embedding FLOAT[])""")


def ingest_documents(con, docs_dir=DOCS_DIR, embedder=None):
    """Process every new or changed document. Returns a small summary of what happened."""
    embedder = embedder or HashingEmbedder()
    create_tables(con)
    processed = skipped = chunks_written = 0

    files = sorted(p for p in docs_dir.glob("*") if p.suffix.lower() in TEXT_SUFFIXES | AUDIO_SUFFIXES)
    for path in files:
        raw = load_text(path)
        text_hash = hashlib.sha256(raw.encode()).hexdigest()
        doc_id = path.stem

        known = con.execute("select text_hash from genai.documents where doc_id = ?", [doc_id]).fetchall()
        if known and known[0][0] == text_hash:
            skipped += 1                                   # same text as last time: nothing to do
            continue

        clean = redact_pii(raw)                            # 1. personal data out, before anything is stored
        pieces = chunk_text(clean)                         # 2. cut
        vectors = embedder.embed(pieces)                   # 3. vectors
        doc_type = "voice_transcript" if path.stem.startswith("call_") else "document"

        con.execute("begin")                               # replace the old version of this document in one go
        try:
            con.execute("delete from genai.chunks where doc_id = ?", [doc_id])
            con.execute("delete from genai.documents where doc_id = ?", [doc_id])
            con.execute("insert into genai.documents values (?,?,?,?,?,?,?)",
                        [doc_id, path.name, doc_type, text_hash, len(pieces),
                         sum(clean.count(tag) for tag in TAGS), datetime.now()])
            for i, (piece, vector) in enumerate(zip(pieces, vectors, strict=True)):
                con.execute("insert into genai.chunks values (?,?,?,?,?,?)",
                            [f"{doc_id}#{i}", doc_id, i, piece, len(piece.split()), vector])
            con.execute("commit")
        except Exception:
            con.execute("rollback")
            raise
        processed += 1
        chunks_written += len(pieces)

    return {"processed": processed, "skipped": skipped, "chunks": chunks_written}


def search(con, question, k=3, embedder=None):
    """Find the k chunks whose meaning is closest to the question. This is the 'retrieval' in RAG."""
    embedder = embedder or HashingEmbedder()
    vector = embedder.embed([question])[0]
    rows = con.execute("""
        select c.chunk_id, d.source_file, c.text,
               list_cosine_similarity(c.embedding, ?::FLOAT[]) as score
        from genai.chunks c join genai.documents d using (doc_id)
        order by score desc limit ?
    """, [vector, k]).fetchall()
    return [{"chunk_id": r[0], "source_file": r[1], "text": r[2], "score": round(r[3], 3)} for r in rows]


def main():
    con = duckdb.connect(str(WAREHOUSE))
    print(ingest_documents(con))
    for question in ["how do we verify customer identity", "failed mpesa transfer reversal",
                     "what happens when a loan repayment is missed"]:
        best = search(con, question, k=1)[0]
        print(f"\nQ: {question}\n   -> {best['source_file']} (score {best['score']}): {best['text'][:90]}...")
    con.close()


if __name__ == "__main__":
    main()