"""Unit tests for chunking, metadata heuristics and sparse vectors."""
from knowledge_base.chunk import chunk_blocks
from knowledge_base.extract import Block
from knowledge_base.metadata import (detect_manufacturer,
                                     extract_part_numbers, extract_revision,
                                     infer_authority)
from knowledge_base.sparse import sparse_tf, tokenize


def _blocks():
    return [
        Block(1, "heading", "Layout Guidelines"),
        Block(1, "para", "Keep the input capacitor close to the VIN pin. " * 10),
        Block(2, "heading", "Electrical Characteristics"),
        Block(2, "para", "Quiescent current is 25 uA typical. " * 8),
    ]


def test_chunks_respect_section_boundaries():
    chunks = chunk_blocks(_blocks(), chunk_size=600, overlap=50)
    assert len(chunks) == 2
    assert chunks[0].section == "Layout Guidelines"
    assert chunks[1].section == "Electrical Characteristics"
    assert chunks[0].page_start == 1
    assert chunks[1].page_end == 2


def test_long_section_is_split_with_size_limit():
    long_para = Block(3, "para", "word " * 3000)
    chunks = chunk_blocks([Block(3, "heading", "Description"), long_para],
                          chunk_size=800, overlap=100)
    assert len(chunks) > 2
    assert all(len(c.text) <= 900 for c in chunks)


def test_metadata_part_numbers_from_title_and_filename():
    pn = extract_part_numbers("tps62130_datasheet.pdf",
                              "TPS62130 Step-Down Converter")
    assert "TPS62130" in pn
    # blacklist words are not part numbers
    assert "PDF" not in extract_part_numbers("", "PDF DATASHEET USB GPIO LED")


def test_revision_detection_unambiguous_only():
    assert extract_revision("SLVS973F REV C") == "C"
    assert extract_revision("Rev. B") == "B"
    # two different revisions in text -> refuse to guess
    assert extract_revision("Rev A initial release. Rev C corrected") is None
    assert extract_revision("nothing here") is None


def test_manufacturer_detection():
    assert detect_manufacturer("Texas Instruments SLVS973") == "Texas Instruments"
    assert detect_manufacturer("completely unrelated text") is None


def test_authority_inference():
    assert infer_authority("/x/datasheets/tps123.pdf", "file") == "datasheet"
    assert infer_authority("/x/appnotes/snva777.pdf", "file") == "appnote"
    assert infer_authority("https://diptrace.com/docs/pcb.html", "website") == "official_docs"
    assert infer_authority("https://youtube.com/watch?v=x", "youtube") == "community"


def test_sparse_deterministic_and_nonempty():
    a = sparse_tf("TPS62130 VIN capacitor layout")
    b = sparse_tf("TPS62130 VIN capacitor layout")
    assert a.indices == b.indices
    assert a.non_empty
    assert len(a.values) == len(set(a.indices))  # no duplicate indices
    assert any(len(t) >= 2 for t in tokenize("layout"))
