"""spec.md checks 7 and 8: saved lessons are found later and labelled; scanned files are reported, not marked indexed.
The embedding model is replaced by a tiny word-hash embedder, so these tests need no download."""
import math
import re
import zlib

import pytest

from agent import docs, settings
from rag import core


def fake_embed(texts, prefix):
    out = []
    for t in texts:
        v = [0.0] * 128
        for w in re.findall(r"\w+", t.lower()):
            v[zlib.crc32(w.encode()) % 128] += 1
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


@pytest.fixture
def kb(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "KNOWLEDGE", tmp_path / "knowledge")
    monkeypatch.setattr(core, "INDEX_DIR", tmp_path / "index")
    monkeypatch.setattr(core, "MANIFEST", tmp_path / "index" / "manifest.json")
    monkeypatch.setattr(core, "_collection", None)
    monkeypatch.setattr(core, "_embed", fake_embed)
    core.KNOWLEDGE.mkdir()
    return core.KNOWLEDGE


def blank_pdf(path):
    from pypdf import PdfWriter

    w = PdfWriter(); w.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        w.write(f)


# --- chunking and extraction ----------------------------------------------------------------------
def test_chunks_overlap_and_cover_the_text():
    words = [f"w{i}" for i in range(600)]
    chunks = list(core.chunk(" ".join(words)))
    s = settings.get()
    assert all(len(c.split()) <= s.chunk_words for c in chunks)
    assert chunks[0].split()[-s.overlap_words:] == chunks[1].split()[:s.overlap_words]
    assert set(" ".join(chunks).split()) == set(words)


def test_empty_text_gives_no_chunks():
    assert list(core.chunk("   \n ")) == []


def test_extract_reads_word_powerpoint_excel_and_text(tmp_path):
    docs.write_docx(tmp_path / "a.docx", "Lesson", [{"type": "paragraph", "text": "numeric data"}])
    docs.write_pptx(tmp_path / "a.pptx", [{"title": "Slide one", "bullets": ["categorical data"]}])
    docs.write_xlsx(tmp_path / "a.xlsx", [{"name": "Sheet", "rows": [["age"], [15]]}])
    (tmp_path / "a.md").write_text("plain notes")
    assert "numeric data" in core.extract(tmp_path / "a.docx")[0][1]
    assert core.extract(tmp_path / "a.pptx")[0][0] == "slide 1" and "categorical data" in core.extract(tmp_path / "a.pptx")[0][1]
    assert core.extract(tmp_path / "a.xlsx")[0][0] == "sheet Sheet" and "age" in core.extract(tmp_path / "a.xlsx")[0][1]
    assert core.extract(tmp_path / "a.md") == [("file", "plain notes")]


# --- the index lifecycle ---------------------------------------------------------------------------
def test_reindex_adds_skips_updates_and_removes(kb):
    (kb / "a.md").write_text("numeric data are numbers")
    (kb / "b.md").write_text("categorical data are labels")
    assert core.reindex().startswith("added 2, updated 0, removed 0")
    assert core.reindex().startswith("added 0, updated 0, removed 0")        # unchanged files are skipped
    (kb / "a.md").write_text("numeric data are numbers such as age")
    assert core.reindex().startswith("added 0, updated 1, removed 0")
    (kb / "b.md").unlink()
    assert core.reindex().startswith("added 0, updated 0, removed 1")
    assert "categorical" not in core.search_knowledge("categorical labels")


def test_search_ranks_the_matching_file_first_and_cites_file_and_location(kb):
    docs.write_pptx(kb / "slides.pptx", [{"title": "SQL", "bullets": ["select where order by"]}])
    (kb / "other.md").write_text("pivot tables summarise numeric data")
    core.reindex()
    out = core.search_knowledge("select where order", k=2)
    assert out.startswith("[slides.pptx | slide 1 | teacher material")


def test_search_on_an_empty_knowledge_base_says_so(kb):
    assert "Knowledge base is empty" in core.search_knowledge("anything")


# --- check 7: generated lessons are found later, labelled, and filterable --------------------------
def test_generated_files_are_labelled_and_the_source_filter_works(kb):
    (kb / "notes.md").write_text("sorting data in excel is done with the sort dialog")
    docs.write_docx(kb / "generated" / "2026-10-17-sorting" / "plan.docx", "Sorting",
                    [{"type": "paragraph", "text": "students sort a table in excel with the sort dialog"}])
    core.reindex()
    both = core.search_knowledge("sort table excel", k=5)
    assert "GENERATED earlier by this agent" in both and "teacher material" in both
    teacher = core.search_knowledge("sort table excel", source="teacher")
    assert "GENERATED" not in teacher and "notes.md" in teacher
    generated = core.search_knowledge("sort table excel", source="generated")
    assert "teacher material" not in generated and "plan.docx" in generated


def test_the_topic_filter_uses_the_first_folder(kb):
    (kb / "sql").mkdir(); (kb / "excel").mkdir()
    (kb / "sql" / "a.md").write_text("select statements")
    (kb / "excel" / "b.md").write_text("select cells")
    core.reindex()
    out = core.search_knowledge("select", topic="sql", k=5)
    assert "sql/a.md" in out and "excel/b.md" not in out


# --- check 8: files without readable text -----------------------------------------------------------
def test_a_scanned_pdf_is_reported_and_not_marked_indexed(kb):
    blank_pdf(kb / "scan.pdf")
    (kb / "ok.md").write_text("readable text")
    msg = core.reindex()
    assert msg.startswith("added 1") and "WARNING" in msg and "scan.pdf" in msg and "NOT searchable" in msg
    assert "scan.pdf" not in core._load_manifest()
    assert "scan.pdf" in core.reindex()                       # reported again every time until it is fixed


def test_a_file_that_cannot_be_read_is_reported_and_does_not_stop_the_others(kb):
    (kb / "bad.docx").write_bytes(b"this is not a zip")
    (kb / "ok.md").write_text("readable text")
    msg = core.reindex()
    assert msg.startswith("added 1") and "errors:" in msg and "bad.docx" in msg
    assert "readable text" in core.search_knowledge("readable")


def test_the_model_is_released_after_indexing(kb, monkeypatch):
    monkeypatch.setattr(core, "_model", object())
    (kb / "a.md").write_text("text")
    core.reindex()
    assert core._model is None


def test_embedding_uses_a_bounded_number_of_threads():
    assert 2 <= core._threads() <= (core.os.cpu_count() or 4) and settings.get().embed_batch_size == 16
