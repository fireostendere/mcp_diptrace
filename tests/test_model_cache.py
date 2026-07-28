from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

import pytest

import diptrace_mcp.model_cache as model_cache_module
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import DEFAULT_MODEL_CACHE_MAX_BYTES, Settings
from diptrace_mcp.model_cache import ModelCache
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _document(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, MAX_BYTES)


def test_model_cache_evicts_lru_entries_to_byte_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pcb = _document("pcb.xml")
    schematic = _document("schematic.xml")
    pcb_size = model_cache_module._snapshot_accounted_bytes(build_snapshot(pcb))
    schematic_size = model_cache_module._snapshot_accounted_bytes(
        build_snapshot(schematic)
    )
    cache = ModelCache(
        max_entries=8,
        max_bytes=max(pcb_size, schematic_size) + 1,
    )
    real_build_snapshot = model_cache_module.build_snapshot
    build_count = 0

    def counted_build_snapshot(
        document: DipTraceDocument,
        *,
        live_session: bool,
    ):
        nonlocal build_count
        build_count += 1
        return real_build_snapshot(document, live_session=live_session)

    monkeypatch.setattr(
        model_cache_module,
        "build_snapshot",
        counted_build_snapshot,
    )

    first = cache.get(pcb, live_session=False)
    second = cache.get(schematic, live_session=False)

    assert build_count == 2
    assert cache.entry_count == 1
    assert cache.current_bytes <= cache.max_bytes
    assert cache.get(schematic, live_session=False) is second
    assert build_count == 2
    assert cache.get(pcb, live_session=False) is not first
    assert build_count == 3


def test_model_larger_than_budget_is_returned_but_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document("pcb.xml")
    cache = ModelCache(max_bytes=1)
    real_build_snapshot = model_cache_module.build_snapshot
    build_count = 0

    def counted_build_snapshot(
        source: DipTraceDocument,
        *,
        live_session: bool,
    ):
        nonlocal build_count
        build_count += 1
        return real_build_snapshot(source, live_session=live_session)

    monkeypatch.setattr(
        model_cache_module,
        "build_snapshot",
        counted_build_snapshot,
    )

    cache.get(document, live_session=False)
    cache.get(document, live_session=False)

    assert build_count == 2
    assert cache.stats() == {
        "entry_count": 0,
        "max_entries": 8,
        "accounted_bytes": 0,
        "max_bytes": 1,
    }


def test_invalidate_releases_accounted_bytes() -> None:
    document = _document("schematic.xml")
    cache = ModelCache()

    cache.get(document, live_session=False)

    assert cache.entry_count == 1
    assert cache.current_bytes > 0
    cache.invalidate(document.path)
    assert cache.entry_count == 0
    assert cache.current_bytes == 0


def test_concurrent_reads_build_one_consistent_cache_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document("pcb.xml")
    cache = ModelCache()
    real_build_snapshot = model_cache_module.build_snapshot
    count_lock = Lock()
    build_count = 0

    def counted_build_snapshot(
        source: DipTraceDocument,
        *,
        live_session: bool,
    ):
        nonlocal build_count
        with count_lock:
            build_count += 1
        return real_build_snapshot(source, live_session=live_session)

    monkeypatch.setattr(
        model_cache_module,
        "build_snapshot",
        counted_build_snapshot,
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        snapshots = list(
            executor.map(
                lambda _index: cache.get(document, live_session=False),
                range(16),
            )
        )

    assert build_count == 1
    assert all(snapshot is snapshots[0] for snapshot in snapshots)
    assert cache.entry_count == 1
    assert cache.current_bytes <= cache.max_bytes


@pytest.mark.parametrize(
    ("max_entries", "max_bytes"),
    [(0, 1), (1, 0)],
)
def test_cache_limits_must_be_positive(max_entries: int, max_bytes: int) -> None:
    with pytest.raises(ValueError):
        ModelCache(max_entries=max_entries, max_bytes=max_bytes)


def test_cache_budget_is_configured_and_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DIPTRACE_MCP_MODEL_CACHE_MAX_BYTES", "123456")

    settings = Settings.from_env()
    service = DipTraceService(settings)

    assert settings.model_cache_max_bytes == 123456
    assert settings.as_dict()["model_cache_max_bytes"] == 123456
    assert service.models.max_bytes == 123456
    assert service.get_capabilities()["limits"]["max_model_cache_bytes"] == 123456
    assert service.status()["model_cache"] == {
        "entry_count": 0,
        "max_entries": 8,
        "accounted_bytes": 0,
        "max_bytes": 123456,
    }
    assert DEFAULT_MODEL_CACHE_MAX_BYTES == 268435456
