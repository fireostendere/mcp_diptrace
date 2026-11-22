import importlib.util
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.domain import DocumentInfo
from diptrace_mcp.errors import (
    ExternalToolFailedError,
    ExternalToolUnavailableError,
    JobCancelledError,
    JobTimeoutError,
    Sha256MismatchError,
)
from diptrace_mcp.external_adapters import ExternalJobManager
from diptrace_mcp.jobs import JobStore
from diptrace_mcp.xml_document import sha256_bytes


def setup_job(tmp_path, monkeypatch, suffix):
    source = tmp_path / ('original' + suffix)
    source.write_bytes(b'original bytes')
    info = DocumentInfo(document_id='doc_' + 'a' * 16, source_type='native',
                        kind='pcb' if suffix.startswith('.dip') else 'schematic',
                        version='unknown', units='unknown', path=str(source),
                        sha256=sha256_bytes(source.read_bytes()))
    settings = Settings(workspace=tmp_path, allowed_roots=(tmp_path,), state_dir=tmp_path / 'state')
    manager = ExternalJobManager(settings, JobStore(settings.state_dir))
    monkeypatch.setattr(manager, '_launch_worker', lambda record, **kwargs: record)
    return manager, source, info


@pytest.mark.parametrize(('check', 'suffix', 'output'), [
    ('pcb_acceptance', '.dipxml', '.dipxml'),
    ('schematic_acceptance', '.dchxml', None),
    ('schematic_erc', '.dchxml', None),
    ('xml_export', '.dch', '.dchxml'),
    ('xml_export', '.dip', '.dipxml'),
])
def test_native_commands_copy_and_validate(tmp_path, monkeypatch, check, suffix, output):
    manager, source, info = setup_job(tmp_path, monkeypatch, suffix)
    record = manager.start_native_check(info, source, check=check, diptrace_root=tmp_path,
                                        timeout_seconds=None)
    command = record.command
    copied = Path(command[command.index('--project') + 1])
    assert copied != source and copied.read_bytes() == source.read_bytes()
    assert copied.suffix == suffix
    assert 30 <= int(command[command.index('--timeout') + 1]) <= 300
    if output:
        assert Path(command[command.index('--output-xml') + 1]).suffix == output


@pytest.mark.parametrize('timeout', [0, -1, 29, 301, float('nan')])
def test_invalid_timeout(tmp_path, monkeypatch, timeout):
    manager, source, info = setup_job(tmp_path, monkeypatch, '.dchxml')
    with pytest.raises(ExternalToolFailedError):
        manager.start_native_check(info, source, check='schematic_erc', diptrace_root=tmp_path,
                                   timeout_seconds=timeout)


def test_copy_rechecks_source_sha(tmp_path, monkeypatch):
    manager, source, info = setup_job(tmp_path, monkeypatch, '.dipxml')
    source.write_bytes(b'changed since load')
    with pytest.raises(Sha256MismatchError):
        manager.start_native_check(info, source, check='pcb_acceptance', diptrace_root=tmp_path,
                                   timeout_seconds=90)


@pytest.mark.parametrize(('check', 'suffix', 'hashes'), [
    ('schematic_acceptance', '.dchxml', ['a' * 64, 'b' * 64]),
    ('schematic_erc', '.dchxml', ['a' * 64]),
    ('xml_export', '.dch', ['a' * 64]),
])
def test_reviewed_startup_hashes_forwarded(tmp_path, monkeypatch, check, suffix, hashes):
    manager, source, info = setup_job(tmp_path, monkeypatch, suffix)
    record = manager.start_native_check(
        info, source, check=check, diptrace_root=tmp_path, timeout_seconds=90,
        startup_dialog_sha256=hashes,
    )
    assert record.command[-2 * len(hashes):] == [
        arg for digest in hashes for arg in ('--startup-dialog-sha256', digest)]


@pytest.mark.parametrize(('check', 'suffix', 'hashes'), [
    ('schematic_erc', '.dchxml', ['A' * 64]),
    ('schematic_erc', '.dchxml', ['a' * 63]),
    ('schematic_erc', '.dchxml', ['a' * 64 + '\n']),
    ('schematic_erc', '.dchxml', [123]),
    ('schematic_erc', '.dchxml', ['a' * 64] * 9),
    ('schematic_erc', '.dchxml', 'a' * 64),
    ('pcb_acceptance', '.dipxml', ['a' * 64]),
    ('xml_export', '.dip', ['a' * 64, 'b' * 64]),
])
def test_invalid_or_unsupported_startup_hashes_rejected(
    tmp_path, monkeypatch, check, suffix, hashes,
):
    manager, source, info = setup_job(tmp_path, monkeypatch, suffix)
    with pytest.raises(ExternalToolFailedError):
        manager.start_native_check(
            info, source, check=check, diptrace_root=tmp_path, timeout_seconds=90,
            startup_dialog_sha256=hashes,
        )
    assert not list(manager.store.jobs_dir.glob('job_*'))


