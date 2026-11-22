import asyncio
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_native_check_jobs import setup_job
from test_tool_gaps import _Client

from diptrace_mcp import native_cad
from diptrace_mcp.errors import Sha256MismatchError
from diptrace_mcp.external_adapters import ExternalJobManager
from diptrace_mcp.services.context import DocumentGateway, DocumentTarget
from diptrace_mcp.tool_capabilities import tool_capability_mapping
from diptrace_mcp.xml_document import sha256_bytes


def test_native_export_public_schema_and_capability(tmp_path):
    client = _Client(tmp_path)
    tool = next(t for t in asyncio.run(client.server.list_tools()) if t.name == 'run_native_export')
    assert set(tool.inputSchema['properties']) == {'path', 'expected_sha256', 'timeout_seconds'}
    assert set(tool.inputSchema['required']) == {'path', 'expected_sha256'}
    assert tool.annotations.openWorldHint is True
    assert tool.annotations.readOnlyHint is False
    assert tool_capability_mapping()['run_native_export'] == ['read_capabilities.external_jobs']


def test_public_native_export_uses_private_copy_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(native_cad, 'installation_root', lambda: tmp_path / 'installed')
    monkeypatch.setattr(ExternalJobManager, '_launch_worker', lambda self, record, **kw: record)
    client = _Client(tmp_path)
    source = client.workspace / 'board.dipxml'
    data = source.read_bytes()
    result = client.call('run_native_export', path='board.dipxml',
                         expected_sha256=sha256_bytes(data))
    assert result['ok'] is True
    job = result['job']
    command = job['command']
    copied = Path(command[command.index('--project') + 1])
    assert copied != source and copied.read_bytes() == data
    assert command[command.index('--diptrace-root') + 1] == str(tmp_path / 'installed')
    assert 'native_cam_export' in ' '.join(command)
    assert Path(command[command.index('--output-dir') + 1]).parent == copied.parent
    assert 'manifest.json' in [p.name for p in copied.parent.iterdir()]
    assert any('raw CAM' in limitation for limitation in result['limitations'])


@pytest.mark.parametrize('case', ['policy', 'sha', 'kind', 'outside', 'timeout'])
def test_native_export_public_guards(tmp_path, monkeypatch, case):
    monkeypatch.setattr(native_cad, 'installation_root', lambda: tmp_path / 'installed')
    monkeypatch.setattr(ExternalJobManager, '_launch_worker',
                        lambda *args, **kw: pytest.fail('must not launch'))
    client = _Client(tmp_path, active_policy=(
        'read_only' if case == 'policy' else 'interactive_edit'))
    path = client.workspace / ('schematic.xml' if case == 'kind' else 'board.dipxml')
    if case == 'outside':
        outside = tmp_path / 'outside.dipxml'
        outside.write_bytes(path.read_bytes())
        path = outside
    sha = '0' * 64 if case == 'sha' else sha256_bytes(path.read_bytes())
    result = client.call('run_native_export', path=str(path), expected_sha256=sha,
                         **({'timeout_seconds': 301} if case == 'timeout' else {}))
    assert result['ok'] is False


def test_native_export_rejects_live_target(tmp_path, monkeypatch):
    client = _Client(tmp_path)
    monkeypatch.setattr(DocumentGateway, 'resolve_target',
                        lambda *args: DocumentTarget(client.workspace / 'board.dipxml', 'live'))
    result = client.call('run_native_export', path='board.dipxml', expected_sha256='0' * 64)
    assert result['ok'] is False
    assert 'live session' in result['error']['message']


def test_native_export_rechecks_sha_before_launch(tmp_path, monkeypatch):
    manager, source, info = setup_job(tmp_path, monkeypatch, '.dipxml')
    monkeypatch.setattr(native_cad, 'installation_root', lambda: tmp_path / 'installed')
    source.write_bytes(b'changed after service validation')
    with pytest.raises(Sha256MismatchError):
        manager.start_native_export(info, source)
    assert all(manager.store.read(p.name).status == 'failed'
               for p in manager.store.jobs_dir.glob('job_*'))


@pytest.mark.skipif(sys.platform == 'win32', reason='no GUI in tests')
def test_native_export_job_uses_real_cli_without_signoff(tmp_path, monkeypatch):
    monkeypatch.setattr(native_cad, 'installation_root', lambda: tmp_path / 'installed')
    client = _Client(tmp_path)
    source = client.workspace / 'board.dipxml'
    original = source.read_bytes()
    started = client.call('run_native_export', path='board.dipxml',
                          expected_sha256=sha256_bytes(original), timeout_seconds=30)
    jobid = started['job']['jobid']
    for _ in range(100):
        job = client.call('get_job_status', jobid=jobid)['result']['job']
        if job['status'] in {'completed', 'failed', 'cancelled'}:
            break
        time.sleep(0.05)
    assert job['status'] == 'completed'
    assert job['result']['helper_passed'] is False
    assert job['result']['acceptance_decision'] == 'not_evaluated'
    assert {'manifest.json', 'log.txt', 'input.dipxml'} <= set(job['result']['output_files'])
    assert 'requires Windows' in (Path(job['result']['output_directory']) / 'log.txt').read_text()
    assert source.read_bytes() == original


def test_frozen_native_cad_child_uses_owned_helper_dispatch(tmp_path, monkeypatch):
    client = _Client(tmp_path)
    source = client.workspace / 'board.dipxml'
    output = tmp_path / 'native-output'
    helper = tmp_path / 'tools/diptrace_mcp_headless_gui/diptrace_mcp_headless_gui.exe'
    helper.parent.mkdir(parents=True)
    helper.touch()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'server.exe'))
    monkeypatch.setattr(native_cad, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(native_cad, 'input_desktop_name', lambda: 'Default')
    calls = []

    def wait(timeout):
        assert (output / 'worker-start').is_file()
        (output / 'native-result.json').write_text(json.dumps({'completed': True}))
        return 0

    @contextmanager
    def launch(argv):
        calls.append(argv)
        yield SimpleNamespace(pid=123, wait=wait)

    @contextmanager
    def desktop(name):
        yield SimpleNamespace(launch=launch)

    owned = []
    job = SimpleNamespace(assign=lambda pid: owned.append(pid),
                          terminate_and_close=lambda: owned.append('closed'))
    monkeypatch.setattr(native_cad, 'HiddenDesktop', desktop)
    monkeypatch.setattr(native_cad.KillOnCloseJob, 'create', lambda: job)
    request = native_cad.NativeCadRequest(
        source=source, output_dir=output, diptrace_root=tmp_path,
        expected_sha256=sha256_bytes(source.read_bytes()), export_manufacturing=True,
    )
    assert native_cad.run_native_cad(request)['completed'] is True
    assert calls[0][:3] == [str(helper), 'native-cad-worker', '--worker']
    assert owned == [123, 'closed']
