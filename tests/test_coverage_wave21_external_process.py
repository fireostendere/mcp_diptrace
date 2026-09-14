from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import external_process as process


def _runner() -> process.ExternalProcessRunner:
    return process.ExternalProcessRunner(
        max_concurrent=1,
        max_log_bytes=64,
        poll_interval_seconds=0.01,
        termination_grace_seconds=0.01,
    )


def test_bounded_tail_and_runner_configuration_guards() -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        process._BoundedByteTail(0)
    tail = process._BoundedByteTail(4)
    tail.append(b"abcdefgh")
    assert len(tail.render()) == 4
    tail = process._BoundedByteTail(64)
    tail.append(b"a" * 80)
    assert tail.render().startswith(b"[log truncated")
    for values in (
        {"max_concurrent": 0, "max_log_bytes": 1},
        {"max_concurrent": 1, "max_log_bytes": 0},
        {"max_concurrent": 1, "max_log_bytes": 1, "poll_interval_seconds": 0},
        {"max_concurrent": 1, "max_log_bytes": 1, "termination_grace_seconds": 0},
    ):
        with pytest.raises(ValueError):
            process.ExternalProcessRunner(**values)


def test_finish_reader_forces_tree_and_closes_stuck_pipe() -> None:
    runner = _runner()

    class Reader:
        def __init__(self) -> None:
            self.joins = 0

        def join(self, *, timeout: float) -> None:
            assert timeout == 0.01
            self.joins += 1

        def is_alive(self) -> bool:
            return self.joins < 3

    closed: list[bool] = []
    fake = SimpleNamespace(stdout=SimpleNamespace(close=lambda: closed.append(True)))
    forced: list[bool] = []
    runner._signal_process_tree = lambda _process, *, force: forced.append(force)  # type: ignore[method-assign]
    reader = Reader()
    runner._finish_reader(fake, reader)
    assert forced == [True] and closed == [True] and reader.joins == 3


def test_process_tree_windows_and_posix_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    events: list[object] = []

    class FakeProcess:
        pid = 7
        stdout = None

        def poll(self) -> int | None:
            return None

        def kill(self) -> None:
            events.append("kill")

        def wait(self, timeout: float | None = None) -> int:
            events.append(("wait", timeout))
            return 0

        def send_signal(self, value: object) -> None:
            events.append(("signal", value))

    fake = FakeProcess()
    monkeypatch.setattr(process, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(process, "_close_windows_job", lambda _item: events.append("close"))
    runner._terminate_process_tree(fake)  # type: ignore[arg-type]
    runner._stop_remaining_descendants(fake)  # type: ignore[arg-type]
    runner._signal_process_tree(fake, force=True)  # type: ignore[arg-type]
    assert events.count("close") == 3 and events.count("kill") == 2

    def missing_group(_pid: int, _signal: object) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(process, "os", SimpleNamespace(name="posix", killpg=missing_group))
    runner._signal_process_tree(fake, force=False)  # type: ignore[arg-type]

    def denied_group(_pid: int, _signal: object) -> None:
        raise OSError("denied")

    monkeypatch.setattr(process, "os", SimpleNamespace(name="posix", killpg=denied_group))
    runner._signal_process_tree(fake, force=False)  # type: ignore[arg-type]
    assert any(isinstance(item, tuple) and item[0] == "signal" for item in events)


def test_drain_output_records_write_and_open_stream_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Stream:
        closed = False

        def fileno(self) -> int:
            return 3

        def close(self) -> None:
            self.closed = True

    chunks = iter((b"abc", b""))
    monkeypatch.setattr(
        process,
        "os",
        SimpleNamespace(read=lambda _fd, _size: next(chunks)),
    )
    monkeypatch.setattr(
        process,
        "atomic_write_bytes",
        lambda *_args: (_ for _ in ()).throw(OSError("disk")),
    )
    errors: list[Exception] = []
    stream = Stream()
    capture = process._BoundedByteTail(10)
    process._drain_output(stream, capture, errors, tmp_path / "log")  # type: ignore[arg-type]
    assert capture.render() == b"abc" and len(errors) == 1 and stream.closed

    stream = Stream()
    monkeypatch.setattr(
        process,
        "os",
        SimpleNamespace(read=lambda *_args: (_ for _ in ()).throw(ValueError("bad"))),
    )
    errors = []
    process._drain_output(stream, capture, errors, tmp_path / "log")  # type: ignore[arg-type]
    assert len(errors) == 1


def test_terminate_posix_escalates_after_wait_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    states = iter((None, None, None))
    fake = SimpleNamespace(
        pid=9,
        poll=lambda: next(states),
        wait=lambda timeout=None: (
            (_ for _ in ()).throw(subprocess.TimeoutExpired("x", timeout))
            if timeout is not None
            else 0
        ),
        kill=lambda: None,
    )
    signals: list[bool] = []
    monkeypatch.setattr(process, "os", SimpleNamespace(name="posix"))
    runner._signal_process_tree = lambda _process, *, force: signals.append(force)  # type: ignore[method-assign]
    runner._terminate_process_tree(fake)  # type: ignore[arg-type]
    assert signals == [False, True]
