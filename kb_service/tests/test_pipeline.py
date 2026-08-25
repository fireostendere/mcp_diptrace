"""Integration: full pipeline against live Qdrant (ingest, dedup, update,
semantic & part-number search, filters, source/page provenance, restart)."""
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
PDF_FIX = FIX / "datasheets" / "tps62130_datasheet_fixture.pdf"
MD_FIX = FIX / "appnotes" / "buck_current_loop_appnote_fixture.md"


def _ingest(stores, settings, path: Path):
    from knowledge_base.ingest import ingest_path
    registry, store, _ = stores
    authority = "datasheet" if "datasheet" in str(path) else "appnote"
    reports = ingest_path(str(path), settings, registry, store,
                          authority_override=authority)
    assert len(reports) == 1
    return reports[0]


def test_ingest_pdf_and_no_duplicates(test_settings, stores):
    rep = _ingest(stores, test_settings, PDF_FIX)
    assert rep.status == "indexed"
    assert rep.doc_id and rep.n_chunks > 0

    # re-ingest identical content -> unchanged, no duplicate chunks
    points_before = stores[1].count_points()
    rep2 = _ingest(stores, test_settings, PDF_FIX)
    assert rep2.status == "unchanged"
    assert stores[1].count_points() == points_before


def test_changed_document_updates_index(test_settings, stores, tmp_path):
    work = tmp_path / "changed_doc.txt"
    work.write_text("Layout recommendation for the XM42 regulator: keep the "
                    "input loop small.\n" + ("Filler engineering text. " * 60),
                    encoding="utf-8")
    rep1 = _ingest(stores, test_settings, work)
    id1 = rep1.doc_id
    assert rep1.status == "indexed"

    # content changes -> new hash, old points removed
    work.write_text("UPDATED: The XM42 regulator needs a 47 uF output "
                    "capacitor for stability.\n" + ("Other filler text. " * 60),
                    encoding="utf-8")
    rep2 = _ingest(stores, test_settings, work)
    assert rep2.status == "reindexed"
    assert rep2.doc_id != id1

    hits = stores[1].scroll_by_doc(id1)
    assert hits == []  # old version fully replaced


def test_semantic_search_ru(test_settings, stores):
    from knowledge_base.search import search as do_search
    res = do_search("как уменьшить токовую петлю импульсного преобразователя",
                    test_settings, stores[1], top_k=5)
    assert res["hits"], "no semantic hits"
    top_titles = [h["title"] or "" for h in res["hits"][:3]]
    joined = " ".join(top_titles).lower()
    blob = " ".join(h["text"].lower() for h in res["hits"])
    assert "current loop" in blob or "токовую петлю" in blob or \
           "buck converter" in joined or "hot loop" in blob


def test_exact_part_number_search(test_settings, stores):
    from knowledge_base.search import search as do_search
    res = do_search("TPS62130 VIN capacitor", test_settings, stores[1], top_k=5)
    assert res["hits"]
    top = res["hits"][0]
    assert "TPS62130" in (top["title"] or "")
    assert any("TPS62130" in pn for pn in top["part_numbers"]) or \
           "TPS62130" in top["text"]


def test_metadata_filters(test_settings, stores):
    from knowledge_base.search import build_filter, search as do_search
    flt, _ = build_filter({"authority": "appnote"})
    res = do_search("layout guidelines", test_settings, stores[1], top_k=5,
                    filters={"authority": "appnote"})
    assert all(h["authority"] == "appnote" for h in res["hits"])
    with pytest.raises(ValueError):
        build_filter({"nonsense_key": 1})


def test_source_page_provenance(test_settings, stores):
    from knowledge_base.search import search as do_search
    res = do_search("PowerPAD thermal pad vias ground plane",
                    test_settings, stores[1], top_k=3)
    hit = res["hits"][0]
    assert hit["source"].endswith("tps62130_datasheet_fixture.pdf")
    assert isinstance(hit["page_start"], int) and hit["page_start"] >= 1
    section = (hit.get("section") or "").lower()
    assert section  # a section heading is attached


def test_knowledge_get_and_restart(test_settings, stores):
    from knowledge_base.ingest import ingest_path
    registry, store, _ = stores
    ingest_path(str(MD_FIX), test_settings, registry, store,
                authority_override="community")
    docs = registry.list_docs()
    md_docs = [d for d in docs if d.filename.endswith(".md")]
    assert md_docs
    doc = md_docs[0]

    # simulate restart: brand-new client objects over the same storage
    store.close()
    registry.close()
    from tests.helpers import open_stores
    registry2, store2, _ = open_stores(test_settings)

    points = store2.scroll_by_doc(doc.doc_id)
    assert points, "document lost after reconnect"
    assert points[0].payload["text"]

    from knowledge_base.search import search as do_search
    res = do_search("reduce hot loop EMI", test_settings, store2, top_k=3)
    assert res["hits"]

    store2.close()
    registry2.close()


def test_context_budget(test_settings, stores):
    from knowledge_base.search import search as do_search
    res = do_search("input capacitor placement", test_settings, stores[1],
                    top_k=8)
    limit_chars = test_settings.max_context_tokens * test_settings.chars_per_token
    assert len(res["context"]) <= limit_chars * 1.05
