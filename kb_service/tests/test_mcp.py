"""End-to-end MCP test: launches the real stdio server (like OpenCode does)
and calls knowledge_search / knowledge_sources / knowledge_status."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
PDF_FIX = FIX / "datasheets" / "tps62130_datasheet_fixture.pdf"
MD_FIX = FIX / "appnotes" / "buck_current_loop_appnote_fixture.md"


@pytest.fixture(scope="module")
def seeded_kb(test_settings):
    """Ingest fixtures once so MCP tools have something to find."""
    from knowledge_base.ingest import ingest_path

    from .helpers import open_stores
    registry, store, _ = open_stores(test_settings)
    try:
        ingest_path(str(PDF_FIX), test_settings, registry, store,
                    authority_override="datasheet")
        ingest_path(str(MD_FIX), test_settings, registry, store,
                    authority_override="appnote")
    finally:
        store.close()
        registry.close()
    return test_settings


def _with_mcp_session(test_settings, fn):
    """Open a real stdio MCP session against the server module and run fn(session)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {
        "QDRANT_URL": test_settings.qdrant_url,
        "KB_COLLECTION": test_settings.collection,
        "KB_DATA_DIR": str(test_settings.data_dir),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "knowledge_base.mcp_server"],
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )

    async def body():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)

    return asyncio.new_event_loop().run_until_complete(body())


def _parse(result):
    return json.loads(result.content[0].text)


def test_mcp_knowledge_search(seeded_kb):
    async def fn(session):
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert {"knowledge_search", "knowledge_get", "knowledge_ingest",
                "knowledge_research", "knowledge_sources",
                "knowledge_status"} <= names

        result = await session.call_tool(
            "knowledge_search",
            {"query": "TPS62130 layout recommendations", "top_k": 5})
        payload = _parse(result)
        assert payload["hits"], "MCP search returned no hits"
        top = payload["hits"][0]
        for key in ("title", "source", "page_start", "score", "document_id"):
            assert key in top
        assert payload["context"]

    _with_mcp_session(seeded_kb, fn)


def test_mcp_get_sources_status_research(seeded_kb):
    async def fn(session):
        # knowledge_get round-trip
        sources = _parse(await session.call_tool("knowledge_sources", {}))
        assert sources["count"] >= 1
        doc = sources["documents"][0]
        got = _parse(await session.call_tool(
            "knowledge_get", {"document_id": doc["document_id"]}))
        assert got["document"]["document_id"] == doc["document_id"]
        assert got["chunks"] and got["chunks"][0]["text"]

        status = _parse(await session.call_tool("knowledge_status", {}))
        assert status["qdrant_reachable"] is True
        assert (status["indexed_points"] or 0) > 0

        research = _parse(await session.call_tool(
            "knowledge_research", {"query": "best layout appnote"}))
        assert research["status"] == "not_implemented"

    _with_mcp_session(seeded_kb, fn)


def test_mcp_ingest_new_file(seeded_kb, tmp_path):
    new_doc = tmp_path / "brand_new_note.md"
    new_doc.write_text("# ZX99 Module Notes\n\nThe ZX99 module requires a "
                       "10 uF bootstrap capacitor near the BOOT pin.",
                       encoding="utf-8")

    async def fn(session):
        res = _parse(await session.call_tool(
            "knowledge_ingest", {"source": str(new_doc)}))
        assert res["ok"], res
        found = _parse(await session.call_tool(
            "knowledge_sources", {"query": "ZX99"}))
        assert found["count"] == 1
        search_res = _parse(await session.call_tool(
            "knowledge_search",
            {"query": "ZX99 bootstrap capacitor BOOT pin", "top_k": 3}))
        assert search_res["hits"]
        assert any("ZX99" in (h["title"] or "") for h in search_res["hits"])

    _with_mcp_session(seeded_kb, fn)
