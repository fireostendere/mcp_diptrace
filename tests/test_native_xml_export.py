"""Synthetic safety checks; these do not claim native DipTrace acceptance."""

import pytest

from diptrace_mcp import native_xml_export as nx
from diptrace_mcp.errors import DocumentError


@pytest.mark.parametrize(
    ("suffix", "xml_suffix", "source_type"),
    [(".dch", ".dchxml", "DipTrace-Schematic"), (".dip", ".dipxml", "DipTrace-PCB")],
)
def test_export_opens_copy_and_preserves_original(
    tmp_path, monkeypatch, suffix, xml_suffix, source_type
):
    source = tmp_path / ("original" + suffix)
    source.write_bytes(b"native source")
    target = tmp_path / ("export" + xml_suffix)

    def run(root, copy, output, timeout, approval):
        assert copy != source
        assert copy.read_bytes() == b"native source"
        copy.write_bytes(b"editor may save its private copy")
        output.write_text(f'<Source Type="{source_type}" Version="5.3.0.3" Units="mm"/>')
        return {"ok": True, "desktop_changed": False}

    monkeypatch.setattr(nx, "_run_hidden", run)
    result = nx.export_native_xml(tmp_path, source, target)
    assert result["ok"] is True
    assert result["source_type"] == source_type
    assert result["source_sha256_before"] == result["source_sha256_after"]
    assert source.read_bytes() == b"native source"
    assert target.is_file()
    assert not list(tmp_path.glob(".diptrace-export-*"))


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 301])
def test_invalid_timeout_fails_before_launch(tmp_path, monkeypatch, timeout):
    monkeypatch.setattr(nx, "_run_hidden", lambda *args: pytest.fail("must not launch"))
    with pytest.raises(ValueError):
        nx.export_native_xml(tmp_path, tmp_path / "board.dip", tmp_path / "out.dipxml", timeout)


def test_existing_output_is_never_overwritten(tmp_path, monkeypatch):
    source, target = tmp_path / "board.dip", tmp_path / "out.dipxml"
    source.write_bytes(b"source")
    target.write_bytes(b"existing")
    monkeypatch.setattr(nx, "_run_hidden", lambda *args: pytest.fail("must not launch"))
    with pytest.raises(FileExistsError):
        nx.export_native_xml(tmp_path, source, target)
    assert target.read_bytes() == b"existing"


@pytest.mark.parametrize("contents", ["not XML", '<Source Type="DipTrace-PCB"/>'])
def test_bad_export_is_not_published(tmp_path, monkeypatch, contents):
    source, target = tmp_path / "board.dch", tmp_path / "out.dchxml"
    source.write_bytes(b"source")

    def run(root, copy, output, timeout, approval):
        output.write_text(contents)
        return {"ok": True}

    monkeypatch.setattr(nx, "_run_hidden", run)
    with pytest.raises((DocumentError, ValueError)):
        nx.export_native_xml(tmp_path, source, target)
    assert not target.exists()


def test_worker_failure_does_not_publish_partial_xml(tmp_path, monkeypatch):
    source, target = tmp_path / "board.dch", tmp_path / "out.dchxml"
    source.write_bytes(b"source")

    def run(root, copy, output, timeout, approval):
        output.write_text('<Source Type="DipTrace-Schematic"/>')
        return {"ok": False, "error": "native dialog blocked export"}

    monkeypatch.setattr(nx, "_run_hidden", run)
    with pytest.raises(RuntimeError, match="native dialog"):
        nx.export_native_xml(tmp_path, source, target)
    assert not target.exists()


def test_output_race_preserves_other_file(tmp_path, monkeypatch):
    source, target = tmp_path / "board.dch", tmp_path / "out.dchxml"
    source.write_bytes(b"source")

    def run(root, copy, output, timeout, approval):
        output.write_text('<Source Type="DipTrace-Schematic"/>')
        target.write_bytes(b"created by someone else")
        return {"ok": True}

    monkeypatch.setattr(nx, "_run_hidden", run)
    with pytest.raises(FileExistsError):
        nx.export_native_xml(tmp_path, source, target)
    assert target.read_bytes() == b"created by someone else"


def test_changed_original_is_reported_not_restored(tmp_path, monkeypatch):
    source, target = tmp_path / "board.dch", tmp_path / "out.dchxml"
    source.write_bytes(b"source")

    def run(root, copy, output, timeout, approval):
        output.write_text('<Source Type="DipTrace-Schematic"/>')
        source.write_bytes(b"concurrent user edit")
        return {"ok": True}

    monkeypatch.setattr(nx, "_run_hidden", run)
    with pytest.raises(RuntimeError, match="source changed"):
        nx.export_native_xml(tmp_path, source, target)
    assert source.read_bytes() == b"concurrent user edit"
    assert not target.exists()