def test_source_race_during_copy_fails_before_launch(tmp_path, monkeypatch):
    manager, source, info = setup_job(tmp_path, monkeypatch, '.dipxml')
    original = JobStore.store_artifact

    def racing_store(store, *args):
        copied = original(store, *args)
        source.write_bytes(b'changed during copy')
        return copied

    monkeypatch.setattr(JobStore, 'store_artifact', racing_store)
    with pytest.raises(Sha256MismatchError):
        manager.start_native_check(info, source, check='pcb_acceptance', diptrace_root=tmp_path,
                                   timeout_seconds=90)
    assert all(manager.store.read(p.name).status == 'failed'
               for p in manager.store.jobs_dir.glob('job_*'))


@pytest.mark.parametrize(('check', 'suffix'), [
    ('xml_export', '.dipxml'), ('schematic_erc', '.dch'), ('pcb_acceptance', '.dchxml'),
])
def test_invalid_check_input(tmp_path, monkeypatch, check, suffix):
    manager, source, info = setup_job(tmp_path, monkeypatch, suffix)
    with pytest.raises(ExternalToolFailedError):
        manager.start_native_check(info, source, check=check, diptrace_root=tmp_path,
                                   timeout_seconds=90)


def test_frozen_server_uses_only_bundled_helper(tmp_path, monkeypatch):
    from diptrace_mcp.native_helper import MODULES, helper_command

    server = tmp_path / 'diptrace_mcp_server.exe'
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(server))
    with pytest.raises(ExternalToolUnavailableError):
        helper_command('xml-export')
    helper = tmp_path / 'tools/diptrace_mcp_headless_gui/diptrace_mcp_headless_gui.exe'
    helper.parent.mkdir(parents=True)
    helper.touch()
    for dispatch in MODULES:
        assert helper_command(dispatch, '_worker', 'request') == [
            str(helper), dispatch, '_worker', 'request']
    monkeypatch.setattr(sys, 'executable', str(helper))
    assert helper_command('xml-export', '_worker')[0] == str(helper)


@pytest.mark.parametrize('dispatch', [
    'pcb-acceptance', 'schematic-acceptance', 'xml-export', 'native-cam', 'native-cad-worker',
])
@pytest.mark.parametrize('arguments', [['--help'], ['_worker', 'private-request']])
def test_bundled_dispatch_and_packaging(monkeypatch, dispatch, arguments):
    from diptrace_mcp.native_helper import MODULES

    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        'helper_entry', root / 'scripts/headless_gui_entry.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    seen = []
    fake = ModuleType(MODULES[dispatch])
    fake.main = lambda *args: seen.append(args or (sys.argv[1:],)) or 17
    monkeypatch.setitem(sys.modules, MODULES[dispatch], fake)
    monkeypatch.setattr(sys, 'argv', ['helper.exe', dispatch, *arguments])
    assert entry._main() == 17
    assert seen == [(arguments,)]
    assert MODULES[dispatch] in (root / 'packaging/diptrace_mcp_headless_gui.spec').read_text()
    assert dispatch in (root / 'scripts/build_windows_server.ps1').read_text()


@pytest.mark.parametrize('outcome', [0, 2, JobCancelledError, JobTimeoutError, OSError])
def test_native_job_execution_is_not_acceptance(tmp_path, monkeypatch, outcome):
    manager, source, info = setup_job(tmp_path, monkeypatch, '.dipxml')
    record = manager.start_native_check(info, source, check='pcb_acceptance',
                                        diptrace_root=tmp_path, timeout_seconds=90)
    command = record.command
    copied = Path(command[command.index('--project') + 1])

    def run(*args, **kwargs):
        copied.write_bytes(b'saved by native helper')
        (copied.parent / 'evidence.json').write_text('{"verdict": "FAIL"}')
        if isinstance(outcome, type):
            raise outcome('simulated interrupted execution')
        return SimpleNamespace(return_code=outcome, elapsed_seconds=1.0)

    monkeypatch.setattr(manager._runner, 'run', run)
    released = []
    manager._run_native_check(record.jobid, command, 270, threading.Event(),
                              SimpleNamespace(release=lambda: released.append(True)))
    final = manager.store.read(record.jobid)
    assert final.result['acceptance_decision'] == 'not_evaluated'
    assert 'evidence.json' in final.result['output_files']
    assert released == [True]
    assert source.read_bytes() == b'original bytes'
    if isinstance(outcome, int):
        assert final.status == 'completed'
        assert final.result['execution_status'] == 'finished'
        assert final.result['helper_passed'] == (outcome == 0)
    else:
        assert final.status == ('cancelled' if outcome is JobCancelledError else 'failed')
